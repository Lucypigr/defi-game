import json
from types import SimpleNamespace

import pytest

from airdrop_hunter import pipeline, render
from airdrop_hunter.enrich import ai, rules
from airdrop_hunter.models import Post, Project
from airdrop_hunter.store import Store


@pytest.fixture(autouse=True)
def no_network_translate(monkeypatch):
    fake = lambda text, lang="zh-TW": f"譯:{text}" if text else ""   # noqa: E731
    monkeypatch.setattr(rules, "translate", fake)
    monkeypatch.setattr(rules, "translate_list", lambda items, lang="zh-TW": [fake(i) for i in items])


def _projects():
    return [
        Project(name="Foo Protocol", source="airdrops.io", source_url="https://airdrops.io/foo/", status="ongoing",
                actions="Join testnet, claim faucet", steps=["Join the testnet", "Claim faucet tokens"],
                links={"participate": "https://app.foo.xyz", "evil": "javascript:alert(1)"}, score=50),
        Project(name="Foo", source="dropstab", source_url="https://dropstab.com/coins/foo", status="upcoming",
                backers=[{"name": "Paradigm", "tier": 3}], funds_raised_usd=2e7, description="Foo is a DEX."),
        Project(name="Space Game", source="coingecko", kind="p2e", status="ongoing", score=20,
                extra={"price_usd": 1.2, "symbol": "SPG"}),
    ]


def _posts():
    return [Post(id="telegram:c/1", source="telegram", channel="c", url="https://t.me/c/1",
                 text="Foo testnet airdrop is live, do it now!", published="2099-01-01T00:00:00+00:00")]


def test_rules_pipeline_merges_and_renders(tmp_path):
    store = Store(tmp_path / "db.json")
    res = pipeline.run({"language": "zh-TW"}, store, use_ai=False, collect_fn=lambda cfg: (_projects(), _posts()))
    assert sorted(res["new_keys"]) == ["foo", "space-game"]   # "Foo Protocol" 與 "Foo" 合併

    foo = store.projects["foo"]
    assert {s["source"] for s in foo["sources"]} == {"airdrops.io", "dropstab"}
    assert foo["raw"]["status"] == "ongoing"
    a = foo["analysis"]
    assert a["backing_level"] == "top" and a["cost_type"] == "free" and a["difficulty"] == 1
    assert foo["related_posts"] == ["telegram:c/1"]
    assert store.projects["space-game"]["analysis"]["kind"] == "p2e"

    store.save()
    render.render(Store(tmp_path / "db.json"), tmp_path / "out")
    pub = json.loads((tmp_path / "out" / "data.json").read_text())
    links = [l["url"] for p in pub["projects"] for l in p["links"]]
    assert "javascript:alert(1)" not in links                      # 危險連結被過濾
    assert pub["posts"][0]["projects"] == ["foo"]
    md = (tmp_path / "out" / "AIRDROPS.md").read_text()
    assert "Foo Protocol" in md and "Space Game" in md

    # 第二次執行：內容沒變 → 不重新分析
    before = foo["analyzed_at"]
    pipeline.run({"language": "zh-TW"}, store, use_ai=False, collect_fn=lambda cfg: (_projects(), []))
    assert store.projects["foo"]["analyzed_at"] == before


def test_stale_projects_marked(tmp_path):
    store = Store(tmp_path / "db.json")
    pipeline.run({}, store, use_ai=False, collect_fn=lambda cfg: (_projects(), []))
    store.projects["space-game"]["last_seen"] = "2000-01-01T00:00:00+00:00"   # 很久沒看到 → 會被清除
    store.projects["foo"]["last_seen"] = "2099-01-01T00:00:00+00:00"
    pipeline.run({}, store, use_ai=False, collect_fn=lambda cfg: ([], []))
    assert "space-game" not in store.projects and "foo" in store.projects


def test_ai_pipeline_uses_extraction(tmp_path, monkeypatch):
    analysis = rules.analyze(_projects()[0], [])
    analysis.update(summary="AI 摘要", backing_level="notable")

    class FakeAnalyzer:
        model = "fake"
        calls = 0

        def __init__(self, cfg, lang):
            pass

        def extract_posts(self, posts):
            return [{"post_id": p["id"], "relevant": True, "title_zh": "標題", "summary_zh": "摘要",
                     "projects": [{"name": "Bar Network", "kind": "defi", "status": "ongoing",
                                   "confirmed": "unconfirmed", "actions": "互動", "chains": ["Base"],
                                   "backers": [], "links": ["https://bar.xyz"], "scam_risk": False},
                                  {"name": "Scammy", "kind": "defi", "status": "ongoing", "confirmed": "confirmed",
                                   "actions": "", "chains": [], "backers": [], "links": [], "scam_risk": True}]}
                    for p in posts]

        def analyze_project(self, p, related):
            return dict(analysis)

    monkeypatch.setattr(pipeline, "ClaudeAnalyzer", FakeAnalyzer)
    store = Store(tmp_path / "db.json")
    pipeline.run({"ai": {"max_projects_per_run": 1}}, store, use_ai=True,
                 collect_fn=lambda cfg: (_projects(), _posts()))
    assert "bar" in store.projects and "scammy" not in store.projects
    assert store.projects["bar"]["social_only"] is True
    by = sorted(r["analysis_by"] for r in store.projects.values())
    assert by.count("ai") == 1 and by.count("rules") == 2           # 超過上限的先用規則分析
    assert store.posts["telegram:c/1"]["zh"]["title_zh"] == "標題"


# ── Claude 回應解析 ──────────────────────────────────────────
def _resp(stop, *texts):
    return SimpleNamespace(stop_reason=stop, stop_details=None,
                           content=[SimpleNamespace(type="text", text=t) for t in texts])


def test_structured_handles_pause_and_refusal(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    an = ai.ClaudeAnalyzer({"web_search": True}, "zh-TW")
    calls = []

    def create(**kw):
        calls.append(kw)
        return _resp("pause_turn") if len(calls) == 1 else _resp("end_turn", '{"posts": ', "[]}")

    an.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert an.extract_posts([{"id": "1", "source": "x", "channel": "c", "text": "t"}]) == []
    assert len(calls) == 2 and calls[1]["messages"][-1]["role"] == "assistant"
    assert calls[0]["fallbacks"] == "default" and calls[0]["output_config"]["format"]["type"] == "json_schema"

    an.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: _resp("refusal"))))
    assert an.extract_posts([{"id": "1", "source": "x", "channel": "c", "text": "t"}]) == []


def test_analyze_project_filters_unsafe_links(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    an = ai.ClaudeAnalyzer({"web_search": False}, "zh-TW")
    out = {"official_links": [{"label": "官網", "url": "https://ok.xyz"}, {"label": "x", "url": "javascript:1"}]}
    an.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: _resp("end_turn", json.dumps(out)))))
    res = an.analyze_project(_projects()[0], [])
    assert res["official_links"] == [{"label": "官網", "url": "https://ok.xyz"}]
