# 🪂 空投雷達 — 自動搜尋 DeFi 空投 & P2E 遊戲

自動從各大網站、Telegram、X (Twitter)、Reddit 與新聞媒體收集**正在進行中**與**即將到來**的加密貨幣空投及 P2E（邊玩邊賺）遊戲，
**翻譯成中文**，並分析每個項目：

| 欄位 | 說明 |
|---|---|
| 項目介紹 | 這個項目在做什麼、為什麼可能空投 |
| 背後支撐 | 是否有大型公司 / 頂級 VC（a16z、Paradigm、幣安 YZi Labs、Coinbase…）投資、募資金額 |
| 完成難易度 | ★ ~ ★★★★★，以及需要投入多少時間（一次性 / 每日 / 每週） |
| 是否免費 | 免費 / 只需 Gas / 需投入資金 / 需付費 |
| 如何進行 | 一步一步的中文教學 |
| 完成後如何發放 | 積分換代幣、TGE 空投到錢包、需手動 Claim、NFT… |
| 狀態 | 進行中 / 即將開始 / 潛在（官方未確認）/ 可領取 / 已結束 |
| 風險 | 是否官方確認、本金風險、疑似詐騙警示 |
| 超連結 | 官網、參與連結、X、Telegram、Discord、文件、資料來源、相關貼文 |

結果會輸出成一個**手機也能看的中文網頁**（可篩選「免費」、「最簡單」、「頂級機構支持」…），
以及一份 Markdown 清單 [`docs/AIRDROPS.md`](docs/AIRDROPS.md)，並可選擇把新項目**推播到你的 Telegram**。

---

## 資料來源

| 類型 | 來源 | 用途 |
|---|---|---|
| 空投網站 | [airdrops.io](https://airdrops.io)（最新 / 熱門 / 潛在） | 空投列表、狀態、步驟教學、需求（KYC、X、TG…） |
| 空投網站 | [DropsTab](https://dropstab.com/activities) | 積分 / 測試網 / 空投活動，**附投資機構與募資金額** |
| 鏈上數據 | [DefiLlama](https://defillama.com) | 「還沒發幣但鎖倉量很高」的協議 → 潛在空投 |
| 市場數據 | [CoinGecko](https://www.coingecko.com) | 已上線的熱門 P2E / GameFi 遊戲（價格、市值） |
| Telegram | airdrops_io、AirdropDetective、airdropinspector、airdrop、airdropfind、ICODrops、幣安公告 | 最新空投情報（免帳號，抓公開頻道預覽） |
| X (Twitter) | X API 搜尋，或自架 RSSHub | 關鍵字搜尋 + 追蹤指定帳號 |
| Reddit | r/airdrops、r/CryptoAirdrop、r/playtoearn | 社群討論 |
| 新聞 | CoinTelegraph、The Block、Decrypt、Blockworks、CoinDesk、Google News | 只保留與空投 / P2E 相關的文章 |

所有來源都可以在 [`config/sources.yaml`](config/sources.yaml) 新增、刪除或調整。

## 兩種分析模式

| | Claude AI 模式（推薦） | 規則模式（免費） |
|---|---|---|
| 需要 | `ANTHROPIC_API_KEY` | 不需要任何 key |
| 翻譯 | 自然流暢的中文 | Google 機器翻譯 |
| 支撐 / 難度 / 費用判斷 | AI 閱讀全文判斷，並**上網查證**投資方、是否已確認空投、官方連結 | 關鍵字規則 + 內建 VC 名單 |
| 社群貼文 | 從 Telegram / X / 新聞中**抽取出新項目**並建立卡片 | 只翻譯貼文，顯示在「最新情報」 |
| 詐騙偵測 | AI 判斷 + 自動排除可疑項目 | 關鍵字（助記詞、私鑰、保證獲利…） |

沒有設定 API key 時會自動使用規則模式；之後加上 key，舊項目會在後續執行中逐步升級成 AI 分析。

---

## 🚀 部署到 GitHub（自動更新，不需要自己的電腦）

1. **開啟 GitHub Pages**：Repo → Settings → Pages → Source 選「Deploy from a branch」→ Branch 選 `main`、資料夾選 `/docs` → Save。
   幾分鐘後網址會是 `https://<你的帳號>.github.io/<repo 名稱>/`。
2. **（建議）加入 Claude API key**：Settings → Secrets and variables → Actions → New repository secret
   - `ANTHROPIC_API_KEY`：到 <https://console.anthropic.com> 申請
3. **（選用）其他設定**（同一個頁面）：
   - Secret `X_BEARER_TOKEN`：X API 的 Bearer Token，用來搜尋 X 上的空投貼文
   - Secret `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`：新項目推播到你的 Telegram（用 [@BotFather](https://t.me/BotFather) 建立機器人；chat id 可用 [@userinfobot](https://t.me/userinfobot) 查詢）
   - Variable `CLAUDE_MODEL`：想換模型時設定（預設 `claude-opus-5-5`；想省錢可設 `claude-sonnet-5-5`）
4. **啟動**：Actions 分頁 → 「更新空投資料」→ Run workflow。之後會**每 3 小時自動更新**並把結果 commit 回 repo。

> 想改更新頻率：修改 `.github/workflows/update.yml` 裡的 `cron`（例如 `"17 */6 * * *"` = 每 6 小時）。

## 💻 在自己電腦執行

```bash
pip install -r requirements.txt

# 規則模式（免費）
python -m airdrop_hunter run --no-ai

# AI 模式
export ANTHROPIC_API_KEY=sk-ant-...
python -m airdrop_hunter run

# 打開網頁
cd docs && python -m http.server 8000   # 瀏覽器開 http://localhost:8000

# 其他指令
python -m airdrop_hunter sources        # 測試每個來源抓到幾筆
python -m airdrop_hunter render         # 只用現有資料重新產生網頁
python -m pytest -q                     # 執行測試
```

## 💰 費用估算（AI 模式）

只有**新出現或內容有變動**的項目才會送去 AI 分析，舊的會沿用結果。
上限由 `config/sources.yaml` 的 `ai.max_projects_per_run`（預設 15）與 `ai.max_posts_per_run`（預設 60）控制。

- 每個項目（含最多 2 次網路搜尋）約 US$0.05–0.20；不開搜尋（`web_search: false`）約 US$0.02–0.05
- 每 12 則貼文的抽取約 US$0.03–0.08
- 第一次執行要補齊所有項目，會花比較多；之後每天通常只有少量新項目
- 想再省：調低上面兩個上限、把 `effort` 維持 `low`、關閉 `web_search`，或把 `CLAUDE_MODEL` 設為 `claude-sonnet-5-5`

---

## 專案結構

```
airdrop_hunter/
  sources/        各資料來源（airdrops_io、dropstab、defillama、coingecko、telegram、x_api、feeds）
  enrich/ai.py    Claude 分析：翻譯、支撐 / 難度 / 費用 / 發放判斷、上網查證、從貼文抽取項目
  enrich/rules.py 沒有 API key 時的規則分析 + 免費翻譯
  enrich/vc.py    知名投資機構名單（可自行增修）
  pipeline.py     收集 → 抽取 → 合併去重 → 分析 → 標記過期
  render.py       產生 docs/data.json、docs/index.html、docs/AIRDROPS.md
  notify.py       Telegram 推播
config/sources.yaml  所有設定
site/index.html      網頁原始檔（會複製到 docs/）
data/db.json         資料庫（每次執行自動更新）
```

- 同一個項目出現在多個來源時會自動合併（例如 airdrops.io 的步驟 + DropsTab 的投資方）。
- 超過 21 天沒有任何來源再提到的項目會標記為「已結束（久未更新）」，60 天後刪除；只有社群提到的項目更早過期。
- 網頁上所有外部文字都以純文字顯示、連結只允許 `http(s)`，避免惡意內容。

## ⚠️ 免責聲明 & 防詐提醒

本專案內容由程式自動收集與 AI 整理，**可能有錯誤或過時資訊，不構成任何投資建議**。

- **任何要你輸入助記詞 / 私鑰的網站都是詐騙。**真正的空投只需要連接錢包與簽名。
- 只從官方 X / Discord 公告或可信來源進入，小心假冒網址。
- 用專門的空投錢包，不要放大額資產；簽名前確認授權額度。
- 「官方未確認」的空投可能做了也拿不到；需要投入資金的項目有本金與合約風險。
- 請遵守各網站的使用條款與你所在地的法規。
