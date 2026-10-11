"""資料庫（data/db.json）：保存所有項目、分析結果與貼文，讓每次執行只需處理「新的或有變動」的部分。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .util import iso, now_utc

DB_VERSION = 1


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"version": DB_VERSION, "updated_at": None, "projects": {}, "posts": {}}
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    @property
    def projects(self) -> dict[str, dict]:
        return self.data["projects"]

    @property
    def posts(self) -> dict[str, dict]:
        return self.data["posts"]

    def save(self) -> None:
        self.data["updated_at"] = iso(now_utc())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
