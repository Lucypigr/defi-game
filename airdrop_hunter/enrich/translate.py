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
        time.sleep(0.8)   # 放慢速度，降低被 Google 限流的機會
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


# 一律不翻譯的專有名詞（錢包、平台、幣種），避免被翻成奇怪的中文
ALWAYS_KEEP = ["MetaMask", "Rabby", "Phantom", "Keplr", "Backpack", "OKX Wallet", "Trust Wallet", "Discord",
               "Telegram", "Galxe", "Zealy", "Layer3", "Guild", "Twitter", "USDC", "USDT", "ETH", "SOL", "BNB",
               "TGE", "Gas", "DeFi", "NFT", "EVM", "Solana", "Ethereum", "Arbitrum", "Base", "Hyperliquid"]

# 機器翻譯常見的怪翻譯 → 加密貨幣圈常用說法（只用於繁體）
GLOSSARY_TW = [
    (r"連(?:線|結)(?:你|您)?的?錢包", "連接錢包"),
    (r"(推薦|邀請|存取|訪問)(?:程式碼|代碼)", r"\1碼"),
    (r"程式碼", "代碼"),
    (r"立即播放", "立即開始遊戲"),
    (r"(?:等候|等待|候補)名單", "候補名單"),
    (r"點數", "積分"),
    (r"(?:造訪|訪問)", "前往"),
    (r"水龍頭(?!\s*[（(]Faucet)", "水龍頭（Faucet，免費領測試幣）"),
    (r"您", "你"),
    (r"永續期貨", "永續合約"),
    (r"空投下降", "空投"),
]
_GLOSSARY = [(re.compile(a), b) for a, b in GLOSSARY_TW]
_TOKEN = re.compile(r"ZQX\s?(\d+)")


def polish(text: str, target: str = "zh-TW") -> str:
    """套用詞彙表，修正常見的機器翻譯用語。"""
    if target != "zh-TW":
        return text
    for rx, rep in _GLOSSARY:
        text = rx.sub(rep, text)
    return text


def _protect(text: str, keep) -> tuple[str, list[str]]:
    """把網址、$代幣、專有名詞換成 ZQX0、ZQX1… 佔位符，翻譯後再換回來。"""
    saved: list[str] = []

    def stash(m: re.Match) -> str:
        saved.append(m.group(0))
        return f"ZQX{len(saved) - 1}"

    text = re.sub(r"https?://[^\s)）」，。]+", stash, text)
    text = re.sub(r"\$[A-Za-z][A-Za-z0-9]{1,11}\b", stash, text)
    names = sorted({n for n in list(keep) + ALWAYS_KEEP if n and len(n) >= 3}, key=len, reverse=True)
    if names:
        rx = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(n) for n in names) + r")(?![A-Za-z0-9])")
        text = rx.sub(stash, text)
    return text, saved


def _restore(text: str, saved: list[str]) -> str | None:
    found = {int(m.group(1)) for m in _TOKEN.finditer(text)}
    if found != set(range(len(saved))):
        return None          # Google 弄丟或改壞了佔位符 → 改用不保護的翻譯
    return _TOKEN.sub(lambda m: saved[int(m.group(1))], text)


def translate(text: str, target: str = "zh-TW", keep=()) -> str:
    text = (text or "").strip()
    if not text:
        return text
    protected, saved = _protect(text, keep)
    cache = _load()
    key = hashlib.sha1(f"{target}\0{protected}\0{saved}".encode()).hexdigest()[:20]
    if hit := cache.get(key):
        hit["used"] = iso(now_utc())[:10]
        return polish(hit["t"], target)
    out, ok = [], True
    for chunk in _chunks(protected, 1800):
        res = _request(chunk, target)
        if res is None:
            ok = False
            res = chunk
        out.append(res)
    result = _restore("\n".join(out), saved) if ok else None
    if result is None:
        if ok and saved:          # 佔位符壞掉：直接翻原文
            raw = [_request(c, target) for c in _chunks(text, 1800)]
            ok = all(r is not None for r in raw)
            result = "\n".join(r if r is not None else c for r, c in zip(raw, _chunks(text, 1800)))
        else:
            result = text
    if target in _CONVERTERS:
        result = _CONVERTERS[target].convert(result)
    if ok:
        cache[key] = {"t": result, "used": iso(now_utc())[:10]}
    return polish(result, target)


def translate_list(items: list[str], target: str = "zh-TW", keep=()) -> list[str]:
    """把多行合併成一次請求翻譯，再拆回來（省請求次數）。"""
    if not items:
        return []
    joined = translate("\n".join(i.replace("\n", " ") for i in items), target, keep)
    parts = joined.split("\n")
    if len(parts) != len(items):
        return [translate(i, target, keep) for i in items]
    # Google 偶爾會跳過整行英文（原封不動傳回）→ 單獨再翻一次
    return [translate(src, target, keep) if out.strip() == src.strip() and _mostly_latin(src) else out
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
