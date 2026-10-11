"""X (Twitter) — 使用官方 X API v2 的 recent search（需要環境變數 X_BEARER_TOKEN）。

沒有 token 時會改用 config 裡的 rss_feeds（例如自架 RSSHub）；兩者都沒有就跳過 X。
"""
from __future__ import annotations

import os

from ..models import Post
from ..util import clean_text, log, session
from .feeds import collect_x_rss

URL = "https://api.x.com/2/tweets/search/recent"


def _search(token: str, query: str, max_results: int) -> list[Post]:
    r = session().get(URL, timeout=30, headers={"Authorization": f"Bearer {token}"}, params={
        "query": query,
        "max_results": max(10, min(100, max_results)),
        "tweet.fields": "created_at,public_metrics,entities,author_id",
        "expansions": "author_id",
        "user.fields": "username,verified,public_metrics",
        "sort_order": "relevancy",
    })
    if r.status_code != 200:
        log.warning("X API %s: %s", r.status_code, r.text[:200])
        return []
    data = r.json()
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    out = []
    for t in data.get("data", []):
        u = users.get(t.get("author_id"), {})
        handle = u.get("username", "i")
        m = t.get("public_metrics", {})
        links = [x.get("expanded_url") for x in t.get("entities", {}).get("urls", []) if x.get("expanded_url")]
        out.append(Post(
            id=f"x:{t['id']}",
            source="x",
            channel=f"@{handle}",
            url=f"https://x.com/{handle}/status/{t['id']}",
            text=clean_text(t.get("text"), 2000),
            published=t.get("created_at"),
            extra={"likes": m.get("like_count", 0), "retweets": m.get("retweet_count", 0),
                   "followers": u.get("public_metrics", {}).get("followers_count", 0), "links": links},
        ))
    return out


def collect(cfg: dict) -> list[Post]:
    out: list[Post] = []
    token = os.environ.get("X_BEARER_TOKEN")
    if token:
        queries = list(cfg.get("queries", []))
        if accts := cfg.get("accounts_to_watch"):
            queries.append("(" + " OR ".join(f"from:{a}" for a in accts) + ") -is:retweet")
        for q in queries:
            out += _search(token, q, cfg.get("max_results", 50))
        # 過濾掉幾乎沒人互動的小帳號貼文（常見詐騙 / 洗版）
        out = [p for p in out if p.extra.get("followers", 0) >= 1000 or p.extra.get("likes", 0) >= 20]
    out += collect_x_rss(cfg)
    if not token and not cfg.get("rss_feeds"):
        log.info("X：未設定 X_BEARER_TOKEN 或 rss_feeds，略過")
    else:
        log.info("X：%d 則貼文", len(out))
    return out
