# SVE Meta 收藏差距工具 — 設計文件

- 日期：2026-06-23
- 狀態：設計已通過，待寫實作計畫
- 範圍：純自己用（單人、單機/一台小服務）

## 1. 目標

一個自架網站，反映 Shadowverse Evolve 當前線下賽 meta，並讓我：

1. 在收藏庫對每張卡記錄擁有數量（0–3）。
2. 把每副 meta 入賞牌**以一張張單卡呈現**（不是整副圖）。
3. 比對「我距離某副牌差哪些卡、差幾張」。
4. 從 yuyu-tei 查缺卡日幣價，算出**補完該牌組的總成本**。
5. 把所有 meta 牌組依「我的補完成本」升冪排序 →「差最少錢的是哪幾副」。

## 2. 架構總覽

- 單一 Flask app + 單一 SQLite 檔。
- 所有官方資料先抓進 SQLite **快取表**；頁面渲染只讀本地快取，**絕不在 request 熱路徑打官方**。
- 三個爬蟲：Bushi-Navi 與 DeckLog 是直接 HTTP API（`requests`）；yuyu-tei 與卡表是 server-render HTML（`requests` + `BeautifulSoup`）。**全程不需 Playwright / 無頭瀏覽器。**
- 主鍵全用 `card_number`（日版編號，如 `BP07-007`）。Bushi-Navi → DeckLog → yuyu-tei → 卡表四邊編號天然對齊，**不做任何英日轉換**。

```
Bushi-Navi API ──events + deck_recipe_id──┐
(game_title_id=6, X-Accept-Version:v1)     │
                                           ▼
              DeckLog API (POST view/{碼}) ──list[{card_number,num}]──┐
                                                                      ▼
我的收藏 (card_number → 0~3) ───────────────────────────────────►  差距比對
日版卡表 (card_number → 名稱/圖/職業) ──────────────────────────►  (缺 = max(0, 需要−擁有))
yuyu-tei (card_number → 日幣價) ────────────────────────────────►  補完成本 → 升冪排序
```

## 3. 資料模型（SQLite）

```
cards   (card_number PK, name, class, type, cost, atk, def, set, rarity, img)
owned   (card_number PK, qty)                          -- qty 0..3，唯一由使用者產生的資料
prices  (card_number PK, jpy, fetched_at, source, is_manual)
decks   (code PK, game_title_id, class, list_json, fetched_at)   -- DeckLog 拆解結果，永久快取
events  (event_id PK, title, store, pref, players, start_date, rankings_json, fetched_at)
```

- `decks.list_json`：`[{ "card_number": "...", "num": N }, ...]`
- `events.rankings_json`：`[{ "rank": N, "player": "...", "class": "...", "deck_code": "..." }, ...]`
- `prices.is_manual`：true 表示人工填的價，刷新時不被自動覆蓋。

## 4. 模組拆解（各一檔，可獨立測試）

| 模組 | 職責 | 介面（概念） |
|------|------|------|
| `cardmaster` | 爬日版卡表寫入 `cards` | `refresh_set(set)`、`get(card_number)`、`by_set()` |
| `collection` | 讀寫收藏 | `get_owned() -> dict[cn,qty]`、`set_owned(cn, qty)` |
| `decklog` | 牌組碼 → 單卡清單（快取） | `resolve(code) -> {game_title_id, class, list:[{card_number,num}]}` |
| `bushinavi` | 走賽果 API（快取） | `fetch_events(start, end, min_players) -> [event...]` |
| `prices` | 爬 yuyu-tei + 手動覆寫 | `get(cn) -> jpy?`、`refresh_set(set)`、`set_manual(cn, jpy)` |
| `engine` | **純函式**：diff / 成本 / 排序 / meta 聚合 | 見 §6 |
| `web` | Flask 路由 + 前端頁面 | 見 §7 |

每個爬蟲模組對外只回乾淨的 Python 結構，官方回應的細節（headers、分頁、重試）都封在模組內。

## 5. 外部端點規格（已實測，2026-06-23）

### 5.1 Bushi-Navi（公開、免登入、CORS 全開）
- 列表：`GET https://api-user.bushi-navi.com/api/user/event/result/list`
  - query：`game_title_id[]=6`（SVE）、`start_date=YYYY-MM-DD`、`end_date=YYYY-MM-DD`、`limit=50`、`offset=N`
  - **必帶 header `X-Accept-Version: v1`**（不帶 → 404）。
  - 逐頁 `offset += limit` 直到 `events[]` 空。
  - 每筆 event 含 `event_id`、`event_title`、`place`（店家/場地）、`pref_code`、`joined_player_count`。
  - **最小參賽人數在 client 端用 `joined_player_count` 過濾**（API 無原生參數）。
- 詳情：`GET .../api/user/event/result/detail/{event_id}`（同樣帶 `X-Accept-Version: v1`）
  - `success.grouped_rankings`：每筆含 `rank`、`team_member[].player_name`、`team_member[].deck_param1`（職業/類型）、`team_member[].deck_recipe_id`（**= DeckLog 牌組碼**）。
- 注意：主辦可設「入賞牌隱藏期」（`hide_winning_deck_start/end_datetime`），期間部分活動無牌組碼。

### 5.2 DeckLog（牌組碼 → 單卡）
- `POST https://decklog.bushiroad.com/system/app/api/view/{CODE}`
  - **必須 POST**；GET 回 `[]`。
  - body：`{}`；header：`Content-Type: application/json` + `Referer: https://decklog.bushiroad.com/view/{CODE}`。
  - 回傳 `{ game_title_id, list:[{ card_number, img, num, ... }], sub_list, ... }`。SVE = `game_title_id 6`。
  - 每張卡的 `card_number`（如 `BP07-007`）直接可用，即主鍵。
- 失敗模式：被刪/隱藏/過期 → 回 `[]`（HTTP 仍 200）。
- 卡圖：`https://shadowverse-evolve.com/wordpress/wp-content/images/cardlist/` + `img`（如 `BP07/bp07-007.png`）。**直連會 404（防盜連），需帶 `Referer: https://decklog.bushiroad.com/`**，見 §8。

### 5.3 yuyu-tei（價格）
- `GET https://yuyu-tei.jp/sell/sev/s/{set}`（`sev` = Shadowverse Evolve；改 `{set}`，如 `bp06`、`bp07`…）。
- server-render HTML；每張卡列出官方卡號（`BP06-001`）、日幣價、稀有度、庫存。**卡號精準對號，不需模糊比對。**
- set 清單由 `https://yuyu-tei.jp/sell/sev/` 列舉。

### 5.4 日版卡表母表
- `GET https://shadowverse-evolve.com/cardlist/cardsearch/?expansion={SET}&view=text`
- DOM 固定：`ul.cardlist-Result_List` 內 `p.number`（卡號）、`p.ttl`（名稱）、`div.status`（類型）、`span.status-Item-Cost/-Power/-Hp`、`div.center-Txtarea`（能力）。`var max_page` 控分頁。
- set 列表：`https://shadowverse-evolve.com/cardlist/`（列舉 BP01..、CP..、SD.. 等）。
- 日版卡號無 EN 後綴；圖檔小寫（`bp17-001.png`）。

## 6. 核心運算（`engine`，純函式，先寫測試）

- 差距：`missing(deck, owned) = { cn: max(0, need - owned.get(cn, 0)) for cn, need in deck if need > owned.get(cn,0) }`
- 成本：`cost(deck, owned, prices) = Σ missing[cn] × prices[cn]`；某 `cn` 無價 → 標記 `?` 並列入「待補價」清單。
- 排序：`rank(decks, owned, prices) = sorted(decks, key=cost)` 升冪。
- meta 聚合：依 `deck_param1` **正規化成七職**（把聯動 leader title 收斂回基礎職業，需一張 title→class 對照表）後計數，產出甜甜圈資料，支援「前 8 強 / 僅第 1 名」toggle。

## 7. 前端頁面（4 頁）

1. **收藏**：卡表依 set 分頁，每張一個 `0–3` 的 `+/−`，即時寫回 `owned`（小 JSON endpoint）。
2. **Meta**：兩張統計卡（總活動 / 總參賽）＋ 甜甜圈（toggle）＋ 可排序活動表（活動 / 冠軍 / 人數）。頂部「獲取數據」吃日期範圍 + 最小人數。
3. **牌組（核心）**：把一副牌渲染成**一張張單卡**（圖片走 §8 代理）；疊上 diff：缺卡標紅 + 差幾張；顯示該副補完成本。
4. **排序**：全部 meta 牌組依「我的補完成本」升冪列；點開即頁面 3。

## 8. 圖片代理

後端開 `/img/{card_number}`：依卡號組出官方圖 URL，加 `Referer: https://decklog.bushiroad.com/` 抓回、存本地磁碟快取；前端只指此路徑。解決防盜連 404 與重複抓取。

## 9. 錯誤處理與快取

- DeckLog 回 `[]` → 該副標「無法取得」，meta 計數略過並註記。
- Bushi-Navi 隱藏期 → 顯示「牌組於 {日期} 後公開」。
- yuyu-tei 查無價 → 成本顯示 `?`，可在 `prices` 手動填（`is_manual=true`）。
- 快取策略：牌組/賽果**永久快取**（內容不可變）；價格 **TTL 日刷**；卡表**手動刷新**（新 set 時）。
- 所有爬蟲：快取優先 + 請求間 delay + 失敗 backoff；自用低頻，不高頻轟官方。

## 10. 測試策略

- `engine`（diff / 成本 / 排序 / 聚合）：TDD，純函式配 fixture。
- 四個客戶端 parser：用**錄下來的樣本回應**測，不打 live（deterministic、不轟官方）。
- 一條 end-to-end smoke：已知牌組碼 → 拆解 → diff，跑在 fixture 上。

## 11. 刻意不做（YAGNI，v1 範圍外）

- 帳號 / 多人 / 權限。
- 即時更新 / 推播。
- 英文版（全程 JP）。
- fork 開源 deckbuilder（授權有雷，且核心功能本來就得自寫）。

## 12. 未來可能（不在 v1）

- 價格歷史走勢。
- 收藏匯入 / 匯出。
- 「一鍵把某副 meta 牌加進我的目標清單」。

## 13. 已驗證的關鍵假設（為何可行）

- DeckLog 確切 endpoint、POST + body + Referer 需求、回應含 `card_number`：實測確認。
- Bushi-Navi 公開賽果 API、`X-Accept-Version: v1` 眉角、`grouped_rankings` 帶牌組碼：實測確認。
- yuyu-tei 列表含官方卡號 + 日幣價、精準對號：實測確認（`/sell/sev/s/bp06`）。
- 日版卡表可爬、DOM 固定、卡號與上述對齊：實測確認。
- 四邊主鍵均為 JP `card_number`，無需英日映射：確認。
