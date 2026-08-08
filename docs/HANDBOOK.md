# SVE Meta 專案手冊（交接／LLM 上手用）

> 最後更新：2026-08-09。給接手的人與 AI 的完整導覽：這個專案在做什麼、
> 架構長怎樣、資料從哪來、日常怎麼維運、以及**如何用這包資料做牌組分析**。

---

## 1. 這個專案在做什麼

抓 **Shadowverse Evolve（SVE，Bushiroad 實體卡牌遊戲）** 的日本線下賽結果，
自動整理成一個**純靜態網站**，部署在 GitHub Pages，每天自動更新三次。

網站功能（網址 `https://xingting1026.github.io/shadowverseWBCard/`）：

| 頁面 | 功能 |
|---|---|
| `index.html` Meta 總表 | 各月份（或自訂期間+最低人數）的職業占比圓餅、每場比賽前8強名單 |
| `tiers.html` 近期 Meta 牌組一覽 | 近 15 天入賞牌組自動聚類成「原型」，分 T0~T5，附共識牌表/彈性卡位/範例牌組 |
| `champions.html` 冠軍牌組·最省組件 | 各月第1名牌組，以同名最便宜印刷計算全新組建成本，由便宜到貴 |
| `search.html` 卡片查詢 | 查一張卡（卡號或卡名，同名印刷自動合併）被哪些冠軍牌組用過、各帶幾張 |
| `deck.html?m=&code=` 牌組單卡 | 一副牌的完整卡表＋單價；`&cheapest=1` 顯示最省替換版；可連 DeckLog 原頁 |
| 牌效彈窗（各頁點卡片） | 大卡圖＋完整牌效＋flavor，**繁中/日文一鍵切換**（中文缺翻自動退日文） |

---

## 2. 架構總覽

**核心設計：沒有伺服器。** Python 只在「建站時」跑，產出純靜態檔案；
瀏覽器端只有原生 JS 讀 JSON 渲染。

```
┌────────── GitHub Actions（每日 3 次：台灣 18:00 / 20:00 / 22:10）──────────┐
│ scrape_meta.py --days 7   抓近7天賽果+牌組 → sve_meta.db                  │
│ update_sets.py            新彈自動補卡表/牌效/價格；刷新近30天set價格      │
│ build_site.py             sve_meta.db → site/（HTML+JS+JSON+卡圖）        │
│ git commit db+img_cache   （狀態持久化，下次增量）                        │
│ deploy-pages              site/ → GitHub Pages                            │
└───────────────────────────────────────────────────────────────────────────┘
```

- 排程定義在 [.github/workflows/update.yml](../.github/workflows/update.yml)。
  爬蟲步驟 `continue-on-error`：偶發 timeout 不會讓整趟失敗，用既有資料照常部署，
  缺的資料下一班次（回看 7 天）自動補回。
- `sve_meta.db`（SQLite）與 `img_cache/`（卡圖縮圖）**都 commit 進版控**，
  這就是「狀態」——Actions 每天增量更新，不用重抓歷史。
- 本機預覽：`python run.py` → http://localhost:5000（產站但不抓圖）。

### 前端（web/ → 建站時複製到 site/）

- 無框架，原生 JS 單檔 [web/static/app.js](../web/static/app.js)，依 `body[data-page]` 分派各頁邏輯。
- 深色主題 [web/static/style.css](../web/static/style.css)；職業固定色（圓餅用色塊、標籤用文字色）。
- HTML 引用的 css/js 會在建站時加上內容雜湊（`?v=xxxx`）破快取。
- 卡圖懶載入（IntersectionObserver）；牌效 JSON 第一次點卡才下載。

### 後端模組（sve_meta/，只在建站時執行）

| 模組 | 職責 |
|---|---|
| `bushinavi.py` | Bushi-Navi 賽果 API 客戶端 |
| `decklog.py` | DeckLog 牌組碼 → 單卡清單（存 decks 表快取） |
| `cardmaster.py` | 官方卡表爬蟲（卡名/種類/費用/攻體/卡圖路徑/**牌效/flavor**）。解析器必須用 **lxml**（見 §7） |
| `prices.py` | yuyu-tei 單卡價爬蟲（`is_manual=1` 的手動價不會被覆蓋） |
| `setsync.py` | 新彈自我修復：牌組出現卡表沒有的 set → 自動補卡表+牌效+價格 |
| `events_store.py` | 賽果持久化（events 表，rankings 含展開後的牌表 JSON） |
| `byname.py` | 「卡名＋基本/進化」身分層：同名不同印刷視為同卡、找最便宜印刷 |
| `tiering.py` | 原型聚類與 T0~T5（見 §5），可調參數都在檔頭常數 |
| `sitebuild.py` | DB → site/ 的總匯出器（月份JSON/tiers/卡表/牌效/查詢索引/卡圖） |
| `classmap.py` | 職業正規化（聯動 leader → 基礎職業；空白 → 略過不顯示） |
| `imgproxy.py` | 官方卡圖 → 240px JPEG 縮圖快取（抓不到存佔位圖，之後每天自動重試） |

---

## 3. 資料來源（皆為第三方，請保持低頻與快取）

| 來源 | 用途 | 備註 |
|---|---|---|
| Bushi-Navi API `api-user.bushi-navi.com` | 賽事清單與名次 | header `X-Accept-Version: v1`；資料最早回溯 2024-05-01；**只有最終名次，無對局細節（誰打誰/勝負）** |
| DeckLog `decklog.bushiroad.com` | 牌組碼 → 60張明細 | POST `/system/app/api/view/{code}`；跨 Bushiroad 全遊戲共用（可能查到 WS 等他遊戲牌組） |
| 官方卡表 `shadowverse-evolve.com/cardlist/` | 卡名/種類/數值/卡圖路徑/**日文牌效** | 列表頁就有完整牌效；HTML 有未閉合的 `<img>`，**必須用 lxml 解析** |
| yuyu-tei `yuyu-tei.jp/sell/sev/` | 單卡日幣售價 | 部分預組/PR 無單卡價 → 顯示「無價卡」不計入金額 |

每請求間隔 1 秒（`config.REQUEST_DELAY`）。

---

## 4. 資料層 schema

### SQLite（sve_meta.db）

```sql
cards  (card_number PK, name, class, type, cost, atk, def, set_code, rarity, img,
        text,      -- 日文牌效（含 [圖示] 標記與換行）
        flavor)    -- flavor text
prices (card_number PK, jpy, fetched_at, source, is_manual)
decks  (code PK, class, list_json, evolve_json, fetched_at)   -- DeckLog 快取
events (event_id PK, title, store, pref, players, start_date,
        rankings_json)  -- [{rank, class, deck_code, list:[{card_number,num}], evolve:[...]}]
```

### 靜態站資料檔（site/data/，建站產出）

| 檔案 | 內容 |
|---|---|
| `index.json` | `{generated_at, months:[...], latest}` |
| `month/YYYY-MM.json` | `{events:[{id,title,store,players,date,rankings:[{rank,cls,code}]}], decks:{code:{cls,main:[[卡號,張數]],evo:[...]}}, champions:[{code,cls,event,date,players,cost,unpriced}], cheapest:{code:{cost,unpriced:[卡名],main:[{cn,name,num,unit}],evo:[...]}}}` |
| `cards.json` | `{卡號: [卡名, 單價或null, 是否進化(0/1)]}`（只含牌組用過的卡） |
| `effects.ja.json` | `{卡名: {"B"|"E": [牌效, flavor]}}`——**同名所有印刷共用一份**，B=基本卡、E=進化卡 |
| `effects.zh.json` | 同上結構的繁中版（來源是 repo 的 `translations/effects.zh.json`） |
| `tiers.json` | `{window:{start,end,days}, total_decks, clusters:[{cls,label,tier,score,share,n,wins,signature,consensus:{main,evo},flexible,samples}], others}` |
| `usage/{SET}.json` | `{卡號: [[月份,牌組碼,活動,日期,人數,張數],...]}`——卡片查詢的反向索引（只收第1名牌組） |

牌效文字裡的記號：`[コスト2]`、`[攻撃力]`、`[体力]`、`[エルフ]` 等半形方括號是
**圖示佔位符**（原卡面上的 icon）；`【入場曲】`、`【疾走】` 等全形是關鍵字能力；
`『卡名』` 是引用其他卡/token（保留日文，可拿去對卡名索引）。

---

## 5. 原型聚類（tiers）演算法

在 [sve_meta/tiering.py](../sve_meta/tiering.py)，參數全在檔頭常數：

1. 視窗：最新賽事日往回 `WINDOW_DAYS=15` 天、前8強、有公開牌表的牌組。
2. 牌組向量＝「卡名＋基本/進化」張數 multiset；相似度＝Σmin/Σmax（multiset Jaccard）。
3. 同職業內相似度 ≥ `SIM_THRESHOLD=0.5` 用 union-find 併成一個「原型」。
4. 命名＝群內出現率 × 全場 IDF 最高的 2 張特徵卡（跨職業算 IDF，中立萬用卡壓得下去）。
5. 計分：冠軍3／亞軍2／3-4名1.5／5-8名1，加總為原型分數。
6. 檔位＝分數相對最強原型的比例：T0≥70%、T1≥45%、T2≥25%、T3≥12%、T4≥5%、餘 T5（同型<2副歸「其他」）。
7. 共識牌表＝群內 ≥50% 的人帶的卡（張數取中位數）；彈性卡位＝25~50%。

---

## 6. 工具箱（repo 根目錄的可執行腳本）

| 腳本 | 用途 | 什麼時候跑 |
|---|---|---|
| `scrape_meta.py` | 抓賽果（`--days N` / `--from --to --by-month` / `--min 人數` / `--delay`） | Actions 每天自動；手動回補歷史才自己跑 |
| `update_sets.py` | 新彈偵測補資料＋刷新近期價格（`--no-prices` 只補新彈） | Actions 每天自動 |
| `build_site.py` | 產站（`--no-images` 跳過抓圖；`--out` 換輸出目錄） | Actions 自動；本機驗證時 |
| `run.py` | 產站＋本機預覽伺服器 :5000 | 本機開發 |
| `init_data.py` | 一次性灌全部 set 卡表+價格 | 幾乎不再需要（setsync 會自動補新的） |
| `refill_texts.py` | 重抓全部 set 的卡表（含牌效） | 只在解析邏輯改動後需要全量重建時 |
| `missing_zh.py` | 統計/匯出「還沒中文翻譯」的牌效（`--export dir` 切批次檔） | 新彈後想補中文時 |
| `merge_zh.py` | 合併 AI 翻譯批次 → `translations/effects.zh.json`（含驗證+術語統一） | 補翻完成後 |

---

## 7. 已知眉角（血淚史，別再踩）

1. **HTML 解析一定要用 lxml**。官方卡表頁的 `<img>` 沒閉合，`html.parser` 會提早
   關閉容器導致**牌效被截斷在圖示處**（歷史上 2,483 張卡中招）。`cardmaster.py`
   全部走 lxml，不要改回去。
2. **git pull 撞到 `sve_meta.db` 衝突**：Actions 每天 commit 資料庫，本地若也改過
   DB 就會二進位衝突。解法（rebase 時）：
   `git checkout --theirs sve_meta.db && git add sve_meta.db && git rebase --continue`
   （rebase 語意下 `--theirs`＝**本地版**）。少抓到的賽果下一班次自動補回。
3. **快取**：靜態資產已用內容雜湊破快取；但 GitHub Pages CDN 對 JSON 有約 10 分鐘
   快取，部署後看到舊資料等幾分鐘或強制重整。
4. **卡圖佔位圖**：新卡發售時官方常還沒上圖，抓失敗會快取灰色佔位圖；
   每次產站會自動重試佔位圖，官方上圖後隔天自動補齊。
5. **職業空白的名次**（店家沒登錄）在匯出時直接略過不顯示；店家補登後自動回來。
6. **對局層級資料拿不到**：Bushi-Navi 公開端點只有最終名次，沒有配對表/單場勝負，
   所以做不出「原型 A 對原型 B 勝率」矩陣，只能從名次分布間接推論。

---

## 8. 新彈出來時的 SOP

**全自動的部分（不用動手）**：牌組裡一出現新 set 的卡，`update_sets.py`（每天跑）
會自動抓官方卡表＋完整日文牌效＋yuyu-tei 價格＋卡圖；tiers/meta/查詢全部自動吃到新卡。

**補中文翻譯（半自動，想做時再做）**：

```bash
python missing_zh.py                    # 看缺多少
python missing_zh.py --export zh_todo   # 缺的切成 ja_XX.json 批次檔
```

然後把批次檔交給 LLM 翻譯（歷史上是派 Claude Sonnet 子代理，每批 110~150 卡名）。
翻譯 prompt 的鐵則（完整版可參考 git log 中派工用的 prompt）：

- JSON key（日文卡名）一字不改；『』內引用卡名保留日文
- 半形 `[圖示]` token 原樣保留（只有 [ファンファーレ]→【入場曲】、[ラストワード]→【謝幕曲】、[起動]→【起動】三個例外）
- 術語表：從者/法術/護符/主戰者/牌組/手牌/EX區/傷害/抽牌…（見 merge_zh.py 的 TERM_CANON）

翻完放進資料夾後：

```bash
python merge_zh.py zh_todo    # 驗證（token/長度）+ 術語統一 + 合併
python build_site.py --no-images
git add -A && git commit && git push
```

驗證器會自動剔除不合格的條目（那些卡先 fallback 顯示日文，之後再補）。

---

## 9. 給 LLM 的環境分析指引（本專案的下一階段用途）

想讓 LLM 做「牌組好壞分析／組牌建議」，資料已經齊了。建議的餵法：

**環境全貌**（誰強、標準構成長怎樣）：
- `site/data/tiers.json` — 當前 T0~T5 原型、每個原型的共識牌表（幾乎必帶的卡+張數）、
  彈性卡位、入賞數/冠軍數/占比。這就是「環境」的結構化摘要。
- `site/data/month/YYYY-MM.json` 的 `decks` — 每一副實際入賞 60 張的完整構成。

**卡片知識**（每張卡做什麼）：
- `site/data/effects.ja.json` / `effects.zh.json` — 全卡牌效（按卡名去重，B/E 分開）。
- `site/data/cards.json` — 卡號→卡名/價格/是否進化 的對照。

**單卡採用度**：
- `site/data/usage/{SET}.json` — 一張卡被哪些冠軍牌組用、各帶幾張（採用率與張數共識）。

**分析範例流程**（給一副待評估的牌組）：
1. 把牌組的卡號經 `cards.json` 轉成卡名，對 `effects.*.json` 取牌效 → LLM 理解每張卡功能。
2. 與 `tiers.json` 同職業原型的共識牌表做差集 → 「你比主流版本多帶/少帶了什麼」。
3. 用 `usage/` 看少帶的卡在冠軍牌組的採用率/張數 → 量化「不足之處」。
4. 對照 T0 原型的效果文（解場/攻速/回復手段）→ 推論對抗環境的弱點。

**已知限制**：沒有對局勝負資料（§7-6），勝率類結論只能從入賞分布間接推論；
牌效繁中是 AI 翻譯打底（數值經驗證器把關，語感可能不完美），嚴謹分析建議以日文為準。

---

## 10. 檔案地圖速查

```
├─ .github/workflows/update.yml   每日自動化（抓→補→產→部署）
├─ sve_meta/                      Python 模組（見 §2 表）
├─ web/                           前端源碼（建站時複製進 site/）
├─ site/                          產站輸出（gitignore，Actions 每次重建）
├─ translations/effects.zh.json   繁中牌效母本（人工/AI 維護，commit 進版控）
├─ sve_meta.db                    SQLite 資料庫（commit 進版控）
├─ img_cache/                     卡圖縮圖快取（commit 進版控）
├─ docs/HANDBOOK.md               本文件
├─ docs/superpowers/specs/        歷次設計文件
└─ tests/                         pytest（56 個測試；改完跑 pytest -q）
```
