"""CoinGecko — 已經有代幣、正在營運中的熱門 P2E / GameFi 遊戲（含市值與 24h 漲跌）。"""
from __future__ import annotations

from ..models import Project
from ..util import get, log

URL = "https://api.coingecko.com/api/v3/coins/markets"


def to_project(c: dict, category: str) -> Project:
    return Project(
        name=c["name"],
        source="coingecko",
        source_url=f"https://www.coingecko.com/en/coins/{c['id']}",
        kind="p2e",
        status="ongoing",
        confirmed=True,
        actions="遊戲已上線，代幣已在交易所流通（玩遊戲賺取代幣 / NFT）",
        tags=[category, f"${c.get('symbol', '').upper()}"],
        score=max(0.0, 60 - (c.get("market_cap_rank") or 999) / 20),
        extra={
            "symbol": (c.get("symbol") or "").upper(),
            "price_usd": c.get("current_price"),
            "market_cap_usd": c.get("market_cap"),
            "market_cap_rank": c.get("market_cap_rank"),
            "change_24h_pct": c.get("price_change_percentage_24h"),
            "image": c.get("image"),
        },
    )


def collect(cfg: dict) -> list[Project]:
    out: dict[str, Project] = {}
    for cat in cfg.get("categories", ["play-to-earn"]):
        try:
            rows = get(URL, params={"vs_currency": "usd", "category": cat, "order": "market_cap_desc",
                                    "per_page": cfg.get("max_items", 40), "page": 1},
                       polite_delay=1.5).json()
        except Exception as e:  # noqa: BLE001
            log.warning("CoinGecko %s 失敗: %s", cat, e)
            continue
        for c in rows if isinstance(rows, list) else []:
            out.setdefault(c["id"], to_project(c, cat))
    projects = sorted(out.values(), key=lambda p: -(p.extra.get("market_cap_usd") or 0))
    projects = projects[: cfg.get("max_items", 40)]
    log.info("CoinGecko：%d 個 P2E / GameFi 遊戲", len(projects))
    return projects
