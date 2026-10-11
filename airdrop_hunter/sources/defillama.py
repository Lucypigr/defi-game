"""DefiLlama — 找出「還沒發代幣、但鎖倉量很高」的 DeFi 協議，這類項目最常做回溯空投。"""
from __future__ import annotations

from datetime import timedelta

from ..models import Project
from ..util import clean_text, from_ms, get, log, now_utc

URL = "https://api.llama.fi/protocols"

# 交易所、跨鏈橋、託管型產品幾乎不會空投，排除
EXCLUDED_CATEGORIES = {
    "CEX", "Bridge", "Canonical Bridge", "Chain", "RWA", "Basis Trading", "Treasury Manager",
    "Liquid Staking", "Onchain Capital Allocator", "Developer Tools", "Payments", "Services",
    "Staking Pool", "Wallets", "Exotic Options", "SoFi", "Real World Assets",
}
GAME_CATEGORIES = {"Gaming", "NFT Marketplace", "Metaverse"}
_EXCHANGE_NAMES = ("binance", "coinbase", "okx", "bybit", "bitget", "kraken", "robinhood", "gemini")


def select(protocols: list[dict], cfg: dict) -> list[Project]:
    min_tvl = cfg.get("min_tvl_usd", 30_000_000)
    since = now_utc() - timedelta(days=cfg.get("listed_within_days", 900))
    out = []
    for p in protocols:
        tvl = p.get("tvl") or 0
        if tvl < min_tvl or p.get("parentProtocol") or p.get("category") in EXCLUDED_CATEGORIES:
            continue
        if p.get("gecko_id") or p.get("cmcId") or p.get("symbol") not in (None, "", "-"):
            continue  # 已經有代幣
        name = p.get("name", "")
        if any(x in name.lower() for x in _EXCHANGE_NAMES):
            continue
        listed = from_ms((p.get("listedAt") or 0) * 1000)
        if listed and listed < since:
            continue
        links = {"website": p.get("url")}
        if p.get("twitter"):
            links["twitter"] = f"https://x.com/{p['twitter']}"
        out.append(Project(
            name=name,
            source="defillama",
            source_url=f"https://defillama.com/protocol/{p.get('slug')}",
            kind="p2e" if p.get("category") in GAME_CATEGORIES else "defi",
            status="potential",
            confirmed=False,
            description=clean_text(p.get("description"), 1200),
            actions=f"使用協議（{p.get('category')}）— 尚無代幣，可能回溯空投",
            chains=(p.get("chains") or [])[:6],
            tags=[p.get("category") or "", "no-token"],
            links={k: v for k, v in links.items() if v},
            score=min(100.0, 30 + tvl / 50_000_000),
            extra={"tvl_usd": round(tvl), "category": p.get("category")},
        ))
    out.sort(key=lambda x: -x.extra["tvl_usd"])
    return out[: cfg.get("max_items", 40)]


def collect(cfg: dict) -> list[Project]:
    try:
        projects = select(get(URL, timeout=60).json(), cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("DefiLlama 失敗: %s", e)
        return []
    log.info("DefiLlama：%d 個尚未發幣的高 TVL 協議", len(projects))
    return projects
