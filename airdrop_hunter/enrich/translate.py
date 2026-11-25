"""免費翻譯（沒有 ANTHROPIC_API_KEY 時使用）— Google 翻譯公開端點。

- 翻譯結果存在 data/translations.json，同一段文字只翻一次（避免被 Google 限流）。
- 失敗時回傳原文，並記錄失敗次數；呼叫端可據此把項目標記為「下次重試」。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import timedelta
from pathlib import Path

from ..util import iso, log, now_utc, parse_iso, session

try:   # 選用：把翻譯結果統一成繁體（台灣用語）或簡體
    import opencc
    _CONVERTERS = {"zh-TW": opencc.OpenCC("s2twp"), "zh-CN": opencc.OpenCC("t2s")}
except ImportError:  # pragma: no cover
    _CONVERTERS = {}

URL = "https://translate.googleapis.com/translate_a/single"
CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "translations.json"
CACHE_KEEP_DAYS = 45
MAX_CONSECUTIVE_FAILURES = 3      # 連續失敗這麼多次 → 本次執行不再請求（多半是被限流）

_cache: dict | None = None
_consecutive = 0
_fail_total = 0


def fail_count() -> int:
    """到目前為止翻譯失敗的次數（呼叫前後比較，就知道這段有沒有翻譯失敗）。"""
    return _fail_total


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def save_cache() -> None:
    cache = _load()
    cutoff = now_utc() - timedelta(days=CACHE_KEEP_DAYS)
    for k in [k for k, v in cache.items() if (parse_iso(v.get("used")) or cutoff) < cutoff]:
        del cache[k]
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    except OSError as e:
        log.warning("無法寫入翻譯快取：%s", e)


def _request(chunk: str, target: str) -> str | None:
    global _consecutive, _fail_total
    if _consecutive >= MAX_CONSECUTIVE_FAILURES:
        _fail_total += 1
        return None
    try:
        time.sleep(0.3)
        r = session().post(URL, timeout=20, params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t"},
                           data={"q": chunk})
        r.raise_for_status()
        _consecutive = 0
        return "".join(seg[0] for seg in r.json()[0] if seg and seg[0])
    except Exception as e:  # noqa: BLE001
        _consecutive += 1
        _fail_total += 1
        if _consecutive == MAX_CONSECUTIVE_FAILURES:
            log.warning("Google 翻譯連續失敗（%s），本次先停止翻譯，下次執行會重試", e)
        return None


def translate(text: str, target: str = "zh-TW") -> str:
    text = (text or "").strip()
    if not text:
        return text
    cache = _load()
    key = hashlib.sha1(f"{target}\0{text}".encode()).hexdigest()[:20]
    if hit := cache.get(key):
        hit["used"] = iso(now_utc())[:10]
        return hit["t"]
    out, ok = [], True
    for chunk in _chunks(text, 1800):
        res = _request(chunk, target)
        if res is None:
            ok = False
            res = chunk
        out.append(res)
    result = "\n".join(out)
    if target in _CONVERTERS:
        result = _CONVERTERS[target].convert(result)
    if ok:
        cache[key] = {"t": result, "used": iso(now_utc())[:10]}
    return result


def translate_list(items: list[str], target: str = "zh-TW") -> list[str]:
    """把多行合併成一次請求翻譯，再拆回來（省請求次數）。"""
    if not items:
        return []
    joined = translate("\n".join(i.replace("\n", " ") for i in items), target)
    parts = joined.split("\n")
    if len(parts) != len(items):
        return [translate(i, target) for i in items]
    # Google 偶爾會跳過含網址的英文行（原封不動傳回）→ 單獨再翻一次
    return [translate(src, target) if out.strip() == src.strip() and _mostly_latin(src) else out
            for src, out in zip(items, parts)]


def _mostly_latin(s: str) -> bool:
    s = re.sub(r"https?://\S+", "", s)
    letters = re.findall(r"[A-Za-z]", s)
    return len(letters) >= 8 and len(letters) > 0.5 * len(s.replace(" ", ""))


def _chunks(text: str, size: int) -> list[str]:
    chunks, cur = [], ""
    for line in text.split("\n"):
        for piece in [line[i:i + size] for i in range(0, len(line), size)] or [""]:
            if cur and len(cur) + len(piece) + 1 > size:
                chunks.append(cur)
                cur = piece
            else:
                cur = f"{cur}\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks
