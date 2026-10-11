"""規則式分析（沒有 ANTHROPIC_API_KEY 時使用）：關鍵字判斷難度 / 費用 / 發放方式 + 免費翻譯。

輸出格式與 AI 分析完全相同（見 enrich/schema.py），網頁不需要區分。
"""
from __future__ import annotations

import re

from ..models import Project
from . import vc
from .translate import translate, translate_list

_PAID = re.compile(r"\b(deposit|stake|staking|bridge|buy|purchase|mint|swap|trade|trading|lend|borrow|"
                   r"provide liquidity|add liquidity|lp\b|vault|pre-deposit|hold)", re.I)
_FREE = re.compile(r"\b(testnet|faucet|waitlist|sign ?up|register|follow|retweet|join (?:discord|telegram)|"
                   r"quest|galxe|zealy|layer3|check-?in|social|referr?al|invite|telegram mini ?app|tap)", re.I)
_STRONG_PAID = re.compile(r"\b(deposit|stake|staking|bridge|buy|purchase|mint|lend|provide liquidity|"
                          r"add liquidity|vault|pre-deposit)", re.I)
_HARD = re.compile(r"\b(nodes?|vps|validator|docker|command[- ]line|(?<!trading )terminal|cli|github|ubuntu|ssh)\b", re.I)
_DAILY = re.compile(r"\b(daily|every day|each day|streak|check-?in|weekly|epoch|season)", re.I)
_SCAM = re.compile(r"(seed phrase|private key|recovery phrase|send (?:eth|usdt|bnb|sol) to|double your|"
                   r"guaranteed profit|100x)", re.I)
_GAME = re.compile(r"\b(game|gaming|gamefi|play-to-earn|play to earn|p2e|quest game|rpg|nft game|metaverse)\b", re.I)


def analyze(p: Project, related_posts: list[dict], lang: str = "zh-TW") -> dict:
    # 難度 / 費用只看「要做的事」，避免被產品介紹裡的 trading、stake 等字眼誤判
    text = " ".join([p.actions, " ".join(p.steps) if p.steps else p.description, p.cost_hint, " ".join(p.tags)])
    backers = [b["name"] for b in p.backers]
    if not backers:
        backers = vc.find_mentions(p.description)
    level = vc.backing_level(backers, p.funds_raised_usd)

    paid, free = bool(_PAID.search(text)), bool(_FREE.search(text))
    if "testnet" in text.lower():   # 測試網上的「交易」用的是免費測試幣
        paid = bool(_STRONG_PAID.search(text))
        free = free or not paid
    if p.source == "coingecko":
        cost_type = "paid"
    elif paid:
        cost_type = "deposit"
    elif free:
        cost_type = "free" if "testnet" in text.lower() or not re.search(r"on-?chain|transaction|gas", text, re.I) else "gas_only"
    else:
        cost_type = "unknown"

    # 1 = 幾分鐘免費任務；3 = 需資金或持續互動；5 = 架節點 / 技術操作 + 資金
    difficulty = 1
    if paid:
        difficulty += 2
    elif not free:
        difficulty += 1
    if _DAILY.search(text):
        difficulty += 1
    if _HARD.search(text):
        difficulty += 2
    if "kyc" in p.requirements:
        difficulty += 1
    if len(p.steps) >= 9:
        difficulty += 1
    difficulty = max(1, min(5, difficulty))

    low = text.lower()
    if p.status == "claimable":
        distribution = "已開放領取：到官方網站連接錢包後手動 Claim。"
    elif "point" in low:
        distribution = "先累積積分 (Points)，預計在代幣發行 (TGE) 時依積分比例換成代幣空投。"
    elif "nft" in low:
        distribution = "可能以 NFT 或白名單形式發放，詳見官方公告。"
    elif "testnet" in low:
        distribution = "測試網互動紀錄可能作為日後空投資格，發放方式待官方公告。"
    elif p.source == "coingecko":
        distribution = "邊玩邊賺：遊戲內賺取代幣 / NFT，可在交易所賣出。"
    else:
        distribution = "官方尚未公布，通常是代幣發行時空投到錢包或開放 Claim。"

    risks = []
    if p.confirmed is False or p.status == "potential":
        risks.append("官方尚未確認會空投，可能白做工。")
    if cost_type in ("deposit", "paid"):
        risks.append("需要投入資金，有本金虧損 / 智能合約風險。")
    if level == "none_known":
        risks.append("查無知名投資方，請自行查證團隊背景。")
    if _SCAM.search(text):
        risks.append("內容出現疑似詐騙字眼（索取助記詞 / 私鑰或保證獲利），請勿參與！")
    risk_level = "high" if (_SCAM.search(text) or (cost_type == "deposit" and level == "none_known")) \
        else "medium" if risks else "low"

    summary_src = "\n".join((p.description or p.actions or "").split("\n")[:2])[:700]
    steps_src = p.steps or ([p.actions] if p.actions else [])
    return {
        "summary": translate(summary_src, lang) if summary_src else "",
        "kind": "p2e" if p.kind == "p2e" or _GAME.search(text) else "defi",
        "status": p.status,
        "confirmed": "confirmed" if p.confirmed else ("unconfirmed" if p.confirmed is False else "speculative"),
        "backing_level": level,
        "backers": backers[:12],
        "backing_note": (f"已募資約 ${p.funds_raised_usd/1e6:.1f}M。" if p.funds_raised_usd else "")
                        + ("" if backers else "未找到公開的投資方資料。"),
        "difficulty": difficulty,
        "difficulty_note": "",
        "time_commitment": "需持續每日 / 每週互動" if _DAILY.search(text) else "一次性完成即可",
        "cost_type": cost_type,
        "cost_note": {"free": "只需錢包或社群帳號，不用花錢。", "gas_only": "只需少量鏈上手續費 (Gas)。",
                      "deposit": "需要存入 / 交易資金才能累積資格。", "paid": "需要購買代幣或 NFT 才能遊玩。",
                      "unknown": "資訊不足，請以官方說明為準。"}[cost_type],
        "steps": translate_list([s[:400] for s in steps_src[:12]], lang),
        "reward": translate(p.reward_hint, lang) if p.reward_hint else "未公布",
        "distribution": distribution,
        "requirements": sorted(set(p.requirements + ["錢包 (Wallet)"])),
        "deadline": p.end or "未公布",
        "risk_level": risk_level,
        "risks": risks,
        "official_links": [],
        "tips": "",
    }


def summarize_post(post: dict, lang: str = "zh-TW") -> dict:
    title = post.get("title") or ""
    text = post.get("text") or ""
    return {
        "title_zh": translate(title, lang) if title else "",
        "summary_zh": translate(text[:600], lang),
    }
