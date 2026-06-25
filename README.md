# SVE Meta 收藏差距工具

抓 Shadowverse Evolve 線下賽 meta、把每副入賞牌以**單張卡**呈現、對照我的收藏算出
「差哪些卡」與「補完成本」，並依成本排序。Flask + SQLite。

**收藏（擁有數量）只存在使用者的瀏覽器（localStorage），不上傳伺服器**；補完成本、
缺卡、排行榜都在瀏覽器即時計算，所以可公開部署、每個訪客各看各的、不互相覆蓋。

詳細設計見 `docs/superpowers/specs/2026-06-23-sve-meta-collection-tool-design.md`。

## 部署（已可上線）
- `sve_meta.db`（含卡表 / 價格 / 一年 meta）**有 commit 進版控**，部署後直接有資料。
- 不能用 GitHub Pages（那是靜態）；用能跑 Python 的主機（Render / Railway / Fly.io）。
- 啟動指令見 `Procfile`：`gunicorn "sve_meta.web:create_app()" --bind 0.0.0.0:$PORT`。
- 例（Render）：New → Web Service → 連這個 repo → Build `pip install -r requirements.txt`、
  Start `gunicorn "sve_meta.web:create_app()" --bind 0.0.0.0:$PORT`。
- 註：多數平台檔案系統是暫時的，執行時抓的卡圖 / 新賽事不會永久保存（重啟後重抓）；
  已 commit 的 `sve_meta.db` 仍在，所以歷史 meta 一直都在。

## 安裝
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## 首次初始化資料（一次性，會打官方站約 10+ 分鐘，請低頻）
```bash
python init_data.py    # 全 53 個 set：官方卡表（全分頁）+ yuyu-tei 價格
```
`init_data.py` 容錯：單一 set 失敗不中斷，最後印出抓不到/無價的清單。可重跑
（`INSERT OR REPLACE`），手動填過的價（`is_manual=1`）不會被覆蓋。只想灌特定 set
就改 `init_data.py` 裡的 `SETS` 清單。

## 抓比賽 meta（存進資料庫，跨重啟保留）
Bushi-Navi 的 SVE 賽果**最早回溯到 2024-05-01**（約 2 年、3400+ 場），全部可爬。
```bash
python scrape_meta.py                                   # 近 30 天、≥8 人（預設）
python scrape_meta.py --days 14 --min 16                # 近 14 天、≥16 人
python scrape_meta.py --from 2024-05-01 --to 2024-12-31 --min 8     # 指定歷史區間
python scrape_meta.py --from 2024-05-01 --to 2026-06-30 --by-month  # 逐月抓（做整段歷史推薦）
```
整段歷史很久（數十分鐘～數小時，每請求間隔 1 秒）。做歷史 meta 建議 `--by-month`
（一個月一段、有進度、可隨時 Ctrl+C，已抓的月份會留著）或提高 `--min` 只收大賽。

## 啟動
```bash
python run.py        # http://localhost:5000
```

## 使用
1. **收藏**：系列收合，展開才載圖；各卡 ＋/− 記錄擁有數（0–3）。
2. **Meta 總表**：選**檢視期間**（可拉到任意歷史月份）、切第1名/前8強、看職業圓餅圖、各場各隊組法。
3. **牌組**：看單卡 + 缺卡標紅 + 補完成本。
4. **排行榜·補完**：meta 牌組依「我的補完成本」由便宜到貴。
5. **排行榜·最省組建**：該期間第1名牌組，用**卡名取最便宜稀有度**算全新組建成本，由便宜到貴。

## 測試
```bash
. .venv/bin/activate && pytest -q
```

## 資料來源（皆為 Bushiroad / 第三方，自用請狠快取、加 delay、勿高頻）
- Bushi-Navi 賽果 API（`api-user.bushi-navi.com`，header `X-Accept-Version: v1`）
- DeckLog 牌組碼 → 單卡（`decklog.bushiroad.com/system/app/api/view/{code}`，POST）
- yuyu-tei 單卡日幣價（`yuyu-tei.jp/sell/sev/s/{set}`）
- 官方日版卡表（`shadowverse-evolve.com/cardlist/cardsearch/`）
