"""資料模型。

Project：一個空投 / P2E 項目（來源網站的結構化資料，或 AI 從貼文中抽取出來的）。
Post：來自 X / Telegram / Reddit / 新聞的一則原始貼文（「最新情報」）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

KINDS = ("defi", "p2e")
STATUSES = ("ongoing", "upcoming", "potential", "claimable", "ended", "unknown")


@dataclass
class Project:
    name: str
    source: str                       # 例如 "airdrops.io"、"dropstab"、"telegram:airdrop"
    source_url: str = ""
    kind: str = "defi"                # defi = DeFi/加密空投、p2e = 邊玩邊賺遊戲
    status: str = "unknown"
    confirmed: bool | None = None     # 官方是否已確認有空投 / 代幣
    description: str = ""             # 原文說明
    actions: str = ""                 # 需要做的事（原文摘要）
    steps: list[str] = field(default_factory=list)
    chains: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    backers: list[dict] = field(default_factory=list)   # [{"name": ..., "tier": 1-3 或 None}]
    funds_raised_usd: float | None = None
    requirements: list[str] = field(default_factory=list)  # kyc / twitter / telegram / discord / email ...
    cost_hint: str = ""
    reward_hint: str = ""
    distribution_hint: str = ""
    start: str | None = None
    end: str | None = None
    links: dict[str, str] = field(default_factory=dict)   # website / participate / twitter / docs ...
    score: float = 0.0                # 熱度（各來源自己的分數，正規化到 0-100）
    published: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Post:
    id: str                           # 全域唯一，例如 "telegram:airdrop:12345"
    source: str                       # telegram / x / reddit / news
    channel: str                      # 頻道 / 帳號 / 子版 / 媒體名稱
    url: str
    text: str
    published: str | None = None
    title: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
