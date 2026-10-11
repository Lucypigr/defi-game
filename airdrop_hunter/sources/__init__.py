"""所有資料來源。PROJECT_SOURCES 產生結構化項目，POST_SOURCES 產生社群 / 新聞貼文。"""
from . import airdrops_io, coingecko, defillama, dropstab, feeds, telegram, x_api

# (config 區塊名稱, 收集函式)
PROJECT_SOURCES = [
    ("airdrops_io", airdrops_io.collect),
    ("dropstab", dropstab.collect),
    ("defillama", defillama.collect),
    ("coingecko_p2e", coingecko.collect),
]

POST_SOURCES = [
    ("telegram", telegram.collect),
    ("x", x_api.collect),
    ("reddit", feeds.collect_reddit),
    ("news", feeds.collect_news),
]
