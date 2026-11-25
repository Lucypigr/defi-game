"""來源沒有提供教學時，依項目類型產生中文「如何進行」步驟（規則模式使用，也提供給 AI 參考）。"""
from __future__ import annotations

from ..models import Project

# DefiLlama 類別 → 要做的主要動作
CATEGORY_ACTION = {
    "Dexs": "在平台上兌換 (Swap) 代幣，或提供流動性 (LP) 賺取手續費",
    "DEX Aggregator": "透過平台兌換代幣（它會自動幫你找最划算的路線）",
    "Lending": "存入資產賺取利息，或抵押後小額借款",
    "Derivatives": "用少量資金交易永續合約（注意槓桿風險，建議低倍數）",
    "Perps": "用少量資金交易永續合約（注意槓桿風險，建議低倍數）",
    "Options": "買賣期權或存入期權金庫",
    "Yield": "把資產存入收益金庫 (Vault) 賺取收益",
    "Yield Aggregator": "把資產存入收益金庫 (Vault)，讓協議自動幫你複利",
    "Farm": "提供流動性並質押 LP 代幣挖礦",
    "Leveraged Farming": "使用槓桿挖礦（風險較高，新手建議小額）",
    "Liquid Restaking": "質押 ETH 等資產換取再質押代幣 (LRT)，並可拿去其他 DeFi 協議使用",
    "Restaking": "把已質押的資產再質押，同時賺取多份收益與積分",
    "Liquid Staking": "質押資產換取流動性質押代幣",
    "CDP": "存入抵押品鑄造穩定幣，或使用該協議的穩定幣",
    "Stablecoin Issuer": "鑄造或持有該協議的穩定幣，並在合作協議中使用",
    "Synthetics": "鑄造或交易合成資產",
    "Prediction Market": "在預測市場上買賣事件結果",
    "Launchpad": "參與平台上的代幣發售或任務",
    "Gaming": "進入遊戲並開始遊玩",
    "NFT Marketplace": "在平台上買賣或掛單 NFT",
    "NFT Lending": "用 NFT 抵押借款或出借資金",
    "Bridge": "使用平台跨鏈轉移資產",
    "Insurance": "購買保險或提供承保資金",
    "Indexes": "買入指數型代幣或金庫",
    "RWA Lending": "存入資金參與現實資產 (RWA) 借貸",
}


def defillama_steps(p: Project) -> list[str]:
    cat = p.extra.get("category") or ""
    site = p.links.get("website", "")
    tw = p.links.get("twitter", "").rsplit("/", 1)[-1]
    chains = "、".join(p.chains[:3]) or "該協議支援的鏈"
    action = CATEGORY_ACTION.get(cat, "依照官網說明使用平台的主要功能（存款、交易或質押）")
    return [
        f"打開官網 {site}" + (f"（先確認網址和官方 X 帳號 @{tw} 公布的一致，避免進到釣魚網站）" if tw else "（請先確認是官方網址）"),
        f"準備錢包（MetaMask、Rabby 等），在 {chains} 鏈上準備要使用的資金與少量 Gas 手續費",
        f"連接錢包後，{action}",
        "持續使用一段時間（例如每週互動、維持部位不要馬上撤出），累積鏈上紀錄：回溯型空投通常看使用時間、金額和次數",
        "追蹤官方 X / Discord，留意積分活動 (Points)、快照 (Snapshot) 或代幣發行 (TGE) 公告",
    ]


def p2e_steps(p: Project) -> list[str]:
    site = p.links.get("website", "")
    sym = p.extra.get("symbol") or "遊戲代幣"
    chain = p.extra.get("chain") or (p.chains[0] if p.chains else "")
    return [
        (f"到官網 {site} " if site else f"到 CoinGecko 頁面 {p.source_url} 找官方網站，") + "了解玩法與支援平台（網頁 / 手機 / PC）",
        "建立或連接遊戲支援的錢包" + (f"（{chain} 鏈）" if chain else "") + "；部分遊戲也可以先用 Email 登入",
        "下載或開啟遊戲並註冊帳號，先玩免費模式熟悉規則",
        f"透過任務、對戰、排名、活動等賺取 ${sym} 代幣或 NFT 道具",
        "如果需要先買 NFT / 代幣才能開始賺，先算好回本時間再投入",
        f"把賺到的 ${sym} 轉到有上架的交易所（CoinGecko 頁面有列出）賣出換成 USDT",
    ]


def basic_steps(p: Project, actions_zh: str = "") -> list[str]:
    """其他來源只給了一句「要做什麼」時的通用教學。"""
    url = p.links.get("participate") or p.links.get("website") or p.source_url
    tw = p.links.get("twitter", "")
    return [
        f"打開參與頁面 {url}（先確認是官方網址，可對照官方 X 帳號{' ' + tw if tw else ''}）",
        "連接錢包（MetaMask、Rabby 等），或依頁面要求用 Email / X / Discord 帳號登入",
        f"完成頁面上的任務：{actions_zh}" if actions_zh else "依頁面說明完成任務（社群任務、互動、交易等）",
        "定期回來查看新任務與積分排名，並追蹤官方 X / Discord 的空投公告",
    ]


def generic_steps(p: Project, actions_zh: str = "") -> list[str]:
    if p.source == "defillama":
        return defillama_steps(p)
    if p.source == "coingecko":
        return p2e_steps(p)
    return basic_steps(p, actions_zh)
