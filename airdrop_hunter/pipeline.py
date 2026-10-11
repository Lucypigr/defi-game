"""主流程：收集 → 抽取 → 合併去重 → 分析（AI 或規則）→ 標記過期 → 存檔。"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import timedelta

from .enrich import rules
from .enrich.ai import ClaudeAnalyzer
from .models import Post, Project
from .sources import POST_SOURCES, PROJECT_SOURCES
from .store import Store
from .util import content_hash, iso, log, now_utc, parse_iso, safe_url, slugify

STATUS_RANK = {"claimable": 5, "ongoing": 4, "upcoming": 3, "potential": 2, "unknown": 1, "ended": 0}
STRUCTURED_SOURCES = {"airdrops.io", "dropstab", "defillama", "coingecko"}
POST_KEEP_DAYS = 14
RELEVANT = re.compile(r"airdrop|testnet|points?\b|claim|tge|snapshot|whitelist|waitlist|quest|campaign|"
                      r"reward|play.to.earn|p2e|gamefi|game|mainnet|launch|空投|撸|擼|任務|測試網|测试网", re.I)
ENDED_KEEP_DAYS = 60


# ── 收集 ──────────────────────────────────────────────────────
def collect(cfg: dict) -> tuple[list[Project], list[Post]]:
    projects: list[Project] = []
    posts: list[Post] = []
    for key, fn in PROJECT_SOURCES:
        if cfg.get(key, {}).get("enabled", True):
            projects += fn(cfg.get(key, {}))
    for key, fn in POST_SOURCES:
        if cfg.get(key, {}).get("enabled", True):
            posts += fn(cfg.get(key, {}))
    return projects, posts


# ── 合併同一項目的多個來源 ─────────────────────────────────────
def merge(a: Project, b: Project) -> Project:
    if len(b.description) > len(a.description):
        a.description = b.description
    if len(b.steps) > len(a.steps):
        a.steps = b.steps
    if not a.actions:
        a.actions = b.actions
    if STATUS_RANK.get(b.status, 0) > STATUS_RANK.get(a.status, 0):
        a.status = b.status
    if b.confirmed or a.confirmed is None:
        a.confirmed = b.confirmed if b.confirmed is not None else a.confirmed
    if b.kind == "p2e":
        a.kind = "p2e"
    a.chains = list(dict.fromkeys(a.chains + b.chains))
    a.tags = list(dict.fromkeys(a.tags + b.tags))
    a.requirements = list(dict.fromkeys(a.requirements + b.requirements))
    names = {x["name"].lower() for x in a.backers}
    a.backers += [x for x in b.backers if x["name"].lower() not in names]
    a.funds_raised_usd = max(filter(None, [a.funds_raised_usd, b.funds_raised_usd]), default=None)
    for f in ("cost_hint", "reward_hint", "distribution_hint", "start", "end", "published"):
        if not getattr(a, f) and getattr(b, f):
            setattr(a, f, getattr(b, f))
    for k, v in b.links.items():
        a.links.setdefault(k, v)
    a.extra = {**b.extra, **a.extra}
    a.score = max(a.score, b.score)
    return a


def project_from_extraction(e: dict, post: dict) -> Project:
    links = {}
    for u in e.get("links", []):
        if not safe_url(u):
            continue
        key = ("twitter" if re.search(r"//(x|twitter)\.com/", u) else "telegram" if "t.me/" in u
               else "discord" if "discord" in u else "website")
        links.setdefault(key, u)
    return Project(
        name=e["name"].strip(),
        source=f"{post['source']}:{post['channel']}",
        source_url=post["url"],
        kind=e.get("kind", "defi"),
        status=e.get("status", "unknown"),
        confirmed={"confirmed": True, "unconfirmed": False}.get(e.get("confirmed")),
        description=post["text"][:1200],
        actions=e.get("actions", ""),
        chains=e.get("chains", []),
        backers=[{"name": b, "tier": None} for b in e.get("backers", []) if b],
        links=links,
        score=10.0,
        published=post.get("published"),
    )


def _analysis_input_hash(raw: dict) -> str:
    return content_hash(raw["name"], raw["description"], raw["steps"], raw["actions"], raw["status"],
                        raw["confirmed"], [b["name"] for b in raw["backers"]], raw["end"], raw["reward_hint"])


def _project_from_dict(d: dict) -> Project:
    names = {f.name for f in fields(Project)}
    return Project(**{k: v for k, v in d.items() if k in names})


# ── 主流程 ────────────────────────────────────────────────────
def run(cfg: dict, store: Store, *, use_ai: bool | None = None, collect_fn=collect) -> dict:
    lang = cfg.get("language", "zh-TW")
    ai_cfg = cfg.get("ai", {})
    if use_ai is None:
        use_ai = ClaudeAnalyzer.available()
    analyzer = ClaudeAnalyzer(ai_cfg, lang) if use_ai else None
    log.info("分析模式：%s", f"Claude AI（{analyzer.model}）" if analyzer else "規則 + 免費翻譯（未設定 ANTHROPIC_API_KEY）")

    now = now_utc()
    now_s = iso(now)
    raw_projects, raw_posts = collect_fn(cfg)

    # 1) 新貼文：翻譯 / 抽取項目
    new_posts = [p.to_dict() for p in raw_posts if p.id not in store.posts]
    new_posts.sort(key=lambda p: p.get("published") or "", reverse=True)
    social_projects: list[Project] = []
    if analyzer:
        todo = new_posts[: ai_cfg.get("max_posts_per_run", 60)]
        batches = [todo[i:i + 12] for i in range(0, len(todo), 12)]
        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(analyzer.extract_posts, batches))
        by_id = {r["post_id"]: r for res in results for r in res}
        for p in todo:
            r = by_id.get(p["id"])
            if not r:
                continue        # 這次沒處理到，下次再試
            p["zh"] = {"title_zh": r["title_zh"], "summary_zh": r["summary_zh"]}
            p["relevant"] = r["relevant"]
            p["processed_by"] = "ai"
            p["mentions"] = []
            for e in r["projects"] if r["relevant"] else []:
                if e.get("scam_risk") or not e.get("name"):
                    continue
                social_projects.append(project_from_extraction(e, p))
                p["mentions"].append(slugify(e["name"]))
            p["first_seen"] = now_s
            store.posts[p["id"]] = p
    else:
        for p in new_posts[:80]:
            p["zh"] = rules.summarize_post(p, lang)
            p["relevant"] = bool(RELEVANT.search(f"{p.get('title', '')} {p['text']}"))
            p["processed_by"] = "rules"
            p["mentions"] = []
            p["first_seen"] = now_s
            store.posts[p["id"]] = p

    # 2) 合併所有來源的項目
    merged: dict[str, Project] = {}
    sources_of: dict[str, list[dict]] = {}
    for p in raw_projects + social_projects:
        key = slugify(p.name)
        sources_of.setdefault(key, []).append({"source": p.source, "url": p.source_url})
        merged[key] = merge(merged[key], p) if key in merged else p

    new_keys = []
    for key, p in merged.items():
        rec = store.projects.get(key)
        srcs = list({s["source"]: s for s in sources_of[key]}.values())
        if rec is None:
            rec = store.projects[key] = {"key": key, "first_seen": now_s, "sources": []}
            new_keys.append(key)
        elif rec.get("raw") and not (set(s["source"] for s in srcs) & STRUCTURED_SOURCES):
            # 只有社群提到 → 與舊資料合併，避免覆蓋掉結構化來源的內容
            p = merge(_project_from_dict(rec["raw"]), p)
        known = {s["source"]: s for s in rec["sources"]}
        for s in srcs:
            known[s["source"]] = {**s, "last_seen": now_s}
        rec["sources"] = list(known.values())
        rec["raw"] = p.to_dict()
        rec["last_seen"] = now_s
        rec["stale"] = False
        rec["social_only"] = not any(s["source"] in STRUCTURED_SOURCES for s in rec["sources"])
        rec["mention_count"] = len(rec["sources"])

    # 把貼文連到項目（名稱比對）
    _link_posts(store)

    # 3) 分析（只處理新的 / 內容有變動的 / 之前是規則分析而現在有 AI 的）
    todo = []
    for key, rec in store.projects.items():
        if "raw" not in rec or rec.get("stale"):
            continue
        h = _analysis_input_hash(rec["raw"])
        if rec.get("analysis_hash") != h or (analyzer and rec.get("analysis_by") != "ai"):
            todo.append((key, rec, h))
    todo.sort(key=lambda t: (-len(t[1]["sources"]), -t[1]["raw"]["score"]))

    ai_todo = todo[: ai_cfg.get("max_projects_per_run", 15)] if analyzer else []
    if ai_todo:
        def work(t):
            key, rec, h = t
            related = [store.posts[i] for i in rec.get("related_posts", [])[:5] if i in store.posts]
            return t, analyzer.analyze_project(_project_from_dict(rec["raw"]), related)
        with ThreadPoolExecutor(max_workers=4) as ex:
            for (key, rec, h), result in ex.map(work, ai_todo):
                if result:
                    rec.update(analysis=result, analysis_by="ai", analysis_hash=h, analyzed_at=now_s)
    for key, rec, h in todo:
        if rec.get("analysis_hash") == h and rec.get("analysis_by") == "ai":
            continue
        if rec.get("analysis") and rec.get("analysis_by") == "ai":
            continue        # 保留舊的 AI 分析，等下次額度再更新
        related = [store.posts[i] for i in rec.get("related_posts", [])[:5] if i in store.posts]
        rec.update(analysis=rules.analyze(_project_from_dict(rec["raw"]), related, lang),
                   analysis_by="rules", analysis_hash=h, analyzed_at=now_s)

    # 4) 過期與清理
    stale_cutoff = now - timedelta(days=cfg.get("stale_after_days", 21))
    social_cutoff = now - timedelta(days=max(7, cfg.get("stale_after_days", 21) // 2))
    drop_cutoff = now - timedelta(days=ENDED_KEEP_DAYS)
    for key in list(store.projects):
        rec = store.projects[key]
        seen = parse_iso(rec.get("last_seen")) or now
        if seen < drop_cutoff or "raw" not in rec:
            del store.projects[key]
            continue
        rec["stale"] = seen < (social_cutoff if rec.get("social_only") else stale_cutoff)
    post_cutoff = now - timedelta(days=POST_KEEP_DAYS)
    for pid in list(store.posts):
        when = parse_iso(store.posts[pid].get("published") or store.posts[pid].get("first_seen"))
        if when and when < post_cutoff:
            del store.posts[pid]

    store.data["last_run"] = {
        "at": now_s, "mode": "ai" if analyzer else "rules",
        "collected_projects": len(raw_projects), "collected_posts": len(raw_posts),
        "new_projects": len(new_keys), "new_posts": len(new_posts),
        "ai_calls": analyzer.calls if analyzer else 0,
    }
    log.info("完成：收集 %d 項目 / %d 貼文，新項目 %d，新貼文 %d",
             len(raw_projects), len(raw_posts), len(new_keys), len(new_posts))
    return {"new_keys": new_keys}


_GENERIC = re.compile(r"\s+(protocol|network|finance|labs?|exchange|app|xyz|io|dex|chain|game|games)$", re.I)


def _name_pattern(name: str) -> re.Pattern | None:
    """名稱比對：完整名稱，或去掉 Protocol / Network 等字尾的短名稱。短名稱需大小寫相符以減少誤判。"""
    alts = []
    for n in {name.strip(), _GENERIC.sub("", name.strip())}:
        if len(n) >= 5:
            alts.append("(?i:" + re.escape(n) + ")")
        elif len(n) >= 3:
            alts.append(re.escape(n))
    return re.compile(r"(?<![\w$])\$?(?:" + "|".join(alts) + r")(?!\w)") if alts else None


def _link_posts(store: Store) -> None:
    patterns = {k: rx for k, rec in store.projects.items() if "raw" in rec
                if (rx := _name_pattern(rec["raw"]["name"]))}
    for rec in store.projects.values():
        rec["related_posts"] = []
    for pid, post in sorted(store.posts.items(), key=lambda kv: kv[1].get("published") or "", reverse=True):
        text = f"{post.get('title', '')} {post.get('text', '')}"
        keys = set(post.get("mentions", [])) | {k for k, rx in patterns.items() if rx.search(text)}
        post["projects"] = sorted(k for k in keys if k in store.projects)
        for k in post["projects"]:
            store.projects[k]["related_posts"].append(pid)
