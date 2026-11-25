"""DropsTab activities — 空投 / 積分 / 測試網活動，附投資機構、募資金額、參與步驟。

頁面是 Next.js，資料藏在 self.__next_f.push(...) 的 flight data 裡，這裡直接解析 JSON。
"""
from __future__ import annotations

import json
import re

from ..models import Project
from ..util import clean_text, from_ms, get, iso, log, strip_markdown

URL = "https://dropstab.com/activities"
_PUSH = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
_START = re.compile(r'\{"id":\s*\d+,\s*"isDraft"')

STATUS_MAP = {"ACTIVE": "ongoing", "UPCOMING": "upcoming", "CLAIM": "claimable",
              "ENDED": "ended", "FINISHED": "ended", "POTENTIAL": "potential"}


def extract_activities(html: str) -> list[dict]:
    text = "".join(json.loads(f'"{c}"') for c in _PUSH.findall(html))
    dec = json.JSONDecoder()
    out, seen = [], set()
    for m in _START.finditer(text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if obj.get("id") not in seen and obj.get("titleProject"):
            seen.add(obj["id"])
            for k in ("howToParticipate", "about"):   # 長文字放在別段，用 "$55" 這種代號引用
                if isinstance(obj.get(k), str) and _REF.fullmatch(obj[k]):
                    obj[k] = _resolve_text(text, obj[k][1:])
            out.append(obj)
    return out


_REF = re.compile(r"\$[0-9a-f]+")


def _resolve_text(text: str, ref: str) -> str:
    """Next.js flight 的文字區塊格式：<代號>:T<位元組長度(16進位)>,<內容>"""
    # 區塊之間不一定有換行（上一段文字結束就緊接下一段），所以只要求前面不是 16 進位字元
    m = re.search(r"(?<![0-9a-f])" + re.escape(ref) + r":T([0-9a-f]+),", text)
    if not m:
        return ""
    size = int(m.group(1), 16)
    return text[m.end():m.end() + size * 2].encode("utf-8")[:size].decode("utf-8", "ignore")


def parse_how_to(md: str) -> tuple[list[str], list[str]]:
    """把 Markdown 教學拆成「步驟」（有編號的項目）和「補充說明」（其他條列 / 段落）。"""
    steps, notes, section = [], [], ""
    for line in md.split("\n"):
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("#"):
            section = strip_markdown(raw.lstrip("#").strip())
            continue
        text = strip_markdown(re.sub(r"^\d+[.)]\s*", "", raw))
        if not text:
            continue
        if re.match(r"^\d+[.)]\s", raw):
            # 每個小節的第一步加上小節名稱，例如「【Join Testnet】Go to ...」
            if section and (not steps or not steps[-1].startswith(f"【{section}】")) and \
                    not any(s.startswith(f"【{section}】") for s in steps):
                text = f"【{section}】{text}"
            steps.append(text)
        else:
            notes.append(text)
    if len(steps) < 2:      # 沒有編號清單時，退而用全部條列
        steps, notes = steps + notes, []
    return steps[:15], notes


def to_project(a: dict) -> Project:
    tp = a.get("titleProject") or {}
    atype = (a.get("activityType") or {}).get("name", "")
    tags = [t.get("name", "") for t in a.get("tags") or []]
    eco = [e.get("displayName", "") for e in a.get("ecosystem") or []]
    is_game = "gaming" in atype.lower() or any("gam" in t.lower() for t in tags + eco)
    backers = [{"name": i.get("name"), "tier": i.get("rating"), "type": i.get("ventureType")}
               for i in tp.get("investors") or [] if i.get("name")]
    steps, notes = parse_how_to(a.get("howToParticipate") or "")
    links = {"participate": a.get("participationLink")}
    for u in a.get("links") or []:
        key = "twitter" if ("x.com/" in u or "twitter.com/" in u) else "docs" if "docs" in u else "website"
        links.setdefault(key, u)
    reward = a.get("reward") or []
    reward_hint = ", ".join(r.get("name", str(r)) if isinstance(r, dict) else str(r) for r in reward)
    if a.get("rewardAmount"):
        reward_hint = f"{reward_hint} {a['rewardAmount']}".strip()
    start, end = from_ms(a.get("activityFrom")), from_ms(a.get("activityTo"))
    return Project(
        name=tp.get("name") or "?",
        source="dropstab",
        source_url=f"https://dropstab.com/coins/{tp['slug']}" if tp.get("slug") else URL,
        kind="p2e" if is_game else "defi",
        status=STATUS_MAP.get(a.get("status", ""), "unknown"),
        confirmed=True if atype == "AirDrop" or a.get("status") == "CLAIM" else None,
        description=clean_text(strip_markdown(a.get("about") or ""), 2500),
        actions=atype,
        steps=steps[:15],
        chains=eco,
        tags=sorted(set(tags + [atype])),
        backers=backers,
        funds_raised_usd=tp.get("fundsRaised"),
        cost_hint=f"price: {a['price']}" if a.get("price") else "",
        reward_hint=reward_hint,
        distribution_hint=str(a.get("rewardDistribution") or a.get("rewardDistributionApprox") or ""),
        start=iso(start),
        end=iso(end) if end else a.get("activityToCustom"),
        links={k: v for k, v in links.items() if v},
        score=min(100.0, (tp.get("tweetscoutScore") or 0) / 10 + (20 if a.get("isFeatured") else 0)),
        published=iso(from_ms(a.get("createdAt"))),
        extra={"dropstab_id": a.get("id"), "outdated": a.get("isOutdated"), "notes": notes[:10]},
    )


def collect(cfg: dict) -> list[Project]:
    try:
        acts = extract_activities(get(URL).text)
    except Exception as e:  # noqa: BLE001
        log.warning("DropsTab 失敗: %s", e)
        return []
    projects = []
    for a in acts:
        if a.get("isDraft"):
            continue
        p = to_project(a)
        if a.get("isOutdated"):   # 超過約 3 個月沒更新的資料：保留，但降低排序（AI 分析時會再查證）
            p.score = max(0.0, p.score - 15)
        projects.append(p)
    log.info("DropsTab：%d 個活動", len(projects))
    return projects
