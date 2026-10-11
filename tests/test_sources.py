import json

from airdrop_hunter.sources import airdrops_io, defillama, dropstab, feeds, telegram

LISTING = """
<article class="post-1 page type-page"><h1>Latest</h1></article>
<article class="grid-33 ongoing confirmed post-2 project type-project categories-dex categories-gaming"
  data-kyc-required="1" data-twitter-required="1" data-published="20261008123642" data-temperature="132">
  <h3>Moon Game</h3>
  <ul class="front-drop-list"><li>Actions: <span>Play, Refer Users</span></li></ul>
  <div class="air-buttons"><a href="/visit/x/?k=1" data-outbound-host="app.moongame.io">CLAIM</a></div>
  <a class="card-link-overlay" href="https://airdrops.io/moon-game/"></a>
</article>
<article class="grid-33 ongoing post-3 project type-project categories-perpetual">
  <h3>Perp Dex</h3><a class="card-link-overlay" href="https://airdrops.io/perp-dex/"></a>
</article>
"""

DETAIL = """
<body class="single active-footer-widgets-3">
<div class="airdrop-info"><ul>
  <li><a data-outbound-host="testnet.perp.xyz" href="/visit/1">Join testnet</a></li>
  <li>Airdrop unconfirmed</li><li>Chain: Arbitrum, Base</li></ul></div>
<div class="drop-features"><p><h2>What is Perp Dex?</h2><p>Perp Dex is a <a href="#">perpetual</a> exchange.</p></p></div>
<div class="airdrop-guide">
  <h3>Step 1: Join the waitlist</h3><div class="step-body">Connect your wallet.
     <div class="lifi-bridge">Bridge funds Swap and bridge across 30+ chains</div></div>
  <h3>Step 2: Trade</h3><p>Open a position.</p>
  <h3>Frequently Asked Questions</h3><p>No token yet.</p>
</div>
<div class="airdrop-list"><a href="https://x.com/perpdex">x</a><a data-outbound-host="perp.xyz" href="/visit/2">site</a></div>
</body>
"""


def test_airdrops_io_listing_and_detail():
    items = airdrops_io.parse_listing(LISTING, "latest")
    assert [p.name for p in items] == ["Moon Game", "Perp Dex"]
    game = items[0]
    assert game.kind == "p2e" and game.status == "ongoing" and game.confirmed is True
    assert game.requirements == ["kyc", "twitter"]
    assert game.links["participate"] == "https://app.moongame.io"   # 不使用含推薦碼的 /visit/ 轉址
    assert game.published.startswith("2026-10-08")

    perp = items[1]
    airdrops_io.parse_detail(DETAIL, perp)
    assert perp.confirmed is False
    assert perp.chains == ["Arbitrum", "Base"]
    assert perp.description == "Perp Dex is a perpetual exchange."
    assert len(perp.steps) == 2 and "Bridge" not in perp.steps[0]
    assert perp.links["twitter"] == "https://x.com/perpdex"
    assert perp.links["website"] == "https://perp.xyz"
    assert perp.links["participate"] == "https://testnet.perp.xyz"


def test_airdrops_io_speculative_is_potential():
    items = airdrops_io.parse_listing(LISTING, "speculative")
    assert all(p.status == "potential" for p in items)


def _flight(obj: dict) -> str:
    payload = 'x:' + json.dumps([{"activities": [obj]}])
    return f'<script>self.__next_f.push([1,{json.dumps(payload)}])</script>'


def test_dropstab_extract_and_convert():
    act = {
        "id": 7, "isDraft": False, "status": "ACTIVE", "isOutdated": False,
        "titleProject": {"slug": "termix", "name": "TermiX", "fundsRaised": 1_000_000,
                         "investors": [{"name": "YZi Labs (prev Binance Labs)", "rating": 3}]},
        "activityType": {"name": "Point Farming"}, "tags": [{"name": "Point Farming"}],
        "ecosystem": [{"displayName": "AI Agents"}],
        "about": "Raised **$1M**", "howToParticipate": "### Setup\n1. Open [site](https://a.b|target=_blank).\n2. Earn points",
        "participationLink": "https://a.b", "links": ["https://x.com/termix"], "activityFrom": 1788048000000,
    }
    acts = dropstab.extract_activities(_flight(act))
    assert len(acts) == 1
    p = dropstab.to_project(acts[0])
    assert p.name == "TermiX" and p.status == "ongoing"
    assert p.backers[0]["name"].startswith("YZi")
    assert p.steps == ["Open site (https://a.b).", "Earn points"]
    assert p.description == "Raised $1M"
    assert p.links["twitter"] == "https://x.com/termix"


TG = """
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="chan/12">
 <div class="tgme_widget_message_text">New airdrop: Foo testnet is live!<br>Join here <a href="https://foo.xyz">foo</a> and earn points.</div>
 <a class="tgme_widget_message_date" href="https://t.me/chan/12"><time datetime="2099-01-01T00:00:00+00:00"></time></a>
</div></div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="chan/13">
 <div class="tgme_widget_message_text">gm</div>
 <a class="tgme_widget_message_date" href="https://t.me/chan/13"></a></div></div>
"""


def test_telegram_parse():
    posts = telegram.parse_channel(TG, "chan")
    assert len(posts) == 1                     # 太短的訊息被略過
    assert posts[0].id == "telegram:chan/12"
    assert "\n" in posts[0].text
    assert posts[0].extra["links"] == ["https://foo.xyz"]


def test_defillama_select_tokenless_only():
    protos = [
        {"name": "NoToken Dex", "slug": "nt", "category": "Dexs", "tvl": 9e7, "symbol": "-", "listedAt": None,
         "twitter": "nt", "url": "https://nt.xyz", "chains": ["Base"]},
        {"name": "Has Token", "category": "Dexs", "tvl": 9e8, "symbol": "HT", "gecko_id": "ht"},
        {"name": "Big CEX", "category": "CEX", "tvl": 9e9, "symbol": "-"},
        {"name": "Small", "category": "Dexs", "tvl": 1e6, "symbol": "-"},
    ]
    out = defillama.select(protos, {"min_tvl_usd": 3e7, "listed_within_days": 900})
    assert [p.name for p in out] == ["NoToken Dex"]
    assert out[0].status == "potential" and out[0].links["twitter"] == "https://x.com/nt"


RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Big airdrop announced</title><link>https://n.com/a</link><pubDate>Mon, 01 Jan 2099 00:00:00 GMT</pubDate><description>Claim now</description></item>
<item><title>Bitcoin price today</title><link>https://n.com/b</link><pubDate>Mon, 01 Jan 2099 00:00:00 GMT</pubDate><description>Up</description></item>
</channel></rss>"""


def test_feed_keyword_filter():
    posts = feeds.parse_feed(RSS, source="news", channel="N", keywords=["airdrop"])
    assert [p.url for p in posts] == ["https://n.com/a"]
