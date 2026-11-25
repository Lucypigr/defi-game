import pytest

from airdrop_hunter.enrich import translate


@pytest.fixture(autouse=True)
def isolated_translation_cache(tmp_path, monkeypatch):
    """測試不能讀寫真正的 data/translations.json。"""
    monkeypatch.setattr(translate, "CACHE_PATH", tmp_path / "translations.json")
    monkeypatch.setattr(translate, "_cache", None)
