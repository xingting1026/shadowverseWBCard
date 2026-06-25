# sve_meta/events_store.py
"""賽果持久化：把大會結果（含名稱化牌表）寫入 / 讀回 events 表，跨重啟保存。"""
import json
import time
from . import decklog, byname


def resolve_and_nameify(conn, events):
    """就地補上每個 ranking 的牌表：
      r['list']  = [{card_number, num}]      （給單卡圖顯示用）
      r['cards'] = [{name, count}]            （依名稱彙總，給比價/可讀顯示用）
    deck_code 為空（入賞牌隱藏期）則兩者皆空。"""
    nmap = byname.name_map(conn)
    for ev in events:
        for r in ev.get("rankings", []):
            code = r.get("deck_code")
            deck = decklog.fetch_deck(conn, code) if code else {"list": [], "evolve": []}
            r["list"] = deck.get("list", [])
            r["evolve"] = deck.get("evolve", [])      # 進化牌組
            r["cards"] = [{"name": d["card_number"], "count": d["num"]}
                          for d in byname.deck_by_name(r["list"], nmap)]
    return events


def store_events(conn, events):
    """寫入 events 表（INSERT OR REPLACE，可重跑）。"""
    for ev in events:
        conn.execute(
            "INSERT OR REPLACE INTO events"
            "(event_id, title, store, pref, players, start_date, rankings_json, fetched_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (str(ev["event_id"]), ev.get("title"), ev.get("store"), ev.get("pref"),
             ev.get("players"), ev.get("start_date"),
             json.dumps(ev.get("rankings", []), ensure_ascii=False), time.time()))
    conn.commit()


def load_events(conn, start=None, end=None):
    """讀回賽果，依 start_date 前 10 碼（YYYY-MM-DD）做區間過濾。新到舊排序。"""
    out = []
    for r in conn.execute("SELECT * FROM events ORDER BY start_date DESC"):
        sd = (r["start_date"] or "")[:10]
        if start and sd < start:
            continue
        if end and sd > end:
            continue
        out.append({"event_id": r["event_id"], "title": r["title"],
                    "store": r["store"], "pref": r["pref"], "players": r["players"],
                    "start_date": r["start_date"],
                    "rankings": json.loads(r["rankings_json"] or "[]")})
    return out
