"""airdrops.io — 專門整理空投的網站，列表頁有狀態、熱度、需要做的動作，詳細頁有逐步教學。"""
from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..models import Project
from ..util import clean_text, get, iso, log

BASE = "https://airdrops.io"
REQ_ATTRS = ("kyc", "twitter", "telegram", "discord", "email-address", "phone", "facebook",
             "reddit", "medium", "youtube", "instagram", "linkedin", "bitcointalk")
GAME_CATEGORIES = {"gaming", "gamefi", "game", "play-to-earn", "p2e", "metaverse"}


def _outbound(a) -> str | None:
    """airdrops.io 的「前往」按鈕是 /visit/ 轉址（含推薦碼），改用真實網域。"""
    host = a.get("data-outbound-host") if a else None
    return f"https://{host}" if host else None


def parse_listing(html: str, page: str) -> list[Project]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Project] = []
    for art in soup.select("article.type-project"):
        h3 = art.select_one("h3")
        link = art.select_one("a.card-link-overlay") or (h3.find_parent("a") if h3 else None)
        if not h3 or not link:
            continue
        classes = set(art.get("class", []))
        cats = [c.removeprefix("categories-") for c in classes if c.startswith("categories-")]
        status = next((s for s in ("ongoing", "upcoming", "ended") if s in classes), "unknown")
        if page == "speculative" and status != "ended":
            status = "potential"
        actions = art.select_one(".front-drop-list span")
        reqs = [r for r in REQ_ATTRS if art.get(f"data-{r}-required") == "1"]
        published = None
        if (p := art.get("data-published")) and len(p) == 14:
            published = iso(datetime.strptime(p, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc))
        temp = float(art.get("data-temperature") or 0)
        out.append(Project(
            name=h3.get_text(strip=True),
            source="airdrops.io",
            source_url=link["href"],
            kind="p2e" if GAME_CATEGORIES & set(cats) else "defi",
            status=status,
            confirmed=True if "confirmed" in classes else (False if page == "speculative" else None),
            actions=actions.get_text(" ", strip=True) if actions else "",
            tags=sorted(cats),
            requirements=["email" if r == "email-address" else r for r in reqs],
            links={k: v for k, v in {"participate": _outbound(art.select_one(".air-buttons a"))}.items() if v},
            score=min(100.0, temp / 2),   # 熱度 °（0~200+）→ 0~100
            published=published,
            extra={"airdrops_io_page": page},
        ))
    return out


def parse_detail(html: str, p: Project) -> None:
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.select(".lifi-bridge, .guide-cta-wrap, button, script, style, figure"):
        junk.decompose()   # 移除跨鏈橋小工具、按鈕等雜訊
    if info := soup.select_one(".airdrop-info"):
        for li in info.select("li"):
            t = li.get_text(" ", strip=True)
            low = t.lower()
            if low.startswith("chain:"):
                p.chains = [c.strip() for c in t.split(":", 1)[1].split(",") if c.strip()]
            elif "unconfirmed" in low:
                p.confirmed = False
            elif "confirmed" in low:
                p.confirmed = True
            elif "total value" in low or "value" in low:
                p.reward_hint = t
            if (a := li.select_one("a")) and (u := _outbound(a)):
                p.links.setdefault("participate", u)
    if feat := soup.select_one(".drop-features"):
        # 只取最內層的段落（頁面有巢狀 <p>，否則文字會重複）
        paras = [e.get_text(" ", strip=True) for e in feat.find_all(["p", "li"]) if not e.find(["p", "li", "h2", "h3"])]
        paras = [x for x in paras if x and not (x.lower().startswith("what is") and x.endswith("?"))]
        p.description = clean_text("\n".join(paras), 2500)
    if guide := soup.select_one(".airdrop-guide"):
        steps = []
        for h in guide.find_all(["h3", "h4"]):
            title = h.get_text(" ", strip=True)
            if not title.lower().startswith("step"):
                continue
            body = []
            for sib in h.find_next_siblings():
                if sib.name in ("h2", "h3", "h4"):
                    break
                body.append(sib.get_text(" ", strip=True))
            steps.append(clean_text(f"{title}: {' '.join(body)}", 400))
        if not steps:  # 版面不同時，退而求其次保留整段文字
            text = clean_text(guide.get_text("\n", strip=True), 2500)
            steps = [line for line in text.split("\n") if line][:20]
        p.steps = steps[:15]
    for a in soup.select(".airdrop-list a"):
        href = a.get("href", "")
        if "x.com/" in href or "twitter.com/" in href:
            p.links.setdefault("twitter", href)
        elif "t.me/" in href:
            p.links.setdefault("telegram", href)
        elif "discord" in href:
            p.links.setdefault("discord", href)
        elif u := _outbound(a):
            p.links.setdefault("website", u)


def collect(cfg: dict) -> list[Project]:
    seen: dict[str, Project] = {}
    for page in cfg.get("pages", ["latest"]):
        try:
            items = parse_listing(get(f"{BASE}/{page}/").text, page)
        except Exception as e:  # noqa: BLE001 — 單一來源失敗不影響其他來源
            log.warning("airdrops.io %s 失敗: %s", page, e)
            continue
        for it in items:
            seen.setdefault(it.source_url, it)
    projects = list(seen.values())
    if cfg.get("fetch_details", True):
        for p in sorted(projects, key=lambda x: -x.score)[: cfg.get("max_details", 40)]:
            try:
                parse_detail(get(p.source_url, polite_delay=0.5).text, p)
            except Exception as e:  # noqa: BLE001
                log.warning("airdrops.io 詳細頁 %s 失敗: %s", p.source_url, e)
    log.info("airdrops.io：%d 個項目", len(projects))
    return projects
