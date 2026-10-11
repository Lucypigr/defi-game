"""共用工具：HTTP、時間、文字處理、日誌。"""
from __future__ import annotations

import hashlib
import html
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("airdrop_hunter")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        _session = s
    return _session


def get(url: str, *, timeout: int = 30, polite_delay: float = 0.0, **kw) -> requests.Response:
    if polite_delay:
        time.sleep(polite_delay)
    r = session().get(url, timeout=timeout, **kw)
    r.raise_for_status()
    return r


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def from_ms(ms: int | float | None) -> datetime | None:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None


def slugify(name: str) -> str:
    """把項目名稱轉成去重用的 key（例如 "Titan Exchange" → "titan-exchange"）。"""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\b(airdrop|testnet|points?|program|campaign|network|protocol|finance|labs?)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or hashlib.sha1(name.encode()).hexdigest()[:10]


def clean_text(s: str | None, limit: int | None = None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s


def strip_markdown(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\(([^)|\s]+)[^)]*\)", r"\1 (\2)", s)   # [文字](網址|target=..) → 文字 (網址)
    s = re.sub(r"(\*\*|__)", "", s)
    s = re.sub(r"^\s*[-•*]\s+", "", s, flags=re.M)
    return s.strip()


def content_hash(*parts: object) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode())
    return h.hexdigest()[:16]


def safe_url(u: str | None) -> str | None:
    """只接受 http(s) 連結，避免 javascript: 之類的惡意連結進到網頁。"""
    if u and re.match(r"^https?://", u.strip(), re.I):
        return u.strip()
    return None
