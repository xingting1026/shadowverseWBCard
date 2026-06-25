import json, time, requests
from .config import DECKLOG_VIEW_API, DECKLOG_REFERER, USER_AGENT, REQUEST_DELAY


def _items(payload, key):
    return [{"card_number": i.get("card_number"), "num": i.get("num")}
            for i in payload.get(key, [])]


def parse_deck(payload):
    """list = 主牌組(40)、sub_list = 進化牌組(10)。兩區都收。"""
    if not isinstance(payload, dict):  # 空 [] = 被刪/隱藏/過期
        return {"game_title_id": None, "class": None, "list": [], "evolve": []}
    return {"game_title_id": payload.get("game_title_id"),
            "class": payload.get("deck_param1"),
            "list": _items(payload, "list"),
            "evolve": _items(payload, "sub_list")}


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
    """先查快取；牌組內容不可變 → 永久快取。
    舊快取沒有 evolve_json（進化牌組）→ 視為未解析，重新抓一次補上。"""
    row = conn.execute("SELECT game_title_id, class, list_json, evolve_json "
                       "FROM decks WHERE code=?", (code,)).fetchone()
    if row and row["evolve_json"] is not None:
        return {"game_title_id": row["game_title_id"], "class": row["class"],
                "list": json.loads(row["list_json"]),
                "evolve": json.loads(row["evolve_json"])}
    deck = parse_deck(poster(code))
    conn.execute("INSERT OR REPLACE INTO decks"
                 "(code, game_title_id, class, list_json, evolve_json, fetched_at) "
                 "VALUES(?,?,?,?,?,?)",
                 (code, deck["game_title_id"], deck["class"],
                  json.dumps(deck["list"]), json.dumps(deck["evolve"]), time.time()))
    conn.commit()
    return deck
