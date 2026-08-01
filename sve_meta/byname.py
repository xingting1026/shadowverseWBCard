# sve_meta/byname.py
"""以「卡片名稱」為鍵的比價層。

同一張卡常有多個稀有度（不同 card_number、不同價）。算「全新組建最省成本」時，
要以名稱彙總需求、並取同名卡裡最便宜印刷的價。本模組把 card_number 維度轉成 name 維度。
"""


def name_map(conn):
    """card_number → name（只含 cards 表已收錄者）。"""
    return {r["card_number"]: r["name"]
            for r in conn.execute("SELECT card_number, name FROM cards")}


def deck_by_name(deck_list, nmap):
    """[{card_number,num}] → [{'card_number': name, 'num': 合計}]，依名稱彙總。
    對不到名稱的卡號，就用卡號字串當名稱（不靜默丟棄）。
    刻意沿用 'card_number' 當鍵名，方便下游對鍵名無關的程式重用。"""
    agg = {}
    for item in deck_list:
        cn = item["card_number"]
        nm = nmap.get(cn) or cn
        agg[nm] = agg.get(nm, 0) + (item.get("num") or 0)
    return [{"card_number": nm, "num": n} for nm, n in agg.items()]


# ---- 身分（卡名＋是否進化）層：避免把「基本卡」與「同名進化卡」混在一起 ----

def is_evolve(type_str):
    return "エボルヴ" in (type_str or "")


def type_map(conn):
    """card_number → type（用來判斷是否進化卡）。"""
    return {r["card_number"]: r["type"] for r in conn.execute(
        "SELECT card_number, type FROM cards")}


def identity_key(name, evolve):
    """卡身分鍵：同名但基本/進化分開。用控制字元分隔避免與卡名衝突。"""
    return f"{name}\x01{'E' if evolve else 'B'}"


def cheapest_by_identity(conn):
    """(name, is_evolve) → {'card_number': 最便宜印刷卡號, 'jpy': 價}。
    同身分（同名且同為基本/進化）內挑最便宜稀有度；基本與進化天然分開。"""
    out = {}
    rows = conn.execute(
        "SELECT c.name AS name, c.type AS type, c.card_number AS cn, p.jpy AS jpy "
        "FROM cards c JOIN prices p ON p.card_number = c.card_number "
        "WHERE p.jpy IS NOT NULL")
    for r in rows:
        if not r["name"]:
            continue
        key = (r["name"], is_evolve(r["type"]))
        if key not in out or r["jpy"] < out[key]["jpy"]:
            out[key] = {"card_number": r["cn"], "jpy": r["jpy"]}
    return out
