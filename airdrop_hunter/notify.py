"""Telegram 推播（選用）：把新發現的項目傳到你的 Telegram（需要 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID）。"""
from __future__ import annotations

import html
import os

from .render import public_project
from .store import Store
from .util import log, session


def format_message(p: dict) -> str:
    e = html.escape
    kind = "🎮 P2E 遊戲" if p["kind"] == "p2e" else "🪂 空投"
    lines = [f"<b>{kind}｜{e(p['name'])}</b>",
             f"狀態：{e(p['status_zh'])}｜{e(p['confirmed_zh'] or '')}",
             f"支撐：{e(p['backing_zh'] or '')}" + (f"（{e('、'.join(p['backers'][:4]))}）" if p["backers"] else ""),
             f"難度：{'★' * p['difficulty']}{'☆' * (5 - p['difficulty'])}｜費用：{e(p['cost_zh'] or '')}｜風險：{e(p['risk_zh'] or '')}",
             "", e(p["summary"][:400])]
    if p["steps"]:
        lines += ["", "<b>怎麼做：</b>"] + [f"{i}. {e(s[:150])}" for i, s in enumerate(p["steps"][:5], 1)]
    if p["distribution"]:
        lines += ["", f"<b>如何發放：</b>{e(p['distribution'][:200])}"]
    if p["links"]:
        lines += ["", " ｜ ".join(f'<a href="{e(l["url"])}">{e(l["label"])}</a>' for l in p["links"][:4])]
    return "\n".join(lines)


def send_new(store: Store, new_keys: list[str], cfg: dict) -> int:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat and cfg.get("telegram_enabled", True)) or not new_keys:
        return 0
    recs = [store.projects[k] for k in new_keys if k in store.projects and store.projects[k].get("analysis")]
    pubs = [public_project(r) for r in recs]
    # 只推播有結構化來源、風險不是「高」的項目，避免把詐騙項目推給你
    pubs = [p for p in pubs if not p["social_only"] and p["risk_level"] != "high"]
    pubs.sort(key=lambda p: -p["score"])
    sent = 0
    for p in pubs[: cfg.get("max_messages_per_run", 10)]:
        r = session().post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20, json={
            "chat_id": chat, "text": format_message(p), "parse_mode": "HTML", "disable_web_page_preview": True})
        if r.ok:
            sent += 1
        else:
            log.warning("Telegram 推播失敗：%s", r.text[:200])
    log.info("Telegram 推播 %d 則", sent)
    return sent
