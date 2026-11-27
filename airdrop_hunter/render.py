"""輸出：docs/data.json（網頁資料）、docs/index.html（網頁）、docs/AIRDROPS.md（GitHub 上直接看的清單）。"""
from __future__ import annotations

import json
from datetime import timedelta
import shutil
from pathlib import Path

from .enrich.rules import clean_step
from .enrich.translate import polish
from .enrich.vc import LEVEL_ZH
from .store import Store
from .util import now_utc, parse_iso, safe_url

ROOT = Path(__file__).resolve().parent.parent

STATUS_ZH = {"ongoing": "進行中", "upcoming": "即將開始", "potential": "潛在空投（未確認）",
             "claimable": "可領取", "ended": "已結束", "unknown": "狀態未知"}
COST_ZH = {"free": "免費", "gas_only": "僅需 Gas 手續費", "deposit": "需投入資金", "paid": "需付費 / 購買",
           "unknown": "未知"}
CONFIRMED_ZH = {"confirmed": "官方已確認", "unconfirmed": "官方未確認", "speculative": "推測"}
RISK_ZH = {"low": "低", "medium": "中", "high": "高"}
DIFF_ZH = {1: "非常簡單", 2: "簡單", 3: "中等", 4: "困難", 5: "非常困難"}
SOURCE_ZH = {"airdrops.io": "airdrops.io", "dropstab": "DropsTab", "defillama": "DefiLlama",
             "coingecko": "CoinGecko"}


def _links(raw: dict, analysis: dict) -> list[dict]:
    label = {"website": "官網", "participate": "參與連結", "twitter": "X (Twitter)", "telegram": "Telegram",
             "discord": "Discord", "docs": "文件"}
    out, seen = [], set()
    for k, u in raw.get("links", {}).items():
        if (u := safe_url(u)) and u not in seen:
            out.append({"label": label.get(k, k), "url": u})
            seen.add(u)
    for l in analysis.get("official_links", []):
        if (u := safe_url(l.get("url"))) and u not in seen:
            out.append({"label": l.get("label") or "連結", "url": u})
            seen.add(u)
    return out


def _main_link(raw: dict, analysis: dict) -> str | None:
    """「前往參與」按鈕要開的網址：參與連結 > 官網 > AI 找到的官方連結。"""
    links = raw.get("links", {})
    for k in ("participate", "website"):
        if u := safe_url(links.get(k)):
            return u
    return next((u for l in analysis.get("official_links", []) if (u := safe_url(l.get("url")))), None)


def deadline_info(raw_deadline: str | None, now=None) -> dict:
    """把 'TBA'、'2026-11-11T00:00:00+00:00' 之類的截止時間轉成中文與剩餘天數。"""
    now = now or now_utc()
    s = (raw_deadline or "").strip()
    if not s or s.upper() in ("TBA", "TBD", "N/A", "NONE", "未公布", "UNKNOWN") or s.startswith("未"):
        return {"deadline_zh": "未公布", "days_left": None}
    dt = parse_iso(s)
    if not dt:
        return {"deadline_zh": s, "days_left": None}
    days = (dt - now).total_seconds() / 86400
    date_zh = f"{dt.year}/{dt.month}/{dt.day}"
    if days < 0:
        return {"deadline_zh": f"{date_zh}（已截止）", "days_left": int(days)}
    left = "今天截止" if days < 1 else f"剩 {int(days)} 天"
    return {"deadline_zh": f"{date_zh}（{left}）", "days_left": int(days)}


def recommend_score(p: dict) -> int:
    """推薦指數 0–100：值不值得做（有大機構、官方確認、免費、簡單、低風險、新出現的排前面）。"""
    if p["status"] == "ended":
        return 0
    s = {"top": 28, "notable": 18, "some": 6}.get(p["backing_level"], 0)
    s += {"claimable": 22, "ongoing": 12, "upcoming": 8, "potential": 2}.get(p["status"], 0)
    s += 12 if p["confirmed"] == "confirmed" else 0
    s += {"free": 18, "gas_only": 15, "unknown": 6, "deposit": 4, "paid": 0}.get(p["cost_type"], 0)
    s += (5 - p["difficulty"]) * 3
    s += {"low": 8, "medium": 3, "high": -40}.get(p["risk_level"], 0)
    s += min(10, p["score"] / 10)                      # 來源熱度
    if p["first_seen"] and (parse_iso(p["first_seen"]) or now_utc()) > now_utc() - timedelta(days=7):
        s += 6                                        # 一週內新出現
    if p["social_only"]:
        s -= 10
    if p["days_left"] is not None and 0 <= p["days_left"] <= 7:
        s += 4                                        # 快截止了，提醒一下
    if not p["steps"]:
        s -= 10
    return max(1, min(100, round(s)))


def public_project(rec: dict) -> dict:
    out = _public_project(rec)
    # 詞彙表修正（連線你的錢包 → 連接錢包…），舊資料不用重新翻譯也能立即改善
    for k in ("summary", "reward", "distribution", "cost_note", "backing_note", "tips", "time_commitment"):
        out[k] = polish(out[k] or "")
    for k in ("steps", "notes", "risks"):
        out[k] = [polish(x) for x in out[k]]
    out["recommend"] = recommend_score(out)
    return out


def _public_project(rec: dict) -> dict:
    raw, a = rec["raw"], rec.get("analysis") or {}
    status = "ended" if rec.get("stale") else (a.get("status") or raw["status"])
    dl = deadline_info(a.get("deadline") or raw.get("end"))
    if dl["days_left"] is not None and dl["days_left"] < -1 and status != "claimable":
        status = "ended"      # 已過截止日
    diff = a.get("difficulty") or 3
    return {
        "key": rec["key"],
        "name": raw["name"],
        "kind": a.get("kind") or raw["kind"],
        "status": status,
        "status_zh": STATUS_ZH.get(status, status) + ("（久未更新）" if rec.get("stale") else ""),
        "confirmed": a.get("confirmed", "speculative"),
        "confirmed_zh": CONFIRMED_ZH.get(a.get("confirmed", "speculative")),
        "summary": a.get("summary", ""),
        "backing_level": a.get("backing_level", "none_known"),
        "backing_zh": LEVEL_ZH.get(a.get("backing_level", "none_known")),
        "backers": a.get("backers", []),
        "backing_note": a.get("backing_note", ""),
        "funds_raised_usd": raw.get("funds_raised_usd"),
        "difficulty": diff,
        "difficulty_zh": DIFF_ZH.get(diff, ""),
        "difficulty_note": a.get("difficulty_note", ""),
        "time_commitment": a.get("time_commitment", ""),
        "cost_type": a.get("cost_type", "unknown"),
        "cost_zh": COST_ZH.get(a.get("cost_type", "unknown")),
        "cost_note": a.get("cost_note", ""),
        "steps": [x for x in (clean_step(st) for st in a.get("steps", [])) if x],
        "notes": a.get("notes", []),
        "main_link": _main_link(raw, a),
        "reward": a.get("reward", ""),
        "distribution": a.get("distribution", ""),
        "requirements": a.get("requirements", []),
        "deadline": a.get("deadline", ""),
        **deadline_info(a.get("deadline") or raw.get("end")),
        "risk_level": a.get("risk_level", "medium"),
        "risk_zh": RISK_ZH.get(a.get("risk_level", "medium")),
        "risks": a.get("risks", []),
        "tips": a.get("tips", ""),
        "chains": raw.get("chains", []),
        "tags": [t for t in raw.get("tags", []) if t],
        "links": _links(raw, a),
        "sources": [{"name": SOURCE_ZH.get(s["source"], s["source"]), "url": safe_url(s.get("url"))}
                    for s in rec.get("sources", [])],
        "social_only": rec.get("social_only", False),
        "market": {k: raw.get("extra", {}).get(k) for k in
                   ("symbol", "price_usd", "market_cap_usd", "change_24h_pct", "tvl_usd")
                   if raw.get("extra", {}).get(k) is not None},
        "score": round(raw.get("score", 0) + 5 * (len(rec.get("sources", [])) - 1)
                       + 2 * min(5, len(rec.get("related_posts", []))), 1),
        "first_seen": rec.get("first_seen"),
        "last_seen": rec.get("last_seen"),
        "analysis_by": rec.get("analysis_by"),
        "related_posts": rec.get("related_posts", [])[:8],
    }


def public_post(p: dict) -> dict:
    zh = p.get("zh") or {}
    return {
        "id": p["id"], "source": p["source"], "channel": p["channel"], "url": safe_url(p["url"]),
        "published": p.get("published") or p.get("first_seen"),
        "title": zh.get("title_zh") or p.get("title") or (zh.get("summary_zh") or p["text"]).split("\n")[0][:70],
        "summary": polish(zh.get("summary_zh") or p["text"][:300]),
        "original": (p.get("title") + "\n" if p.get("title") else "") + p["text"][:600],
        "projects": p.get("projects", []),
    }


def build_public(store: Store) -> dict:
    projects = [public_project(r) for r in store.projects.values() if "raw" in r]
    projects.sort(key=lambda p: (p["status"] == "ended", -p["recommend"], -p["score"]))
    posts = [public_post(p) for p in store.posts.values() if p.get("relevant", True)]
    posts.sort(key=lambda p: p["published"] or "", reverse=True)
    return {"updated_at": store.data.get("updated_at"), "last_run": store.data.get("last_run"),
            "projects": projects, "posts": posts[:300]}


def to_markdown(pub: dict) -> str:
    lines = [f"# 空投 / P2E 項目清單\n\n最後更新：{pub['updated_at']}（自動產生，請勿手動修改）\n",
             "> ⚠️ 本清單由程式自動整理，不構成投資建議。任何要求你提供助記詞 / 私鑰的都是詐騙。\n"]
    for kind, title in (("defi", "DeFi / 加密貨幣空投"), ("p2e", "P2E 邊玩邊賺遊戲")):
        rows = [p for p in pub["projects"] if p["kind"] == kind and p["status"] != "ended"]
        lines.append(f"\n## {title}（{len(rows)}）\n")
        lines.append("| 項目 | 狀態 | 支撐 | 難度 | 費用 | 風險 | 簡介 |")
        lines.append("|---|---|---|---|---|---|---|")
        for p in rows[:150]:
            link = next((l["url"] for l in p["links"]), p["sources"][0]["url"] if p["sources"] else "")
            name = f"[{p['name']}]({link})" if link else p["name"]
            summary = (p["summary"] or "").replace("|", "／").replace("\n", " ")[:90]
            lines.append(f"| {name} | {p['status_zh']} | {p['backing_zh']} | {'★' * p['difficulty']} | "
                         f"{p['cost_zh']} | {p['risk_zh']} | {summary} |")
    return "\n".join(lines) + "\n"


def render(store: Store, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pub = build_public(store)
    (out_dir / "data.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "AIRDROPS.md").write_text(to_markdown(pub), encoding="utf-8")
    shutil.copyfile(ROOT / "site" / "index.html", out_dir / "index.html")
    (out_dir / ".nojekyll").write_text("")
