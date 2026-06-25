# SVE Meta 收藏差距工具 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一個自架的 Flask 網站，抓 Shadowverse Evolve 線下賽 meta、把每副入賞牌以單張卡呈現、對照我的收藏算出「差哪些卡」與「補完成本」，並依成本排序。

**Architecture:** 單一 Flask app + 單一 SQLite 檔。三個爬蟲（Bushi-Navi API、DeckLog API、yuyu-tei + 官方卡表 HTML）把官方資料抓進 SQLite 快取表；頁面只讀本地快取。純函式運算層（diff / 成本 / 排序 / 聚合）與 I/O 完全分離，方便 TDD。主鍵全用日版 `card_number`（如 `BP07-007`），四邊天然對齊。

**Tech Stack:** Python 3.11+、Flask、requests、beautifulsoup4、pytest。資料庫用 stdlib `sqlite3`（不引 ORM）。

---

## 重要前提

- **Git 目前停用（依使用者偏好）。** 每個 Task 結尾的「Checkpoint」step 只跑該模組測試；不執行 `git commit`。日後啟用 git 時，把每個 Checkpoint 當成一次 commit。
- **不打 live 測試。** 所有 parser 測試吃「事先抓好存進 `tests/fixtures/` 的樣本」，deterministic 且不轟官方。每個需要 fixture 的 Task 第一步都附 `curl` 抓取指令。
- **快取優先 + delay。** 爬蟲一律先查 SQLite 快取；牌組/賽果永久快取，價格 TTL 日刷，卡表手動刷。每次對外請求間隔 `config.REQUEST_DELAY` 秒。

## 檔案結構

```
Shadowverse/
  requirements.txt
  run.py                       # 進入點：flask app 啟動
  conftest.py                  # pytest fixtures（conn）+ 確保專案根在 sys.path
  sve_meta/
    __init__.py
    config.py                  # 常數：hosts / headers / paths / delay
    db.py                      # sqlite 連線 + 建表
    classmap.py                # deck_param1 → 七職正規化
    engine.py                  # 純函式：missing / cost / rank / aggregate
    collection.py              # owned CRUD
    decklog.py                 # 牌組碼 → 單卡（parse + fetch + cache）
    bushinavi.py               # 賽果 API（parse + fetch + cache）
    prices.py                  # yuyu-tei 價格（parse + store + manual）
    cardmaster.py              # 官方卡表（parse + store）
    imgproxy.py                # 卡圖 URL 推導 + 帶 Referer 抓取快取
    web.py                     # Flask app + 路由
    templates/
      base.html  collection.html  meta.html  deck.html  ranking.html
    static/
      app.js  style.css
  tests/
    fixtures/                  # 樣本回應（curl 抓）
    test_engine.py  test_classmap.py  test_collection.py
    test_decklog.py  test_bushinavi.py  test_prices.py
    test_cardmaster.py  test_imgproxy.py  test_web.py  test_integration.py
```

每個模組對外只回乾淨 Python 結構；HTTP/分頁/重試細節封在模組內。

---

## Task 0: 專案骨架 + 資料庫

**Files:**
- Create: `requirements.txt`
- Create: `sve_meta/__init__.py`（空）
- Create: `sve_meta/config.py`
- Create: `sve_meta/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: 建 requirements.txt**

```
Flask==3.0.3
requests==2.32.3
beautifulsoup4==4.12.3
pytest==8.2.0
```

- [ ] **Step 2: 裝相依**

Run: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
Expected: 安裝成功，`python -c "import flask, requests, bs4, pytest"` 無錯。

- [ ] **Step 3: 寫 config.py**

```python
# sve_meta/config.py
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "sve_meta.db"
IMG_CACHE_DIR = ROOT / "img_cache"

GAME_TITLE_ID_SVE = 6
REQUEST_DELAY = 1.0  # 秒，對外請求間隔
PRICE_TTL_SECONDS = 24 * 3600

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

BUSHINAVI_API = "https://api-user.bushi-navi.com"
BUSHINAVI_HEADERS = {"X-Accept-Version": "v1", "User-Agent": USER_AGENT}

DECKLOG_VIEW_API = "https://decklog.bushiroad.com/system/app/api/view/{code}"
DECKLOG_REFERER = "https://decklog.bushiroad.com/view/{code}"
DECKLOG_IMG_BASE = "https://shadowverse-evolve.com/wordpress/wp-content/images/cardlist/"
DECKLOG_IMG_REFERER = "https://decklog.bushiroad.com/"

YUYUTEI_SET_URL = "https://yuyu-tei.jp/sell/sev/s/{set}"
CARDLIST_URL = "https://shadowverse-evolve.com/cardlist/cardsearch/?expansion={set}&view=text"
```

- [ ] **Step 4: 寫 db.py（建表）**

```python
# sve_meta/db.py
import sqlite3
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
  card_number TEXT PRIMARY KEY, name TEXT, class TEXT, type TEXT,
  cost TEXT, atk TEXT, def TEXT, set_code TEXT, rarity TEXT, img TEXT
);
CREATE TABLE IF NOT EXISTS owned (
  card_number TEXT PRIMARY KEY, qty INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS prices (
  card_number TEXT PRIMARY KEY, jpy INTEGER, fetched_at REAL,
  source TEXT, is_manual INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS decks (
  code TEXT PRIMARY KEY, game_title_id INTEGER, class TEXT,
  list_json TEXT, fetched_at REAL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, title TEXT, store TEXT, pref TEXT,
  players INTEGER, start_date TEXT, rankings_json TEXT, fetched_at REAL
);
"""

def get_conn(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()
```

- [ ] **Step 5: 寫 conftest.py（專案根，提供 conn fixture）**

放在「專案根目錄」（與 `tests/` 同層）。pytest 會自動載入，並把專案根加入 `sys.path`，讓測試能 `import sve_meta`。各測試檔自行用 `FIXTURES = Path(__file__).parent / "fixtures"` 取樣本路徑。

```python
# conftest.py（專案根）
import pytest
from sve_meta import db

@pytest.fixture
def conn():
    c = db.get_conn(":memory:")
    db.init_db(c)
    yield c
    c.close()
```

- [ ] **Step 6: 寫失敗測試**

```python
# tests/test_db.py
def test_init_db_creates_tables(conn):
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"cards", "owned", "prices", "decks", "events"} <= names
```

- [ ] **Step 7: 跑測試確認通過**

Run: `. .venv/bin/activate && pytest tests/test_db.py -v`
Expected: PASS。

- [ ] **Step 8: Checkpoint** — `pytest -q` 全綠（目前只有 test_db）。

---

## Task 1: engine.missing（差距）

**Files:**
- Create: `sve_meta/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_engine.py
from sve_meta import engine

DECK = [{"card_number": "BP07-007", "num": 3},
        {"card_number": "BP07-010", "num": 2}]

def test_missing_counts_shortfall():
    owned = {"BP07-007": 1}  # 沒有 BP07-010
    assert engine.missing(DECK, owned) == {"BP07-007": 2, "BP07-010": 2}

def test_missing_empty_when_fully_owned():
    owned = {"BP07-007": 3, "BP07-010": 2}
    assert engine.missing(DECK, owned) == {}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL（`module 'engine' has no attribute 'missing'`）。

- [ ] **Step 3: 實作 missing**

```python
# sve_meta/engine.py
def missing(deck, owned):
    """deck: [{'card_number','num'}], owned: {cn: qty} -> {cn: shortfall>0}"""
    out = {}
    for item in deck:
        cn, need = item["card_number"], item["num"]
        have = owned.get(cn, 0)
        if need > have:
            out[cn] = need - have
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_engine.py -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_engine.py -q` 全綠。

---

## Task 2: engine.completion_cost（補完成本 + 未定價清單）

**Files:**
- Modify: `sve_meta/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_engine.py（追加）
def test_completion_cost_sums_missing_times_price():
    owned = {"BP07-007": 1}
    prices = {"BP07-007": 300, "BP07-010": 500}
    total, unpriced = engine.completion_cost(DECK, owned, prices)
    assert total == 2 * 300 + 2 * 500
    assert unpriced == []

def test_completion_cost_flags_unpriced():
    owned = {}
    prices = {"BP07-007": 300}  # 缺 BP07-010 的價
    total, unpriced = engine.completion_cost(DECK, owned, prices)
    assert total == 3 * 300
    assert unpriced == ["BP07-010"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_engine.py -k completion_cost -v`
Expected: FAIL。

- [ ] **Step 3: 實作 completion_cost**

```python
# sve_meta/engine.py（追加）
def completion_cost(deck, owned, prices):
    """回傳 (總日幣, 未定價卡號清單)。未定價的卡不計入總額。"""
    total = 0
    unpriced = []
    for cn, shortfall in missing(deck, owned).items():
        price = prices.get(cn)
        if price is None:
            unpriced.append(cn)
        else:
            total += shortfall * price
    return total, unpriced
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_engine.py -k completion_cost -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_engine.py -q` 全綠。

---

## Task 3: classmap.normalize_class（職業正規化）

**Files:**
- Create: `sve_meta/classmap.py`
- Test: `tests/test_classmap.py`

說明：Bushi-Navi 的 `deck_param1` 是職業/leader 字串。原站甜甜圈會混進聯動 leader title，本模組把它收斂回基礎職業。`BASE_CLASSES` 是 SVE 七職；`LEADER_TO_CLASS` 是已知聯動/別名對照（seed，之後遇到新 leader 再補）。未知字串原樣回傳（不靜默丟棄，便於發現缺漏）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_classmap.py
from sve_meta import classmap

def test_base_class_passthrough():
    assert classmap.normalize_class("ロイヤル") == "ロイヤル"
    assert classmap.normalize_class("ウィッチ") == "ウィッチ"

def test_known_leader_maps_to_base_class():
    # 聯動 leader 收斂回基礎職業（範例 seed）
    assert classmap.normalize_class("シンデレラガールズ") == "ニュートラル"

def test_unknown_returns_input():
    assert classmap.normalize_class("謎のリーダー") == "謎のリーダー"

def test_blank_returns_unknown_label():
    assert classmap.normalize_class("") == "不明"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_classmap.py -v`
Expected: FAIL。

- [ ] **Step 3: 實作 classmap**

```python
# sve_meta/classmap.py
BASE_CLASSES = {
    "エルフ", "ロイヤル", "ウィッチ", "ドラゴン",
    "ネクロマンサー", "ヴァンパイア", "ビショップ", "ネメシス", "ニュートラル",
}

# 聯動/別名 leader → 基礎職業（seed，依實際 deck_param1 持續擴充）
LEADER_TO_CLASS = {
    "シンデレラガールズ": "ニュートラル",
    "ウマ娘": "ニュートラル",
    "プリコネ": "ニュートラル",
}

def normalize_class(deck_param1):
    s = (deck_param1 or "").strip()
    if not s:
        return "不明"
    if s in BASE_CLASSES:
        return s
    if s in LEADER_TO_CLASS:
        return LEADER_TO_CLASS[s]
    return s  # 未知：原樣回傳，方便日後補進對照表
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_classmap.py -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_classmap.py -q` 全綠。

---

## Task 4: engine.aggregate_meta（聚合甜甜圈資料）

**Files:**
- Modify: `sve_meta/engine.py`
- Test: `tests/test_engine.py`

事件結構約定：`event = {"event_id","title","store","players","start_date", "rankings": [{"rank","player","class","deck_code"}]}`。`scope` ∈ {"top8","first"}。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_engine.py（追加）
EVENTS = [
    {"event_id": "1", "players": 20, "rankings": [
        {"rank": 1, "class": "ロイヤル", "deck_code": "A"},
        {"rank": 2, "class": "ウィッチ", "deck_code": "B"},
        {"rank": 3, "class": "ロイヤル", "deck_code": "C"}]},
    {"event_id": "2", "players": 10, "rankings": [
        {"rank": 1, "class": "ウマ娘", "deck_code": "D"}]},
]

def test_aggregate_top8_counts_all_rankings_normalized():
    agg = engine.aggregate_meta(EVENTS, scope="top8")
    assert agg["total_events"] == 2
    assert agg["total_players"] == 30
    assert agg["counts"]["ロイヤル"] == 2
    assert agg["counts"]["ウィッチ"] == 1
    assert agg["counts"]["ニュートラル"] == 1  # ウマ娘 正規化
    assert len(agg["decks"]) == 4

def test_aggregate_first_only_counts_rank1():
    agg = engine.aggregate_meta(EVENTS, scope="first")
    assert agg["counts"] == {"ロイヤル": 1, "ニュートラル": 1}
    assert len(agg["decks"]) == 2
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_engine.py -k aggregate -v`
Expected: FAIL。

- [ ] **Step 3: 實作 aggregate_meta**

```python
# sve_meta/engine.py（檔首追加）
from collections import Counter
from .classmap import normalize_class

# sve_meta/engine.py（函式追加）
def aggregate_meta(events, scope="top8"):
    counts = Counter()
    decks = []
    total_players = 0
    for ev in events:
        total_players += ev.get("players", 0)
        for r in ev.get("rankings", []):
            if scope == "first" and r.get("rank") != 1:
                continue
            cls = normalize_class(r.get("class"))
            counts[cls] += 1
            decks.append({"event_id": ev["event_id"], "rank": r.get("rank"),
                          "class": cls, "deck_code": r.get("deck_code")})
    return {"total_events": len(events), "total_players": total_players,
            "counts": dict(counts), "decks": decks}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_engine.py -k aggregate -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_engine.py -q` 全綠。

---

## Task 5: engine.rank_decks（依補完成本排序）

**Files:**
- Modify: `sve_meta/engine.py`
- Test: `tests/test_engine.py`

deck 結構：`{"deck_code","class","list":[{"card_number","num"}]}`。回傳每副附上 `cost / missing / unpriced`，依 cost 升冪；未定價卡多者次序穩定（cost 相同時依 unpriced 數、再依 deck_code）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_engine.py（追加）
def test_rank_decks_ascending_by_cost():
    decks = [
        {"deck_code": "X", "class": "ロイヤル",
         "list": [{"card_number": "BP07-007", "num": 3}]},
        {"deck_code": "Y", "class": "ウィッチ",
         "list": [{"card_number": "BP07-010", "num": 1}]},
    ]
    owned = {}
    prices = {"BP07-007": 100, "BP07-010": 50}
    ranked = engine.rank_decks(decks, owned, prices)
    assert [d["deck_code"] for d in ranked] == ["Y", "X"]  # 50 < 300
    assert ranked[0]["cost"] == 50
    assert ranked[1]["missing"] == {"BP07-007": 3}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_engine.py -k rank -v`
Expected: FAIL。

- [ ] **Step 3: 實作 rank_decks**

```python
# sve_meta/engine.py（追加）
def rank_decks(decks, owned, prices):
    annotated = []
    for d in decks:
        miss = missing(d["list"], owned)
        cost, unpriced = completion_cost(d["list"], owned, prices)
        annotated.append({**d, "cost": cost, "missing": miss, "unpriced": unpriced})
    annotated.sort(key=lambda d: (d["cost"], len(d["unpriced"]), d["deck_code"]))
    return annotated
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_engine.py -k rank -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_engine.py -q` 全綠（engine 完成）。

---

## Task 6: collection store（收藏讀寫）

**Files:**
- Create: `sve_meta/collection.py`
- Test: `tests/test_collection.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_collection.py
from sve_meta import collection

def test_set_and_get_owned(conn):
    collection.set_owned(conn, "BP07-007", 2)
    assert collection.get_owned(conn) == {"BP07-007": 2}

def test_set_owned_clamps_0_to_3(conn):
    collection.set_owned(conn, "BP07-007", 9)
    collection.set_owned(conn, "BP07-010", -5)
    owned = collection.get_owned(conn)
    assert owned["BP07-007"] == 3
    assert owned["BP07-010"] == 0

def test_get_owned_excludes_zero(conn):
    collection.set_owned(conn, "BP07-007", 0)
    assert "BP07-007" not in collection.get_owned(conn)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_collection.py -v`
Expected: FAIL。

- [ ] **Step 3: 實作 collection**

```python
# sve_meta/collection.py
def set_owned(conn, card_number, qty):
    qty = max(0, min(3, int(qty)))
    conn.execute(
        "INSERT INTO owned(card_number, qty) VALUES(?,?) "
        "ON CONFLICT(card_number) DO UPDATE SET qty=excluded.qty",
        (card_number, qty))
    conn.commit()

def get_owned(conn):
    """只回 qty>0 的卡。"""
    rows = conn.execute("SELECT card_number, qty FROM owned WHERE qty>0")
    return {r["card_number"]: r["qty"] for r in rows}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_collection.py -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_collection.py -q` 全綠。

---

## Task 7: decklog（牌組碼 → 單卡，含快取）

**Files:**
- Create: `sve_meta/decklog.py`
- Test: `tests/test_decklog.py`
- Fixture: `tests/fixtures/decklog_6DBH1.json`

- [ ] **Step 1: 抓 fixture**

Run:
```bash
mkdir -p tests/fixtures
curl -s -X POST "https://decklog.bushiroad.com/system/app/api/view/6DBH1" \
  -H "Content-Type: application/json" \
  -H "Referer: https://decklog.bushiroad.com/view/6DBH1" \
  -d '{}' -o tests/fixtures/decklog_6DBH1.json
python3 -c "import json;d=json.load(open('tests/fixtures/decklog_6DBH1.json'));print(d['game_title_id'], d['list'][0]['card_number'], d['list'][0]['num'])"
```
Expected：印出 `6 ECP02-016 3`（若官方資料有變動，以實際印出為準，並據此調整下方 assert）。

- [ ] **Step 2: 寫失敗測試（parser，純函式）**

```python
# tests/test_decklog.py
import json
from pathlib import Path
from sve_meta import decklog

FIXTURES = Path(__file__).parent / "fixtures"

def _payload():
    return json.load(open(FIXTURES / "decklog_6DBH1.json", encoding="utf-8"))

def test_parse_deck_extracts_card_list():
    deck = decklog.parse_deck(_payload())
    assert deck["game_title_id"] == 6
    items = {i["card_number"]: i["num"] for i in deck["list"]}
    assert items["ECP02-016"] == 3
    assert all("card_number" in i and "num" in i for i in deck["list"])

def test_parse_deck_empty_payload_returns_empty_list():
    assert decklog.parse_deck([]) == {"game_title_id": None, "class": None, "list": []}
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `pytest tests/test_decklog.py -k parse -v`
Expected: FAIL。

- [ ] **Step 4: 實作 parse_deck + fetch_deck（快取）**

```python
# sve_meta/decklog.py
import json, time, requests
from .config import DECKLOG_VIEW_API, DECKLOG_REFERER, USER_AGENT, REQUEST_DELAY

def parse_deck(payload):
    if not isinstance(payload, dict):  # 空 [] = 被刪/隱藏/過期
        return {"game_title_id": None, "class": None, "list": []}
    lst = [{"card_number": i.get("card_number"), "num": i.get("num")}
           for i in payload.get("list", [])]
    return {"game_title_id": payload.get("game_title_id"),
            "class": payload.get("deck_param1"), "list": lst}

def _http_post(code):
    time.sleep(REQUEST_DELAY)
    r = requests.post(DECKLOG_VIEW_API.format(code=code),
                      headers={"Content-Type": "application/json",
                               "User-Agent": USER_AGENT,
                               "Referer": DECKLOG_REFERER.format(code=code)},
                      json={}, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_deck(conn, code, poster=_http_post):
    """先查快取；未命中才打官方。牌組內容不可變 → 永久快取。"""
    row = conn.execute("SELECT game_title_id, class, list_json FROM decks "
                       "WHERE code=?", (code,)).fetchone()
    if row:
        return {"game_title_id": row["game_title_id"], "class": row["class"],
                "list": json.loads(row["list_json"])}
    deck = parse_deck(poster(code))
    conn.execute("INSERT OR REPLACE INTO decks"
                 "(code, game_title_id, class, list_json, fetched_at) "
                 "VALUES(?,?,?,?,?)",
                 (code, deck["game_title_id"], deck["class"],
                  json.dumps(deck["list"]), time.time()))
    conn.commit()
    return deck
```

- [ ] **Step 5: 跑 parser 測試確認通過**

Run: `pytest tests/test_decklog.py -k parse -v`
Expected: PASS。

- [ ] **Step 6: 寫 fetch 快取測試（注入假 poster，不打 live）**

```python
# tests/test_decklog.py（追加）
def test_fetch_deck_uses_cache_and_calls_once(conn):
    calls = {"n": 0}
    def fake_poster(code):
        calls["n"] += 1
        return {"game_title_id": 6, "deck_param1": "ロイヤル",
                "list": [{"card_number": "BP07-007", "num": 3}]}
    d1 = decklog.fetch_deck(conn, "ZZZ1", poster=fake_poster)
    d2 = decklog.fetch_deck(conn, "ZZZ1", poster=fake_poster)
    assert d1["list"][0]["card_number"] == "BP07-007"
    assert d2 == d1
    assert calls["n"] == 1  # 第二次走快取
```

- [ ] **Step 7: 跑測試確認通過**

Run: `pytest tests/test_decklog.py -v`
Expected: PASS。

- [ ] **Step 8: Checkpoint** — `pytest tests/test_decklog.py -q` 全綠。

---

## Task 8: bushinavi（賽果 API，含分頁與快取）

**Files:**
- Create: `sve_meta/bushinavi.py`
- Test: `tests/test_bushinavi.py`
- Fixture: `tests/fixtures/bushinavi_list.json`, `tests/fixtures/bushinavi_detail.json`

- [ ] **Step 1: 抓 fixtures**

Run:
```bash
curl -s "https://api-user.bushi-navi.com/api/user/event/result/list?game_title_id[]=6&limit=5&offset=0" \
  -H "X-Accept-Version: v1" -o tests/fixtures/bushinavi_list.json
curl -s "https://api-user.bushi-navi.com/api/user/event/result/detail/757517" \
  -H "X-Accept-Version: v1" -o tests/fixtures/bushinavi_detail.json
python3 -c "import json;d=json.load(open('tests/fixtures/bushinavi_detail.json'));print(d['success']['joined_player_count'])"
```
Expected：detail 印出參賽人數（範例事件約 15）。檢視兩個 JSON 的實際 key 路徑，必要時調整下方 parser 取值路徑。

- [ ] **Step 2: 寫失敗測試（兩個 parser，純函式）**

```python
# tests/test_bushinavi.py
import json
from pathlib import Path
from sve_meta import bushinavi

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_event_list_returns_rows_with_players():
    payload = json.load(open(FIXTURES / "bushinavi_list.json", encoding="utf-8"))
    rows = bushinavi.parse_event_list(payload)
    assert len(rows) >= 1
    r = rows[0]
    assert set(["event_id", "title", "store", "players", "start_date"]) <= set(r)
    assert isinstance(r["players"], int)

def test_parse_event_detail_returns_rankings_with_deck_codes():
    payload = json.load(open(FIXTURES / "bushinavi_detail.json", encoding="utf-8"))
    detail = bushinavi.parse_event_detail(payload)
    assert detail["players"] >= 1
    top = detail["rankings"][0]
    assert set(["rank", "player", "class", "deck_code"]) <= set(top)
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `pytest tests/test_bushinavi.py -k parse -v`
Expected: FAIL。

- [ ] **Step 4: 實作 parsers + fetch_events**

```python
# sve_meta/bushinavi.py
import time, requests
from .config import (BUSHINAVI_API, BUSHINAVI_HEADERS,
                     GAME_TITLE_ID_SVE, REQUEST_DELAY)

def parse_event_list(payload):
    events = payload.get("success", {}).get("events", []) or payload.get("events", [])
    out = []
    for e in events:
        out.append({
            "event_id": str(e.get("event_id")),
            "title": e.get("event_title"),
            "store": e.get("place"),
            "pref": e.get("pref_code"),
            "players": int(e.get("joined_player_count") or 0),
            "start_date": e.get("start_datetime"),
        })
    return out

def parse_event_detail(payload):
    s = payload.get("success", payload)
    players = int(s.get("joined_player_count") or 0)
    rankings = []
    grouped = s.get("grouped_rankings", {}) or {}
    for entry in grouped.values():
        rank = entry.get("rank")
        for m in entry.get("team_member", []):
            rankings.append({
                "rank": rank,
                "player": m.get("player_name"),
                "class": m.get("deck_param1"),
                "deck_code": m.get("deck_recipe_id"),
            })
    rankings.sort(key=lambda r: (r["rank"] is None, r["rank"]))
    return {"players": players, "rankings": rankings}

def _get(url):
    time.sleep(REQUEST_DELAY)
    r = requests.get(url, headers=BUSHINAVI_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_events(start, end, min_players, limit=50, getter=_get):
    """走 list 分頁 → client 端依 players 過濾 → 逐筆抓 detail 併入 rankings。"""
    collected, offset = [], 0
    while True:
        url = (f"{BUSHINAVI_API}/api/user/event/result/list"
               f"?game_title_id[]={GAME_TITLE_ID_SVE}"
               f"&start_date={start}&end_date={end}&limit={limit}&offset={offset}")
        rows = parse_event_list(getter(url))
        if not rows:
            break
        collected.extend(rows)
        offset += limit
    events = []
    for ev in collected:
        if ev["players"] < min_players:
            continue
        detail = parse_event_detail(
            getter(f"{BUSHINAVI_API}/api/user/event/result/detail/{ev['event_id']}"))
        events.append({**ev, "players": detail["players"] or ev["players"],
                       "rankings": detail["rankings"]})
    return events
```

- [ ] **Step 5: 跑 parser 測試確認通過**

Run: `pytest tests/test_bushinavi.py -k parse -v`
Expected: PASS。

- [ ] **Step 6: 寫 fetch_events 測試（注入假 getter）**

```python
# tests/test_bushinavi.py（追加）
def test_fetch_events_filters_by_min_players():
    pages = {0: {"success": {"events": [
                 {"event_id": 1, "event_title": "A", "place": "店1",
                  "pref_code": "G", "joined_player_count": 20, "start_datetime": "2026-06-01"},
                 {"event_id": 2, "event_title": "B", "place": "店2",
                  "pref_code": "G", "joined_player_count": 5, "start_datetime": "2026-06-02"}]}},
             50: {"success": {"events": []}}}
    detail = {"success": {"joined_player_count": 20, "grouped_rankings": {
                 "t1": {"rank": 1, "team_member": [
                     {"player_name": "p", "deck_param1": "ロイヤル", "deck_recipe_id": "AAA"}]}}}}
    def fake_getter(url):
        if "/list" in url:
            off = 50 if "offset=50" in url else 0
            return pages[off]
        return detail
    events = bushinavi.fetch_events("2026-06-01", "2026-06-30", min_players=10,
                                    getter=fake_getter)
    assert [e["event_id"] for e in events] == ["1"]      # 5 人那場被濾掉
    assert events[0]["rankings"][0]["deck_code"] == "AAA"
```

- [ ] **Step 7: 跑測試確認通過**

Run: `pytest tests/test_bushinavi.py -v`
Expected: PASS。

- [ ] **Step 8: Checkpoint** — `pytest tests/test_bushinavi.py -q` 全綠。

---

## Task 9: prices（yuyu-tei 價格，含手動覆寫）

**Files:**
- Create: `sve_meta/prices.py`
- Test: `tests/test_prices.py`
- Fixture: `tests/fixtures/yuyutei_bp06.html`

yuyu-tei 結構（已實測）：每張卡是 `div.card-product`；卡號在 `span.d-block.border.border-dark`（如 `BP06-SP01`），名稱在 `h4`，價格在 `strong.d-block.text-end`（如 `9,980 円`）。一張卡可能有「正常/傷あり」兩個價，取**第一個**（正常價）。

- [ ] **Step 1: 抓 fixture**

Run:
```bash
curl -s -A "Mozilla/5.0" "https://yuyu-tei.jp/sell/sev/s/bp06" -o tests/fixtures/yuyutei_bp06.html
python3 -c "print(open('tests/fixtures/yuyutei_bp06.html',encoding='utf-8',errors='replace').count('card-product'))"
```
Expected：印出約 200（卡片區塊數）。

- [ ] **Step 2: 寫失敗測試（parser，純函式）**

```python
# tests/test_prices.py
from pathlib import Path
from sve_meta import prices

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_prices_extracts_code_and_jpy():
    html = open(FIXTURES / "yuyutei_bp06.html", encoding="utf-8", errors="replace").read()
    table = prices.parse_prices(html)
    assert table["BP06-SP01"] == 9980        # 第一張，正常價
    assert all(isinstance(v, int) for v in table.values())
    assert len(table) >= 150                  # 一個 set 應有上百張
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `pytest tests/test_prices.py -k parse -v`
Expected: FAIL。

- [ ] **Step 4: 實作 parse_prices + store + 手動覆寫**

```python
# sve_meta/prices.py
import re, time, requests
from bs4 import BeautifulSoup
from .config import YUYUTEI_SET_URL, USER_AGENT, REQUEST_DELAY, PRICE_TTL_SECONDS

def parse_prices(html):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for block in soup.select("div.card-product"):
        code_el = block.select_one("span.border")
        price_el = block.select_one("strong")
        if not code_el or not price_el:
            continue
        code = code_el.get_text(strip=True)
        m = re.search(r"[\d,]+", price_el.get_text())
        if not code or not m:
            continue
        out[code] = int(m.group(0).replace(",", ""))
    return out

def _fetch_html(set_code):
    time.sleep(REQUEST_DELAY)
    r = requests.get(YUYUTEI_SET_URL.format(set=set_code),
                     headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.text

def refresh_set(conn, set_code, fetcher=_fetch_html):
    now = time.time()
    for cn, jpy in parse_prices(fetcher(set_code)).items():
        # 不覆蓋手動價
        row = conn.execute("SELECT is_manual FROM prices WHERE card_number=?",
                           (cn,)).fetchone()
        if row and row["is_manual"]:
            continue
        conn.execute("INSERT OR REPLACE INTO prices"
                     "(card_number, jpy, fetched_at, source, is_manual) "
                     "VALUES(?,?,?,?,0)", (cn, jpy, now, f"yuyu-tei:{set_code}"))
    conn.commit()

def get_price(conn, card_number):
    row = conn.execute("SELECT jpy FROM prices WHERE card_number=?",
                       (card_number,)).fetchone()
    return row["jpy"] if row else None

def get_all(conn):
    return {r["card_number"]: r["jpy"]
            for r in conn.execute("SELECT card_number, jpy FROM prices")}

def set_manual(conn, card_number, jpy):
    conn.execute("INSERT OR REPLACE INTO prices"
                 "(card_number, jpy, fetched_at, source, is_manual) "
                 "VALUES(?,?,?,?,1)", (card_number, int(jpy), time.time(), "manual"))
    conn.commit()
```

- [ ] **Step 5: 跑 parser 測試確認通過**

Run: `pytest tests/test_prices.py -k parse -v`
Expected: PASS。

- [ ] **Step 6: 寫 store / 手動覆寫測試**

```python
# tests/test_prices.py（追加）
def test_refresh_and_manual_override(conn):
    def fake_fetch(set_code):
        return ('<div class="card-product"><span class="border">BP06-001</span>'
                '<strong>320 円</strong></div>')
    prices.refresh_set(conn, "bp06", fetcher=fake_fetch)
    assert prices.get_price(conn, "BP06-001") == 320
    prices.set_manual(conn, "BP06-001", 999)
    prices.refresh_set(conn, "bp06", fetcher=fake_fetch)   # 不可覆蓋手動價
    assert prices.get_price(conn, "BP06-001") == 999
```

- [ ] **Step 7: 跑測試確認通過**

Run: `pytest tests/test_prices.py -v`
Expected: PASS。

- [ ] **Step 8: Checkpoint** — `pytest tests/test_prices.py -q` 全綠。

---

## Task 10: cardmaster（官方日版卡表）

**Files:**
- Create: `sve_meta/cardmaster.py`
- Test: `tests/test_cardmaster.py`
- Fixture: `tests/fixtures/cardlist_bp17.html`

日版卡表 DOM（已驗證）：`ul.cardlist-Result_List` 內每張卡 `p.number`（卡號）、`p.ttl`（名稱）、`div.status`（類型）、`span.status-Item-Cost/-Power/-Hp`（費用/攻/防）。

- [ ] **Step 1: 抓 fixture**

Run:
```bash
curl -s -A "Mozilla/5.0" "https://shadowverse-evolve.com/cardlist/cardsearch/?expansion=BP17&view=text" \
  -o tests/fixtures/cardlist_bp17.html
python3 -c "print(open('tests/fixtures/cardlist_bp17.html',encoding='utf-8',errors='replace').count('cardlist-Result_List'))"
```
Expected：印出 >=1。檢視一個 `p.number` 的實際卡號（如 `BP17-001`），據此設定下方 assert。

- [ ] **Step 2: 寫失敗測試（parser）**

```python
# tests/test_cardmaster.py
from pathlib import Path
from sve_meta import cardmaster

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_cardlist_extracts_cards():
    html = open(FIXTURES / "cardlist_bp17.html", encoding="utf-8", errors="replace").read()
    cards = cardmaster.parse_cardlist(html)
    assert len(cards) >= 1
    c = cards[0]
    assert c["card_number"].startswith("BP17-")
    assert c["name"]
    assert set(["card_number", "name", "type", "cost", "atk", "def"]) <= set(c)
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `pytest tests/test_cardmaster.py -k parse -v`
Expected: FAIL。

- [ ] **Step 4: 實作 parse_cardlist + store**

```python
# sve_meta/cardmaster.py
import time, requests
from bs4 import BeautifulSoup
from .config import CARDLIST_URL, USER_AGENT, REQUEST_DELAY

def _txt(el):
    return el.get_text(strip=True) if el else ""

def parse_cardlist(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for ul in soup.select("ul.cardlist-Result_List"):
        for li in ul.select("li"):
            num = li.select_one("p.number")
            if not num:
                continue
            code = _txt(num)
            cards.append({
                "card_number": code,
                "name": _txt(li.select_one("p.ttl")),
                "type": _txt(li.select_one("div.status")),
                "cost": _txt(li.select_one("span.status-Item-Cost")),
                "atk": _txt(li.select_one("span.status-Item-Power")),
                "def": _txt(li.select_one("span.status-Item-Hp")),
                "set_code": code.split("-")[0] if "-" in code else "",
            })
    return cards

def _fetch_html(set_code):
    time.sleep(REQUEST_DELAY)
    r = requests.get(CARDLIST_URL.format(set=set_code),
                     headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.text

def refresh_set(conn, set_code, fetcher=_fetch_html):
    for c in parse_cardlist(fetcher(set_code)):
        conn.execute(
            "INSERT OR REPLACE INTO cards"
            "(card_number, name, class, type, cost, atk, def, set_code, rarity, img) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (c["card_number"], c["name"], c.get("class", ""), c["type"],
             c["cost"], c["atk"], c["def"], c["set_code"], c.get("rarity", ""),
             c.get("img", "")))
    conn.commit()

def get(conn, card_number):
    row = conn.execute("SELECT * FROM cards WHERE card_number=?",
                       (card_number,)).fetchone()
    return dict(row) if row else None

def by_set(conn):
    out = {}
    for r in conn.execute("SELECT * FROM cards ORDER BY set_code, card_number"):
        out.setdefault(r["set_code"], []).append(dict(r))
    return out
```

- [ ] **Step 5: 跑 parser 測試確認通過**

Run: `pytest tests/test_cardmaster.py -k parse -v`
Expected: PASS（若 DOM 與預期不同，依實際 fixture 調整 selector 後再綠）。

- [ ] **Step 6: 寫 store 測試（注入假 fetcher）**

```python
# tests/test_cardmaster.py（追加）
def test_refresh_set_stores_cards(conn):
    def fake_fetch(set_code):
        return ('<ul class="cardlist-Result_List"><li>'
                '<p class="number">BP17-001</p><p class="ttl">テスト</p>'
                '<div class="status">フォロワー</div>'
                '<span class="status-Item-Cost">2</span>'
                '<span class="status-Item-Power">2</span>'
                '<span class="status-Item-Hp">2</span></li></ul>')
    cardmaster.refresh_set(conn, "BP17", fetcher=fake_fetch)
    c = cardmaster.get(conn, "BP17-001")
    assert c["name"] == "テスト" and c["set_code"] == "BP17"
    assert "BP17" in cardmaster.by_set(conn)
```

- [ ] **Step 7: 跑測試確認通過**

Run: `pytest tests/test_cardmaster.py -v`
Expected: PASS。

- [ ] **Step 8: Checkpoint** — `pytest tests/test_cardmaster.py -q` 全綠。

---

## Task 11: imgproxy（卡圖 URL 推導 + 帶 Referer 抓取）

**Files:**
- Create: `sve_meta/imgproxy.py`
- Test: `tests/test_imgproxy.py`

卡號 → 圖路徑：`BP07-007` → set `BP07`、檔名小寫 `bp07-007.png` → `DECKLOG_IMG_BASE + "BP07/bp07-007.png"`。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_imgproxy.py
from sve_meta import imgproxy

def test_image_url_for_derives_path():
    url = imgproxy.image_url_for("BP07-007")
    assert url.endswith("/BP07/bp07-007.png")

def test_fetch_image_sends_referer_and_caches(tmp_path):
    calls = []
    def fake_getter(url, headers):
        calls.append(headers.get("Referer"))
        return b"PNGDATA"
    p1 = imgproxy.fetch_image("BP07-007", cache_dir=tmp_path, getter=fake_getter)
    p2 = imgproxy.fetch_image("BP07-007", cache_dir=tmp_path, getter=fake_getter)
    assert p1.read_bytes() == b"PNGDATA"
    assert p2 == p1
    assert len(calls) == 1                       # 第二次走磁碟快取
    assert calls[0] == "https://decklog.bushiroad.com/"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_imgproxy.py -v`
Expected: FAIL。

- [ ] **Step 3: 實作 imgproxy**

```python
# sve_meta/imgproxy.py
import time, requests
from pathlib import Path
from .config import (DECKLOG_IMG_BASE, DECKLOG_IMG_REFERER, USER_AGENT,
                     IMG_CACHE_DIR, REQUEST_DELAY)

def image_url_for(card_number):
    set_code = card_number.split("-")[0]
    return f"{DECKLOG_IMG_BASE}{set_code}/{card_number.lower()}.png"

def _http_get(url, headers):
    time.sleep(REQUEST_DELAY)
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.content

def fetch_image(card_number, cache_dir=IMG_CACHE_DIR, getter=_http_get):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{card_number}.png"
    if path.exists():
        return path
    data = getter(image_url_for(card_number),
                  {"User-Agent": USER_AGENT, "Referer": DECKLOG_IMG_REFERER})
    path.write_bytes(data)
    return path
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_imgproxy.py -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_imgproxy.py -q` 全綠。

---

## Task 12: Flask 骨架 + 收藏頁 + 計數器 API

**Files:**
- Create: `sve_meta/web.py`
- Create: `sve_meta/templates/base.html`, `sve_meta/templates/collection.html`
- Create: `sve_meta/static/app.js`, `sve_meta/static/style.css`
- Test: `tests/test_web.py`

- [ ] **Step 1: 寫失敗測試（Flask test client）**

```python
# tests/test_web.py
import pytest
from sve_meta import web, db, collection, cardmaster

@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = tmp_path / "t.db"
    monkeypatch.setattr(web, "DB_PATH", dbfile)
    c = db.get_conn(dbfile); db.init_db(c)
    cardmaster.refresh_set(c, "BP17", fetcher=lambda s: (
        '<ul class="cardlist-Result_List"><li><p class="number">BP17-001</p>'
        '<p class="ttl">テスト</p><div class="status">フォロワー</div>'
        '<span class="status-Item-Cost">2</span>'
        '<span class="status-Item-Power">2</span>'
        '<span class="status-Item-Hp">2</span></li></ul>'))
    c.close()
    app = web.create_app(dbfile)
    app.config["TESTING"] = True
    return app.test_client()

def test_collection_page_lists_cards(client):
    r = client.get("/collection")
    assert r.status_code == 200
    assert b"BP17-001" in r.data

def test_set_owned_endpoint_persists(client):
    r = client.post("/api/owned", json={"card_number": "BP17-001", "qty": 2})
    assert r.status_code == 200 and r.get_json()["qty"] == 2
    r2 = client.get("/api/owned")
    assert r2.get_json()["BP17-001"] == 2
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_web.py -v`
Expected: FAIL。

- [ ] **Step 3: 寫 web.py（app factory + 收藏路由）**

```python
# sve_meta/web.py
from flask import Flask, render_template, request, jsonify, send_file
from .config import DB_PATH, IMG_CACHE_DIR
from . import db, collection, cardmaster, prices, decklog, bushinavi, engine, imgproxy

def create_app(db_path=DB_PATH):
    app = Flask(__name__)

    def conn():
        c = db.get_conn(db_path); db.init_db(c); return c

    @app.route("/")
    def index():
        return render_template("collection.html",
                               sets=cardmaster.by_set(conn()),
                               owned=collection.get_owned(conn()))

    @app.route("/collection")
    def collection_page():
        return index()

    @app.post("/api/owned")
    def set_owned():
        d = request.get_json()
        collection.set_owned(conn(), d["card_number"], d["qty"])
        return jsonify({"card_number": d["card_number"],
                        "qty": max(0, min(3, int(d["qty"])))})

    @app.get("/api/owned")
    def get_owned():
        return jsonify(collection.get_owned(conn()))

    return app
```

- [ ] **Step 4: 寫 base.html**

```html
<!-- sve_meta/templates/base.html -->
<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>SVE Meta Tool</title>
<link rel="stylesheet" href="/static/style.css"></head><body>
<nav><a href="/collection">收藏</a> | <a href="/meta">Meta</a>
 | <a href="/ranking">排序</a></nav>
<main>{% block body %}{% endblock %}</main>
<script src="/static/app.js"></script></body></html>
```

- [ ] **Step 5: 寫 collection.html**

```html
<!-- sve_meta/templates/collection.html -->
{% extends "base.html" %}{% block body %}
<h1>收藏</h1>
{% for set_code, cards in sets.items() %}
<section><h2>{{ set_code }}</h2><div class="grid">
{% for c in cards %}
<div class="card">
  <img src="/img/{{ c.card_number }}" alt="{{ c.card_number }}" loading="lazy">
  <div class="code">{{ c.card_number }}</div>
  <div class="counter" data-cn="{{ c.card_number }}">
    <button class="dec">−</button>
    <span class="qty">{{ owned.get(c.card_number, 0) }}</span>
    <button class="inc">＋</button>
  </div>
</div>
{% endfor %}</div></section>
{% endfor %}{% endblock %}
```

- [ ] **Step 6: 寫 app.js（計數器 0–3）**

```javascript
// sve_meta/static/app.js
document.querySelectorAll(".counter").forEach(c => {
  const cn = c.dataset.cn, span = c.querySelector(".qty");
  const save = q => fetch("/api/owned", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({card_number: cn, qty: q})})
    .then(r => r.json()).then(d => span.textContent = d.qty);
  c.querySelector(".inc").onclick = () =>
    save(Math.min(3, +span.textContent + 1));
  c.querySelector(".dec").onclick = () =>
    save(Math.max(0, +span.textContent - 1));
});
```

- [ ] **Step 7: 寫 style.css（最小）**

```css
/* sve_meta/static/style.css */
body{font-family:sans-serif;margin:1rem}
.grid{display:flex;flex-wrap:wrap;gap:.5rem}
.card{width:120px;text-align:center;font-size:.8rem}
.card img{width:100px}
.missing{outline:3px solid red}
.counter button{width:1.6rem}
```

- [ ] **Step 8: 跑測試確認通過**

Run: `pytest tests/test_web.py -v`
Expected: PASS。

- [ ] **Step 9: Checkpoint** — `pytest tests/test_web.py -q` 全綠。

---

## Task 13: Meta 頁 + 獲取數據 API

**Files:**
- Modify: `sve_meta/web.py`
- Create: `sve_meta/templates/meta.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_web.py（追加）
def test_fetch_and_meta(client, monkeypatch):
    from sve_meta import bushinavi, decklog
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: [
        {"event_id": "1", "title": "T", "store": "S", "players": 20,
         "start_date": "2026-06-01", "rankings": [
            {"rank": 1, "player": "p", "class": "ロイヤル", "deck_code": "AAA"}]}])
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id": 6, "class": "ロイヤル",
        "list": [{"card_number": "BP17-001", "num": 3}]})
    r = client.post("/api/fetch", json={"start": "2026-06-01",
                    "end": "2026-06-30", "min": 8})
    assert r.status_code == 200 and r.get_json()["events"] == 1
    meta = client.get("/meta?scope=first")
    assert "ロイヤル".encode() in meta.data       # 職業出現在甜甜圈計數
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_web.py -k fetch_and_meta -v`
Expected: FAIL。

- [ ] **Step 3: 在 web.py 加入 fetch + meta 路由**

```python
# sve_meta/web.py（在 create_app 內、return 前追加）
    EVENTS_CACHE = {"events": []}

    @app.post("/api/fetch")
    def api_fetch():
        d = request.get_json()
        events = bushinavi.fetch_events(d["start"], d["end"], int(d["min"]))
        c = conn()
        for ev in events:                       # 把每個牌組碼拆成單卡並快取
            for r in ev["rankings"]:
                if r.get("deck_code"):
                    deck = decklog.fetch_deck(c, r["deck_code"])
                    r["list"] = deck["list"]
        EVENTS_CACHE["events"] = events
        return jsonify({"events": len(events),
                        "players": sum(e["players"] for e in events)})

    @app.get("/meta")
    def meta_page():
        scope = request.args.get("scope", "top8")
        agg = engine.aggregate_meta(EVENTS_CACHE["events"], scope=scope)
        return render_template("meta.html", agg=agg, scope=scope,
                               events=EVENTS_CACHE["events"])
```

- [ ] **Step 4: 寫 meta.html**

```html
<!-- sve_meta/templates/meta.html -->
{% extends "base.html" %}{% block body %}
<h1>Meta</h1>
<form id="fetchForm">
  <input name="start" placeholder="YYYY-MM-DD">
  <input name="end" placeholder="YYYY-MM-DD">
  <input name="min" type="number" value="8" placeholder="最小人數">
  <button type="submit">獲取數據</button>
</form>
<div class="stats">總活動 {{ agg.total_events }}｜總參賽 {{ agg.total_players }}</div>
<div>
  <a href="/meta?scope=top8">前8強</a> | <a href="/meta?scope=first">第1名</a>
</div>
<ul class="counts">
{% for cls, n in agg.counts.items() %}<li>{{ cls }}: {{ n }}</li>{% endfor %}
</ul>
<table><tr><th>活動</th><th>店家</th><th>人數</th><th>牌組</th></tr>
{% for e in events %}<tr><td>{{ e.title }}</td><td>{{ e.store }}</td>
<td>{{ e.players }}</td><td>
{% for r in e.rankings %}<a href="/deck/{{ r.deck_code }}">#{{ r.rank }} {{ r.class }}</a> {% endfor %}
</td></tr>{% endfor %}</table>
<script>
document.getElementById("fetchForm").onsubmit = async ev => {
  ev.preventDefault(); const f = ev.target;
  await fetch("/api/fetch", {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({start:f.start.value, end:f.end.value, min:f.min.value})});
  location.href = "/meta";
};
</script>{% endblock %}
```

- [ ] **Step 5: 跑測試確認通過**

Run: `pytest tests/test_web.py -k fetch_and_meta -v`
Expected: PASS。

- [ ] **Step 6: Checkpoint** — `pytest tests/test_web.py -q` 全綠。

---

## Task 14: 牌組單卡頁 + diff 疊圖

**Files:**
- Modify: `sve_meta/web.py`
- Create: `sve_meta/templates/deck.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_web.py（追加）
def test_deck_page_shows_single_cards_and_missing(client, monkeypatch):
    from sve_meta import decklog
    monkeypatch.setattr(decklog, "fetch_deck", lambda conn, code: {
        "game_title_id": 6, "class": "ロイヤル",
        "list": [{"card_number": "BP17-001", "num": 3}]})
    client.post("/api/owned", json={"card_number": "BP17-001", "qty": 1})
    r = client.get("/deck/AAA")
    assert r.status_code == 200
    assert b"BP17-001" in r.data
    assert b"missing" in r.data       # 缺 2 張 → 標記 class
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_web.py -k deck_page -v`
Expected: FAIL。

- [ ] **Step 3: 在 web.py 加 deck 路由**

```python
# sve_meta/web.py（追加）
    @app.get("/deck/<code>")
    def deck_page(code):
        c = conn()
        deck = decklog.fetch_deck(c, code)
        owned = collection.get_owned(c)
        miss = engine.missing(deck["list"], owned)
        cost, unpriced = engine.completion_cost(deck["list"], owned,
                                                prices.get_all(c))
        rows = []
        for item in deck["list"]:
            cn = item["card_number"]
            rows.append({"card_number": cn, "num": item["num"],
                         "owned": owned.get(cn, 0), "missing": miss.get(cn, 0)})
        return render_template("deck.html", code=code, deck=deck, rows=rows,
                               cost=cost, unpriced=unpriced)
```

- [ ] **Step 4: 寫 deck.html**

```html
<!-- sve_meta/templates/deck.html -->
{% extends "base.html" %}{% block body %}
<h1>牌組 {{ code }}（{{ deck.class }}）</h1>
<div class="stats">補完成本 ¥{{ "{:,}".format(cost) }}
{% if unpriced %}（{{ unpriced|length }} 張無價待補）{% endif %}</div>
<div class="grid">
{% for r in rows %}
<div class="card {% if r.missing %}missing{% endif %}">
  <img src="/img/{{ r.card_number }}" alt="{{ r.card_number }}" loading="lazy">
  <div class="code">{{ r.card_number }}</div>
  <div>需 {{ r.num }}／有 {{ r.owned }}{% if r.missing %}／缺 {{ r.missing }}{% endif %}</div>
</div>
{% endfor %}</div>{% endblock %}
```

- [ ] **Step 5: 跑測試確認通過**

Run: `pytest tests/test_web.py -k deck_page -v`
Expected: PASS。

- [ ] **Step 6: Checkpoint** — `pytest tests/test_web.py -q` 全綠。

---

## Task 15: 排序頁（依補完成本）

**Files:**
- Modify: `sve_meta/web.py`
- Create: `sve_meta/templates/ranking.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_web.py（追加）
def test_ranking_orders_by_cost(client, monkeypatch):
    from sve_meta import bushinavi, decklog, prices, db
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: [
        {"event_id": "1", "title": "T", "store": "S", "players": 20,
         "start_date": "d", "rankings": [
            {"rank": 1, "player": "p", "class": "ロイヤル", "deck_code": "X"},
            {"rank": 1, "player": "q", "class": "ウィッチ", "deck_code": "Y"}]}])
    decks = {"X": [{"card_number": "BP17-001", "num": 3}],
             "Y": [{"card_number": "BP17-002", "num": 1}]}
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id": 6, "class": "?", "list": decks[code]})
    # 給價：Y 便宜（10）< X（300）→ Y 排前
    c = db.get_conn(client.application.config["DBFILE"]); db.init_db(c)
    prices.set_manual(c, "BP17-001", 100)
    prices.set_manual(c, "BP17-002", 10)
    c.close()
    client.post("/api/fetch", json={"start": "d", "end": "d", "min": 1})
    r = client.get("/ranking")
    assert r.status_code == 200
    assert r.data.find(b"/deck/Y") < r.data.find(b"/deck/X")
```

說明：為讓測試能拿到 DB 檔路徑，需在 `create_app` 內把 `db_path` 存進 `app.config["DBFILE"]`（見 Step 3）。

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_web.py -k ranking -v`
Expected: FAIL。

- [ ] **Step 3: 在 web.py 加 ranking 路由 + 存 DBFILE**

```python
# sve_meta/web.py：create_app 開頭加
    app.config["DBFILE"] = str(db_path)

# return 前追加：
    @app.get("/ranking")
    def ranking_page():
        c = conn()
        owned = collection.get_owned(c)
        price_table = prices.get_all(c)
        decks = []
        for ev in EVENTS_CACHE["events"]:
            for r in ev["rankings"]:
                if r.get("list"):
                    decks.append({"deck_code": r["deck_code"], "class": r["class"],
                                  "list": r["list"]})
        ranked = engine.rank_decks(decks, owned, price_table)
        return render_template("ranking.html", ranked=ranked)
```

- [ ] **Step 4: 寫 ranking.html**

```html
<!-- sve_meta/templates/ranking.html -->
{% extends "base.html" %}{% block body %}
<h1>差最少錢的牌組</h1>
<table><tr><th>成本</th><th>職業</th><th>缺卡數</th><th></th></tr>
{% for d in ranked %}
<tr><td>¥{{ "{:,}".format(d.cost) }}{% if d.unpriced %}＋{{ d.unpriced|length }}張無價{% endif %}</td>
<td>{{ d.class }}</td>
<td>{{ d.missing.values()|sum }}</td>
<td><a href="/deck/{{ d.deck_code }}">看單卡</a></td></tr>
{% endfor %}</table>{% endblock %}
```

- [ ] **Step 5: 跑測試確認通過**

Run: `pytest tests/test_web.py -k ranking -v`
Expected: PASS。

- [ ] **Step 6: Checkpoint** — `pytest tests/test_web.py -q` 全綠。

---

## Task 16: 圖片代理路由

**Files:**
- Modify: `sve_meta/web.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_web.py（追加）
def test_img_route_returns_cached_png(client, monkeypatch, tmp_path):
    from sve_meta import imgproxy
    monkeypatch.setattr(imgproxy, "fetch_image",
        lambda cn, **k: (tmp_path / "x.png").write_bytes(b"PNG") or (tmp_path / "x.png"))
    r = client.get("/img/BP17-001")
    assert r.status_code == 200
    assert r.data == b"PNG"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_web.py -k img_route -v`
Expected: FAIL。

- [ ] **Step 3: 在 web.py 加 /img 路由**

```python
# sve_meta/web.py（追加；檔首已 import send_file, IMG_CACHE_DIR, imgproxy）
    @app.get("/img/<card_number>")
    def img(card_number):
        path = imgproxy.fetch_image(card_number, cache_dir=IMG_CACHE_DIR)
        return send_file(path, mimetype="image/png")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_web.py -k img_route -v`
Expected: PASS。

- [ ] **Step 5: Checkpoint** — `pytest tests/test_web.py -q` 全綠。

---

## Task 17: 端到端 smoke 測試

**Files:**
- Test: `tests/test_integration.py`

- [ ] **Step 1: 寫測試（全程注入假 I/O，跑 fetch→拆解→diff→排序）**

```python
# tests/test_integration.py
from sve_meta import db, collection, decklog, bushinavi, prices, engine

def test_end_to_end_pipeline(conn, monkeypatch):
    # 1) 收藏
    collection.set_owned(conn, "BP07-007", 1)
    # 2) 假賽果（一場、一副第一名）
    events = [{"event_id":"1","title":"T","store":"S","players":20,
               "start_date":"2026-06-01","rankings":[
                 {"rank":1,"player":"p","class":"ロイヤル","deck_code":"AAA"}]}]
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: events)
    # 3) 假 DeckLog 拆解
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id":6,"class":"ロイヤル",
        "list":[{"card_number":"BP07-007","num":3},
                {"card_number":"BP07-010","num":2}]})
    # 4) 價格
    prices.set_manual(conn, "BP07-007", 100)
    prices.set_manual(conn, "BP07-010", 50)
    # 串起來
    evs = bushinavi.fetch_events("a","b",1)
    for ev in evs:
        for r in ev["rankings"]:
            r["list"] = decklog.fetch_deck(conn, r["deck_code"])["list"]
    decks = [{"deck_code":r["deck_code"],"class":r["class"],"list":r["list"]}
             for ev in evs for r in ev["rankings"]]
    ranked = engine.rank_decks(decks, collection.get_owned(conn), prices.get_all(conn))
    assert ranked[0]["missing"] == {"BP07-007": 2, "BP07-010": 2}
    assert ranked[0]["cost"] == 2*100 + 2*50      # 300
    agg = engine.aggregate_meta(evs, scope="first")
    assert agg["counts"] == {"ロイヤル": 1}
```

- [ ] **Step 2: 跑測試確認通過**

Run: `pytest tests/test_integration.py -v`
Expected: PASS。

- [ ] **Step 3: Checkpoint** — `pytest -q`（全部）全綠。

---

## Task 18: 進入點 + 使用說明

**Files:**
- Create: `run.py`
- Create: `README.md`

- [ ] **Step 1: 寫 run.py**

```python
# run.py
from sve_meta.web import create_app
from sve_meta import db
from sve_meta.config import DB_PATH

if __name__ == "__main__":
    db.init_db(db.get_conn(DB_PATH))     # 確保表存在
    create_app().run(debug=True, port=5000)
```

- [ ] **Step 2: 寫 README.md（首次資料初始化步驟）**

````markdown
# SVE Meta 收藏差距工具

## 安裝
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## 首次初始化資料（一次性）
```python
from sve_meta import db, cardmaster, prices
from sve_meta.config import DB_PATH
c = db.get_conn(DB_PATH); db.init_db(c)
for s in ["BP01","BP02","BP03"]:   # 列出你要的 set
    cardmaster.refresh_set(c, s)   # 卡表（日版）
    prices.refresh_set(c, s.lower())  # yuyu-tei 價格
```

## 啟動
```bash
python run.py    # http://localhost:5000
```

## 使用
1. 收藏頁：各卡 ＋/− 記錄擁有數（0–3）。
2. Meta 頁：填日期範圍 + 最小人數 →「獲取數據」。
3. 牌組頁：看單卡 + 缺卡 + 補完成本。
4. 排序頁：依我的補完成本由便宜到貴。
````

- [ ] **Step 3: 手動冒煙（可選，會打 live，低頻）**

Run: `python run.py`，瀏覽 `http://localhost:5000`，確認收藏頁載入。
Expected：頁面出現、計數器可加減。

- [ ] **Step 4: Checkpoint** — `pytest -q` 全綠，app 可啟動。

---

## 完成定義

- `pytest -q` 全綠（engine / classmap / collection / decklog / bushinavi / prices / cardmaster / imgproxy / web / integration）。
- `python run.py` 後四頁皆可操作：收藏記數、Meta 抓取、牌組單卡 + diff、依成本排序。
- 對外請求皆走快取且帶 delay。

## 對照 spec 的覆蓋

- §3 資料模型 → Task 0。§4 各模組 → Task 1–11、web 系列。§5 端點規格 → Task 7/8/9/10。§6 運算 → Task 1/2/4/5。§7 四頁 → Task 12/13/14/15。§8 圖片代理 → Task 11/16。§9 錯誤/快取 → 各 fetch 模組（`[]`→空 list、`is_manual` 不覆蓋、TTL/永久快取）。§10 測試 → 各 Task 的 fixture/注入式測試 + Task 17 smoke。
