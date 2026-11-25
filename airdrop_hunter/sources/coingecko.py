"""CoinGecko — 已經有代幣、正在營運中的熱門 P2E / GameFi 遊戲（含市值與 24h 漲跌）。"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from ..models import Project
from ..util import clean_text, get, log, now_utc, parse_iso, iso

URL = "https://api.coingecko.com/api/v3/coins/markets"
META_URL = "https://api.coingecko.com/api/v3/coins/{id}"
META_CACHE = Path(__file__).resolve().parents[2] / "data" / "coingecko_meta.json"
META_MAX_AGE_DAYS = 30


def _load_meta() -> dict:
    try:
        return json.loads(META_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fetch_meta(coin_id: str) -> dict:
    d = get(META_URL.format(id=coin_id), polite_delay=2.5, params={
        "localization": "false", "tickers": "false", "market_data": "false",
        "community_data": "false", "developer_data": "false"}).json()
    links = d.get("links") or {}
    home = next((u for u in links.get("homepage") or [] if u), "")
    return {
        "website": home,
        "twitter": f"https://x.com/{links['twitter_screen_name']}" if links.get("twitter_screen_name") else "",
        "telegram": f"https://t.me/{links['telegram_channel_identifier']}" if links.get("telegram_channel_identifier") else "",
        "discord": next((u for u in links.get("chat_url") or [] if "discord" in u), ""),
        "description": clean_text((d.get("description") or {}).get("en"), 1500),
        "chain": d.get("asset_platform_id") or "",
        "fetched_at": iso(now_utc()),
    }


def apply_meta(p: Project, meta: dict) -> None:
    for k in ("website", "twitter", "telegram", "discord"):
        if meta.get(k):
            p.links.setdefault(k, meta[k])
    if meta.get("description"):
        p.description = meta["description"]
    if meta.get("chain"):
        p.extra["chain"] = meta["chain"]
        p.chains = [meta["chain"]]


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

    # 每次最多補抓幾個遊戲的官網 / 介紹（免費 API 有速率限制），結果快取起來
    meta = _load_meta()
    budget = cfg.get("max_meta_per_run", 8)
    for p in projects:
        cid = p.source_url.rsplit("/", 1)[-1]
        cached = meta.get(cid)
        old = cached and (parse_iso(cached.get("fetched_at")) or now_utc()) < now_utc() - timedelta(days=META_MAX_AGE_DAYS)
        if (not cached or old) and budget > 0:
            budget -= 1
            try:
                meta[cid] = cached = fetch_meta(cid)
            except Exception as e:  # noqa: BLE001
                log.warning("CoinGecko 詳細資料 %s 失敗（多半是限流，本次先停止，下次再補）: %s", cid, e)
                budget = 0
        if cached:
            apply_meta(p, cached)
    try:
        META_CACHE.parent.mkdir(parents=True, exist_ok=True)
        META_CACHE.write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    except OSError as e:
        log.warning("無法寫入 CoinGecko 快取: %s", e)
    log.info("CoinGecko：%d 個 P2E / GameFi 遊戲", len(projects))
    return projects
