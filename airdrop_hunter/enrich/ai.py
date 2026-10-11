"""Claude AI 分析：翻譯成中文、判斷支撐機構 / 難易度 / 費用 / 發放方式，並可上網查證。"""
from __future__ import annotations

import json
import os
import re
from datetime import date

import anthropic

from ..models import Project
from ..util import log, safe_url
from .schema import ANALYSIS_SCHEMA, POSTS_SCHEMA

LANG_NAME = {"zh-TW": "繁體中文（台灣用語）", "zh-CN": "简体中文"}

PROJECT_SYSTEM = """You are a careful crypto research analyst writing for Chinese-speaking airdrop hunters \
and play-to-earn (P2E) gamers. You receive raw data about one airdrop / points campaign / testnet / \
P2E game, collected from aggregator sites and social media. Produce a structured analysis.

Write every free-text field in {lang}. Keep project names, token tickers and chain names in their \
original form (e.g. "Titan Exchange", "$VARI", "Base").

How to judge each field:
- backing_level: "top" = tier-1 crypto VCs (a16z, Paradigm, Polychain, YZi/Binance Labs, Coinbase \
Ventures, Pantera, Multicoin, Dragonfly...), major exchanges, big tech / big game companies, or a major \
L1/L2 foundation; "notable" = known mid-tier funds or >= $5M raised; "some" = small/unknown backers; \
"none_known" = nothing public. List only backers that the data or your search results actually show — \
never guess.
- difficulty (1-5): 1 = a few minutes of free social/sign-up tasks; 2 = simple on-chain or testnet \
interaction; 3 = repeated activity over days/weeks or moderate capital; 4 = significant capital, \
trading volume, or technical steps; 5 = running nodes/servers, coding, or heavy capital at risk.
- cost_type: "free" = no money needed (testnet, socials, waitlist); "gas_only" = only small network \
fees; "deposit" = must deposit / stake / trade / provide liquidity; "paid" = must buy tokens/NFTs or pay \
to play; "unknown" if unclear.
- distribution: how rewards will actually reach users (points converted at TGE, claim page, direct \
wallet drop, NFT, in-game earnings sold on exchanges...), plus vesting/unlock if known.
- steps: concrete, numbered-style actions a beginner can follow, in order (no numbering prefix).
- status / confirmed: "confirmed" only if the team officially announced a token or airdrop.
- risk_level and risks: point out unconfirmed airdrops, capital at risk, sybil filters, KYC, and any \
scam signals (asks for seed phrase/private key, upfront payment, fake claim sites, guaranteed returns). \
If the project looks like a scam, set risk_level "high" and say so plainly.
- official_links: only official URLs (website, app, X, Discord, docs) you are confident about.
- tips: one or two practical tips (e.g. use a separate wallet, best time to participate).

If information is missing, say "未公布" (or "未公布" in simplified) instead of inventing it. \
Today's date is {today}."""

POSTS_SYSTEM = """You read recent crypto posts from Telegram channels, X, Reddit and news sites, and \
extract airdrop / points / testnet / play-to-earn game opportunities for Chinese-speaking users.

For every post return: post_id (copied exactly), relevant (true only if the post is about a specific \
airdrop, points program, testnet, token claim, or P2E / web3 game opportunity), title_zh (short {lang} \
headline), summary_zh (2-3 sentence {lang} summary with the key action and deadline), and projects \
(every concrete project the post presents as an opportunity — skip projects merely mentioned in \
passing, exchanges' generic promos, and price talk). For each project: its canonical name, kind \
("p2e" for games), status, confirmed, actions (what users must do, short, {lang}), chains, backers \
explicitly named in the post, official links found in the post, and scam_risk (true if the post asks \
for seed phrases / private keys, upfront payments, or looks like a fake claim). Today's date is {today}."""


class ClaudeAnalyzer:
    def __init__(self, cfg: dict, lang: str = "zh-TW"):
        self.cfg = cfg
        self.lang = lang
        self.model = os.environ.get("CLAUDE_MODEL") or cfg.get("model", "claude-opus-5-5")
        self.client = anthropic.Anthropic(max_retries=3)
        self.calls = 0

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    # ── 單一項目深度分析 ────────────────────────────────────────
    def analyze_project(self, p: Project, related_posts: list[dict]) -> dict | None:
        payload = {
            "name": p.name, "source": p.source, "source_url": p.source_url, "kind_hint": p.kind,
            "status_hint": p.status, "confirmed_hint": p.confirmed, "description": p.description,
            "actions": p.actions, "steps": p.steps, "chains": p.chains, "tags": p.tags,
            "backers": p.backers, "funds_raised_usd": p.funds_raised_usd, "requirements": p.requirements,
            "cost_hint": p.cost_hint, "reward_hint": p.reward_hint, "distribution_hint": p.distribution_hint,
            "start": p.start, "end": p.end, "links": p.links, "extra": p.extra,
            "related_social_posts": [{"source": r["source"], "channel": r["channel"], "url": r["url"],
                                      "text": r["text"][:800]} for r in related_posts[:5]],
        }
        prompt = ("Analyze this project. " + (
            "Use web search to verify backers/funding, whether a token or airdrop is confirmed, and "
            "official links — especially when the raw data is thin. " if self.cfg.get("web_search", True) else "")
            + "Raw data:\n```json\n" + json.dumps(payload, ensure_ascii=False, default=str) + "\n```")
        system = PROJECT_SYSTEM.format(lang=LANG_NAME.get(self.lang, self.lang), today=date.today())
        tools = []
        if self.cfg.get("web_search", True):
            tools = [{"type": "web_search_20260209", "name": "web_search",
                      "max_uses": int(self.cfg.get("max_web_searches", 2))}]
        data = self._structured(system, prompt, ANALYSIS_SCHEMA, tools)
        if data:
            data["official_links"] = [l for l in data.get("official_links", []) if safe_url(l.get("url"))]
        return data

    # ── 社群 / 新聞貼文批次抽取 ─────────────────────────────────
    def extract_posts(self, posts: list[dict]) -> list[dict]:
        system = POSTS_SYSTEM.format(lang=LANG_NAME.get(self.lang, self.lang), today=date.today())
        batch = [{"post_id": p["id"], "source": p["source"], "channel": p["channel"], "title": p.get("title", ""),
                  "text": p["text"][:1500], "links": p.get("extra", {}).get("links", [])} for p in posts]
        prompt = "Posts:\n```json\n" + json.dumps(batch, ensure_ascii=False) + "\n```"
        data = self._structured(system, prompt, POSTS_SCHEMA, [])
        return data.get("posts", []) if data else []

    # ── 共用：呼叫 Claude 並取得符合 schema 的 JSON ──────────────
    def _structured(self, system: str, prompt: str, schema: dict, tools: list) -> dict | None:
        messages: list = [{"role": "user", "content": prompt}]
        try:
            for _ in range(4):   # web search 可能回傳 pause_turn，需要接續
                self.calls += 1
                kwargs = dict(
                    model=self.model,
                    max_tokens=16000,
                    system=system,
                    messages=messages,
                    output_config={"effort": self.cfg.get("effort", "low"),
                                   "format": {"type": "json_schema", "schema": schema}},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
                if tools:
                    kwargs["tools"] = tools
                resp = self.client.beta.messages.create(**kwargs)
                if resp.stop_reason == "pause_turn":
                    messages = [messages[0], {"role": "assistant", "content": resp.content}]
                    continue
                if resp.stop_reason == "refusal":
                    log.warning("Claude 拒絕回答（%s），改用規則分析", getattr(resp, "stop_details", None))
                    return None
                if resp.stop_reason == "max_tokens":
                    log.warning("Claude 輸出超過長度上限，略過")
                    return None
                return _parse_json(resp.content)
        except anthropic.RateLimitError as e:
            log.warning("Claude API 達到速率限制：%s", e)
        except anthropic.APIStatusError as e:
            log.warning("Claude API 錯誤 %s：%s", e.status_code, e.message)
        except anthropic.APIConnectionError as e:
            log.warning("無法連線 Claude API：%s", e)
        return None


def _parse_json(content) -> dict | None:
    # web search 會產生多個 text 區塊（含引用），structured output 的 JSON 在最後的文字裡
    texts = [b.text for b in content if getattr(b, "type", "") == "text"]
    for candidate in ("".join(texts), texts[-1] if texts else ""):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass
    joined = "".join(texts)
    if m := re.search(r"\{.*\}", joined, re.S):
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    log.warning("無法解析 Claude 的 JSON 輸出")
    return None
