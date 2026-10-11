"""知名投資機構 / 大型公司名單，用來判斷「是否有大型公司支撐」。

名單可以自行增修。比對時不分大小寫、只要名稱包含關鍵字就算。
"""
from __future__ import annotations

# 一線：頂級加密 VC、交易所投資部門、大型科技 / 遊戲公司、主流公鏈基金會
TOP_TIER = [
    "a16z", "andreessen", "paradigm", "sequoia", "polychain", "binance labs", "yzi labs", "binance",
    "coinbase", "pantera", "multicoin", "dragonfly", "electric capital", "framework ventures",
    "jump crypto", "jump trading", "galaxy", "hack vc", "founders fund", "lightspeed", "tiger global",
    "haun ventures", "variant", "blockchain capital", "digital currency group", "dcg", "okx ventures",
    "animoca", "bitkraft", "delphi", "hashed", "spartan", "1kx", "placeholder", "robot ventures",
    "ethereum foundation", "solana foundation", "solana ventures", "arbitrum foundation", "optimism",
    "polygon", "sui foundation", "mysten", "aptos", "ava labs", "avalanche", "near foundation",
    "ton foundation", "immutable", "ubisoft", "samsung", "google", "microsoft", "nvidia", "tencent",
    "sony", "softbank", "visa", "paypal", "blackrock", "fidelity", "franklin templeton", "circle",
    "tether", "kraken", "bybit", "crypto.com", "robinhood", "standard crypto", "usv", "union square",
    "greenoaks", "temasek", "mirana", "wintermute", "gsr", "amber group",
]

NOTABLE = [
    "fenbushi", "iosg", "hashkey", "arrington", "mechanism", "shima", "foresight", "spartan",
    "kucoin", "gate", "mexc", "bitget", "htx", "huobi", "okx", "dao5", "nomad", "ngc", "kenetic",
    "big brain", "maven 11", "cms holdings", "alliance dao", "longhash", "everyrealm", "merit circle",
    "yield guild", "ygg", "infinity ventures", "sfermion", "makers fund", "griffin gaming", "hypersphere",
    "mh ventures", "manifold", "selini", "frachtis", "lattice", "nascent", "north island", "dcvc",
    "accel", "khosla", "general catalyst", "kingsway", "cyber fund", "eden block", "folius",
    "breyer", "castle island", "distributed global", "matrixport", "a&t capital", "presto",
]

LEVEL_ZH = {"top": "頂級機構支持", "notable": "知名機構支持", "some": "有投資方", "none_known": "未知 / 無公開投資方"}


def tier_of(name: str) -> int | None:
    n = name.lower()
    if any(k in n for k in TOP_TIER):
        return 1
    if any(k in n for k in NOTABLE):
        return 2
    return None


def backing_level(backers: list[dict] | list[str], funds_raised_usd: float | None = None) -> str:
    names = [b["name"] if isinstance(b, dict) else b for b in backers]
    tiers = [tier_of(n) for n in names]
    if 1 in tiers:
        return "top"
    if 2 in tiers or (funds_raised_usd or 0) >= 5_000_000:
        return "notable"
    if names:
        return "some"
    return "none_known"


def find_mentions(text: str) -> list[str]:
    """從文字中找出提到的知名機構（給沒有結構化投資方資料的項目用）。"""
    low = text.lower()
    hits = []
    for k in TOP_TIER + NOTABLE:
        if len(k) >= 4 and k in low and k not in ("binance", "google", "visa", "circle", "gate", "variant"):
            hits.append(k)
    return sorted(set(hits))
