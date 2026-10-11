"""RSS 類來源：Reddit、大型新聞網站、Google News、以及 X 的 RSS 橋接（RSSHub 等）。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import feedparser

from ..models import Post
from ..util import clean_text, get, iso, log, now_utc


def _entry_time(e) -> datetime | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def parse_feed(xml: bytes | str, *, source: str, channel: str, keywords: list[str] | None = None,
               max_age_days: int = 7) -> list[Post]:
    feed = feedparser.parse(xml)
    cutoff = now_utc() - timedelta(days=max_age_days)
    kw = re.compile("|".join(re.escape(k) for k in keywords), re.I) if keywords else None
    out = []
    for e in feed.entries:
        when = _entry_time(e)
        if when and when < cutoff:
            continue
        title = clean_text(e.get("title"))
        summary = e.get("summary") or ""
        if e.get("content"):
            summary = e["content"][0].get("value") or summary
        text = clean_text(summary, 2500)
        if kw and not kw.search(f"{title} {text}"):
            continue
        link = e.get("link") or ""
        out.append(Post(
            id=f"{source}:{e.get('id') or link}",
            source=source,
            channel=channel,
            url=link,
            title=title,
            text=text or title,
            published=iso(when),
        ))
    return out


def _fetch(url: str, delay: float = 0.0, **kw) -> list[Post]:
    try:
        return parse_feed(get(url, allow_redirects=True, polite_delay=delay).content, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("RSS %s 失敗: %s", url, e)
        return []


def collect_reddit(cfg: dict) -> list[Post]:
    out = []
    for sub in cfg.get("subreddits", []):
        out += _fetch(f"https://www.reddit.com/r/{sub}/new/.rss", delay=6, source="reddit",
                      channel=f"r/{sub}", max_age_days=cfg.get("max_age_days", 7))
    log.info("Reddit：%d 則貼文", len(out))
    return out


def collect_news(cfg: dict) -> list[Post]:
    out = []
    for f in cfg.get("feeds", []):
        out += _fetch(f["url"], source="news", channel=f["name"], keywords=cfg.get("keywords"),
                      max_age_days=cfg.get("max_age_days", 10))
    log.info("新聞：%d 篇相關文章", len(out))
    return out


def collect_x_rss(cfg: dict) -> list[Post]:
    out = []
    for url in cfg.get("rss_feeds") or []:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        out += _fetch(url, source="x", channel=f"@{name}", max_age_days=7)
    return out
