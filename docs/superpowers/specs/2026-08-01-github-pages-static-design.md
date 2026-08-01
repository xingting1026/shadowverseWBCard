# SVE Meta 靜態化 + GitHub Pages 每日自動更新 — 設計

日期：2026-08-01
狀態：實作中（使用者指示先開發、tier 排名法保留討論空間）

## 目標

1. 網站改成**純靜態**，部署到 GitHub Pages（免費、公開 repo 已具備）。
2. GitHub Actions **每日自動抓新賽果**（不回補歷史），更新資料後重新產站、自動部署。
3. **移除**「收藏」與「排行榜·補完」功能（不再有 localStorage / 缺卡 / 補完成本）。
4. Meta 總表保留（月份切換、前8強/僅第1名、職業圓餅、各場各隊組法），**不顯示缺幾張**。
5. 「排行榜·最省組建」改名為「**冠軍牌組·最省組件**」（內容不變：各月第1名牌組
   以同名最便宜印刷計全新組建成本，由便宜到貴）。
6. 新增「**近期 Meta 牌組一覽**」：近 30 天的牌組自動聚類成原型（archetype），
   分 T0～T5 檔位。使用者不知道社群俗名（骰子夢、跳費龍…），所以原型用
   「職業＋特徵卡」自動命名，並展示「共識牌表」與「彈性卡位」。

## 架構

```
GitHub Actions（每日 cron）
  scrape_meta.py --days 3        # 抓近 3 天新賽果 → sve_meta.db（commit 回 repo）
  build_site.py                  # DB → site/（HTML+JS+JSON+卡圖縮圖）
  commit db + img_cache → push
  upload site/ → deploy GitHub Pages
```

- **資料層不動**：bushinavi / decklog / events_store / byname / prices / cardmaster / db 照舊。
- **web.py（Flask）、templates、收藏（collection.py, owned.js）全部移除**。
  `run.py` 改成「產站 + 本機 http.server 預覽」。
- 卡圖：無法可靠熱連結官方圖（需 Referer），改為 build 時抓 240px 縮圖存
  `img_cache/`（**commit 進 repo**，約 4200 張 × ~15KB ≈ 60-80MB，一次性；每日只增量），
  產站時複製到 `site/img/`。

## 靜態站頁面

| 頁面 | 說明 |
|---|---|
| `index.html` | Meta 總表（月份切換、scope 切換、圓餅、各場各隊組法） |
| `tiers.html` | 近期 Meta 牌組一覽（T0~T5） |
| `champions.html` | 冠軍牌組·最省組件（月份切換） |
| `deck.html?m=YYYY-MM&code=…[&cheapest=1]` | 牌組單卡（一般 / 最省組件替換模式） |

資料檔（build 產出）：
- `data/index.json`：月份清單、產生時間。
- `data/month/YYYY-MM.json`：該月 events（含名次/職業/牌組碼）、牌組明細
  `{code: {cls, main:[[cn,num]…], evo:[…]}}`、冠軍最省 `{code: {cost, unpriced, main:[{cn,name,num,unit}…], evo:[…]}}`。
- `data/cards.json`：`{cn: [name, price]}`（只含牌組用到的卡）。
- `data/tiers.json`：聚類結果（見下）。

前端：原生 JS（無框架），沿用既有 style.css 深色風、IntersectionObserver 懶載圖。

## 原型聚類與 T0~T5（tiering.py）

- **視窗**：最新賽事日往回 30 天、前 8 強、有公開牌表的牌組。
- **向量**：牌組＝「卡名＋基本/進化」身分的張數 multiset（主＋進化）。
- **相似度**：multiset Jaccard = Σmin/Σmax。同職業內兩兩比較，
  相似度 ≥ 0.5 視為同原型，union-find 聚類。
- **命名**：不用社群俗名。每群取「特徵卡」＝群內出現率 × 職業內鑑別度（IDF）
  最高的主牌組卡，標籤形如「【ドラゴン】卡A＋卡B 型」。
- **共識牌表**：群內 ≥50% 牌組都有的卡，張數取中位數；「彈性卡位」＝25~50% 出現率的卡。
  另附實際範例牌組連結（名次最好的前 3 副）。
- **檔位分數**：每筆入賞計分 — 第1名=3、第2名=2、第3-4名=1.5、第5-8名=1，群分數=總和。
- **檔位門檻**（相對最強群的分數）：T0 ≥70%、T1 ≥45%、T2 ≥25%、T3 ≥12%、T4 ≥5%、
  其餘且樣本 ≥2 為 T5；單一樣本歸「其他」。門檻與權重集中在 tiering.py 常數，方便調整。

## GitHub Actions

`.github/workflows/update.yml`：
- 觸發：每日 14:10 UTC（23:10 JST，當天賽果多已上傳）＋ push main ＋ 手動。
- 步驟：checkout → Python 3.12 → pip install → `scrape_meta.py --days 3`
  → `build_site.py` → 有變更就 commit `sve_meta.db` + `img_cache/` → push
  → `configure-pages(enablement)` → upload `site/` → `deploy-pages`。
- permissions: contents:write, pages:write, id-token:write。

## 移除清單

web.py、templates/、static/（owned.js、app.js 舊版）、collection.py、Procfile、
tests/test_web.py、tests/test_collection.py。DB 的 owned 表保留不用（無害）。

## 測試

- `tests/test_tiering.py`：相似度、聚類、命名、共識表、檔位分配。
- `tests/test_sitebuild.py`：月份匯出形狀、冠軍最省成本與 byname 邏輯一致。
- 既有資料層測試照跑。
