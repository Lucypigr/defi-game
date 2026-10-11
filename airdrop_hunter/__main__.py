"""命令列入口。

    python -m airdrop_hunter run            # 收集 + 分析 + 產生網頁（預設）
    python -m airdrop_hunter run --no-ai    # 不用 Claude，只用規則 + 免費翻譯
    python -m airdrop_hunter render         # 只用現有資料重新產生網頁
    python -m airdrop_hunter sources        # 測試每個資料來源抓到多少筆
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from . import notify, pipeline, render
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(prog="airdrop_hunter", description="自動搜尋 DeFi 空投與 P2E 遊戲")
    ap.add_argument("command", nargs="?", default="run", choices=["run", "render", "sources"])
    ap.add_argument("--config", default=str(ROOT / "config" / "sources.yaml"))
    ap.add_argument("--db", default=str(ROOT / "data" / "db.json"))
    ap.add_argument("--out", default=str(ROOT / "docs"))
    ap.add_argument("--no-ai", action="store_true", help="不使用 Claude（改用規則分析 + 免費翻譯）")
    ap.add_argument("--no-notify", action="store_true", help="不要發送 Telegram 推播")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpx2", "urllib3", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    store = Store(Path(args.db))

    if args.command == "sources":
        projects, posts = pipeline.collect(cfg)
        from collections import Counter
        for k, v in sorted(Counter(p.source for p in projects).items()):
            print(f"項目  {k:<20} {v}")
        for k, v in sorted(Counter(f"{p.source}:{p.channel}" for p in posts).items()):
            print(f"貼文  {k:<40} {v}")
        return

    if args.command == "run":
        result = pipeline.run(cfg, store, use_ai=False if args.no_ai else None)
        store.save()
        if not args.no_notify:
            notify.send_new(store, result["new_keys"], cfg.get("notify", {}))
    render.render(store, Path(args.out))
    print(f"完成 → {args.out}/index.html（共 {len(store.projects)} 個項目、{len(store.posts)} 則情報）")


if __name__ == "__main__":
    main()
