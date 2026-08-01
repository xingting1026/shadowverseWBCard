# sve_meta/setsync.py
"""新彈自動補資料：牌組裡出現了卡表沒有的卡（= 新 set 發售），
就自動抓官方卡表 + yuyu-tei 價格；並可順帶刷新近期常用 set 的價格。

init_data.py 的 SETS 清單是寫死的，新彈（如 BP21）發售後若只抓賽果，
卡名對不到、價格全缺，冠軍牌組會整排「無價卡」。此模組讓每日更新自我修復。
"""
import json
import re
import datetime
from . import cardmaster, prices, events_store


def _set_of(card_number):
    return (card_number or "").split("-")[0]


def unknown_sets(conn):
    """牌組中用到、但 cards 表完全沒有該卡號的 set 代號（排序後回傳）。"""
    known = {r[0] for r in conn.execute("SELECT card_number FROM cards")}
    out = set()
    for lj, ej in conn.execute("SELECT list_json, evolve_json FROM decks"):
        for j in (lj, ej):
            if not j:
                continue
            for it in json.loads(j):
                cn = it.get("card_number") or ""
                if cn and cn not in known:
                    out.add(_set_of(cn))
    return sorted(s for s in out if s)


def recent_sets(conn, days=30):
    """近 days 天（以最新賽事日回推）入賞牌組用到的 set 代號。"""
    events = events_store.load_events(conn)
    dates = [(e.get("start_date") or "")[:10] for e in events]
    dates = [d for d in dates if d]
    if not dates:
        return []
    start = (datetime.date.fromisoformat(max(dates))
             - datetime.timedelta(days=days)).isoformat()
    out = set()
    for ev in events:
        d = (ev.get("start_date") or "")[:10]
        if not d or d < start:
            continue
        for r in ev.get("rankings", []):
            for it in (r.get("list") or []) + (r.get("evolve") or []):
                out.add(_set_of(it.get("card_number")))
    return sorted(s for s in out if s)


def _expansion_candidates(set_code):
    """官方卡表 expansion 代號候選：原樣大寫；尾端小寫字母去掉再一種（DSD01b→DSD01）。"""
    cands = [set_code.upper()]
    stripped = re.sub(r"[a-z]+$", "", set_code)
    if stripped and stripped.upper() not in cands:
        cands.append(stripped.upper())
    return cands


def fetch_new_set(conn, set_code, log=print):
    """抓一個新 set 的卡表＋價格。回傳是否抓到卡表。"""
    got = False
    for exp in _expansion_candidates(set_code):
        before = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        try:
            cardmaster.refresh_set(conn, exp)
        except Exception as e:
            if log:
                log(f"  ✗ 卡表 {exp}: {type(e).__name__}")
            continue
        after = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        if after > before:
            got = True
            if log:
                log(f"  ✓ 卡表 {exp}：+{after - before} 張")
            try:
                prices.refresh_set(conn, exp.lower())
            except Exception:
                if log:
                    log(f"  · 無價 {exp}（yuyu-tei 未上架或抓取失敗）")
            break
    return got


def sync(conn, price_days=30, log=print):
    """主入口：補新彈卡表＋價格；price_days 非 None 時，刷新近期常用 set 的價格。
    回傳 {'new_sets': [...], 'price_sets': [...]}。"""
    new = unknown_sets(conn)
    fetched = [s for s in new if fetch_new_set(conn, s, log=log)]
    if log and new:
        log(f"新彈偵測：{new} → 補到 {fetched}")

    refreshed = []
    if price_days is not None:
        for s in recent_sets(conn, days=price_days):
            if s in fetched:        # 剛剛已抓過價
                continue
            try:
                prices.refresh_set(conn, s.lower())
                refreshed.append(s)
            except Exception:
                if log:
                    log(f"  · 價格刷新失敗 {s}")
        if log:
            log(f"價格刷新：{len(refreshed)} 個 set")
    return {"new_sets": fetched, "price_sets": refreshed}
