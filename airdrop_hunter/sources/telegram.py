"""Telegram 公開頻道 — 透過 https://t.me/s/<頻道> 的網頁預覽抓取最新訊息（不需要帳號或 API key）。"""
from __future__ import annotations

from datetime import timedelta

from bs4 import BeautifulSoup

from ..models import Post
from ..util import clean_text, get, log, now_utc, parse_iso


def parse_channel(html: str, channel: str) -> list[Post]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for wrap in soup.select(".tgme_widget_message_wrap"):
        msg = wrap.select_one(".tgme_widget_message")
        body = wrap.select_one(".tgme_widget_message_text")
        link = wrap.select_one("a.tgme_widget_message_date")
        when = wrap.select_one("time")
        if not (msg and body and link):
            continue
        for br in body.find_all("br"):
            br.replace_with("\n")
        text = clean_text(body.get_text(), 3000)
        if len(text) < 40:
            continue
        links = sorted({a["href"] for a in body.select("a[href^=http]")})[:15]
        posts.append(Post(
            id=f"telegram:{msg.get('data-post', link['href'])}",
            source="telegram",
            channel=channel,
            url=link["href"],
            text=text,
            published=when.get("datetime") if when else None,
            extra={"links": links},
        ))
    return posts


def collect(cfg: dict) -> list[Post]:
    cutoff = now_utc() - timedelta(days=cfg.get("max_age_days", 7))
    out: list[Post] = []
    for ch in cfg.get("channels", []):
        try:
            r = get(f"https://t.me/s/{ch}", polite_delay=1.5, allow_redirects=False)
            if r.status_code != 200:   # 頻道不存在或關閉預覽時會轉址
                log.warning("Telegram @%s 無法預覽（HTTP %s）", ch, r.status_code)
                continue
            posts = parse_channel(r.text, ch)
        except Exception as e:  # noqa: BLE001
            log.warning("Telegram @%s 失敗: %s", ch, e)
            continue
        out += [p for p in posts if (d := parse_iso(p.published)) is None or d >= cutoff]
    log.info("Telegram：%d 則貼文", len(out))
    return out
