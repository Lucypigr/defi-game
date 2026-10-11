"""免費翻譯（沒有 ANTHROPIC_API_KEY 時使用）— Google 翻譯公開端點，失敗時回傳原文。"""
from __future__ import annotations

from functools import lru_cache

from ..util import log, session

try:   # 選用：把翻譯結果統一成繁體（台灣用語）或簡體
    import opencc
    _CONVERTERS = {"zh-TW": opencc.OpenCC("s2twp"), "zh-CN": opencc.OpenCC("t2s")}
except ImportError:  # pragma: no cover
    _CONVERTERS = {}

URL = "https://translate.googleapis.com/translate_a/single"
_failures = 0


@lru_cache(maxsize=4096)
def translate(text: str, target: str = "zh-TW") -> str:
    global _failures
    text = (text or "").strip()
    if not text or _failures >= 5:      # 連續失敗太多次就不再嘗試，避免拖慢整個流程
        return text
    out = []
    for chunk in _chunks(text, 1800):
        try:
            r = session().post(URL, timeout=20, params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t"},
                               data={"q": chunk})
            r.raise_for_status()
            out.append("".join(seg[0] for seg in r.json()[0] if seg and seg[0]))
            _failures = 0
        except Exception as e:  # noqa: BLE001
            _failures += 1
            log.debug("翻譯失敗：%s", e)
            out.append(chunk)
    result = "\n".join(out)
    return _CONVERTERS[target].convert(result) if target in _CONVERTERS else result


def translate_list(items: list[str], target: str = "zh-TW") -> list[str]:
    """把多行合併成一次請求翻譯，再拆回來（省請求次數）。"""
    if not items:
        return []
    joined = translate("\n".join(i.replace("\n", " ") for i in items), target)
    parts = joined.split("\n")
    return parts if len(parts) == len(items) else [translate(i, target) for i in items]


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
