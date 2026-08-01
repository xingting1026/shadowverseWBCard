# SVE Meta（靜態站 · GitHub Pages 每日自動更新）

抓 Shadowverse Evolve 線下賽 meta，產出**純靜態網站**部署在 GitHub Pages，
GitHub Actions **每天自動抓新賽果**、重新產站、自動部署。Python + SQLite（僅建站時用）。

功能：
1. **Meta 總表**：月份切換、前8強/僅第1名、職業圓餅、各場比賽各隊組法（點入看單卡）。
2. **近期 Meta 牌組一覽**：近 15 天入賞牌組自動聚成「原型」、分 T0~T5 檔位，
   每個原型附「共識牌表」（大家幾乎都帶的卡）、「彈性卡位」與實際範例牌組。
3. **冠軍牌組·最省組件**：該月第 1 名牌組，以**同名最便宜印刷**計全新組建成本，由便宜到貴。

詳細設計見 `docs/superpowers/specs/`（原始工具設計 + 2026-08-01 靜態化設計）。

## 部署（GitHub Pages，一次性設定）
1. push 到 GitHub（repo 需為 public，或帳號有 Pages 私有 repo 權限）。
2. Repo → Settings → Pages → **Source 選「GitHub Actions」**。
3. Repo → Settings → Actions → General → Workflow permissions 選
   **「Read and write permissions」**（每日更新要把 DB commit 回 repo）。
4. 完成。`.github/workflows/update.yml` 會在每次 push 重新部署，
   並在**每天 14:10 UTC（23:10 JST）**自動抓近 3 天新賽果 → 更新 → 部署。
   也可到 Actions 頁籤手動 Run workflow。

網址：`https://<帳號>.github.io/<repo名>/`

- `sve_meta.db`（卡表/價格/歷史 meta）與 `img_cache/`（卡圖縮圖）都 **commit 進版控**，
  Actions 每天只增量更新，不會重抓全部。
- 不往回補歷史；要回補時本機跑 `scrape_meta.py --from ... --by-month` 再 push。

## 本機開發
```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py        # 產站（不抓圖）+ 預覽 http://localhost:5000
```

完整產站（含補抓缺少的卡圖縮圖）：
```bash
python build_site.py
```

## 抓比賽 meta（存進 sve_meta.db）
Bushi-Navi 的 SVE 賽果最早回溯到 2024-05-01。
```bash
python scrape_meta.py                                   # 近 30 天、≥8 人（預設）
python scrape_meta.py --days 14 --min 16
python scrape_meta.py --from 2024-05-01 --to 2026-06-30 --by-month  # 逐月回補歷史
```

## 首次初始化卡表/價格（一次性，約 10+ 分鐘）
```bash
python init_data.py    # 全 53 個 set：官方卡表（全分頁）+ yuyu-tei 價格
```

## 測試
```bash
pytest -q
```

## 原型聚類（tiers）怎麼算
- 同職業內，牌組以「卡名＋基本/進化」張數算 multiset Jaccard 相似度，≥0.5 視為同原型。
- 原型名稱＝該群「出現率 × 職業內鑑別度」最高的 2 張特徵卡（不是社群俗名）。
- 檔位分數＝視窗內入賞加權（冠軍3、亞軍2、四強1.5、八強1），
  相對最強原型的比例切 T0~T5。參數都在 `sve_meta/tiering.py` 頂部常數。

## 資料來源（皆為 Bushiroad / 第三方，自用請狠快取、加 delay、勿高頻）
- Bushi-Navi 賽果 API（`api-user.bushi-navi.com`，header `X-Accept-Version: v1`）
- DeckLog 牌組碼 → 單卡（`decklog.bushiroad.com/system/app/api/view/{code}`，POST）
- yuyu-tei 單卡日幣價（`yuyu-tei.jp/sell/sev/s/{set}`）
- 官方日版卡表（`shadowverse-evolve.com/cardlist/cardsearch/`）
