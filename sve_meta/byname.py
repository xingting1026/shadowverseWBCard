# sve_meta/byname.py
"""以「卡片名稱」為鍵的比價層。

同一張卡常有多個稀有度（不同 card_number、不同價）。算「全新組建最省成本」時，
要以名稱彙總需求、並取同名卡裡最便宜印刷的價。本模組把 card_number 維度轉成 name 維度，
之後可直接餵給 engine.missing / completion_cost / rank_decks（它們對鍵名無關）。
"""


def name_map(conn):
    """card_number → name（只含 cards 表已收錄者）。"""
    return {r["card_number"]: r["name"]
            for r in conn.execute("SELECT card_number, name FROM cards")}


def cheapest_prices_by_name(conn):
    """name → 最便宜印刷的 jpy（跨所有同名 card_number 取 min）。
    只納入 cards 有對到名稱、且 prices 有價的卡。"""
    out = {}
    rows = conn.execute(
        "SELECT c.name AS name, p.jpy AS jpy "
        "FROM cards c JOIN prices p ON p.card_number = c.card_number "
        "WHERE p.jpy IS NOT NULL")
    for r in rows:
        nm, jpy = r["name"], r["jpy"]
        if nm and (nm not in out or jpy < out[nm]):
            out[nm] = jpy
    return out


def cheapest_printing_by_name(conn):
    """name → {'card_number': 最便宜印刷的卡號, 'jpy': 價}。
    用於「最省組建」的看單卡：把參賽用的高稀有度卡換成同名最便宜的印刷。"""
    out = {}
    rows = conn.execute(
        "SELECT c.name AS name, c.card_number AS cn, p.jpy AS jpy "
        "FROM cards c JOIN prices p ON p.card_number = c.card_number "
        "WHERE p.jpy IS NOT NULL")
    for r in rows:
        nm = r["name"]
        if nm and (nm not in out or r["jpy"] < out[nm]["jpy"]):
            out[nm] = {"card_number": r["cn"], "jpy": r["jpy"]}
    return out


def deck_by_name(deck_list, nmap):
    """[{card_number,num}] → [{'card_number': name, 'num': 合計}]，依名稱彙總。
    對不到名稱的卡號，就用卡號字串當名稱（不靜默丟棄）。
    刻意沿用 'card_number' 當鍵名，好讓 engine.* 原封不動重用。"""
    agg = {}
    for item in deck_list:
        cn = item["card_number"]
        nm = nmap.get(cn) or cn
        agg[nm] = agg.get(nm, 0) + (item.get("num") or 0)
    return [{"card_number": nm, "num": n} for nm, n in agg.items()]


def owned_by_name(owned, nmap):
    """{card_number: qty} → {name: 合計 qty}。"""
    out = {}
    for cn, qty in owned.items():
        nm = nmap.get(cn) or cn
        out[nm] = out.get(nm, 0) + qty
    return out


# ---- 身分（卡名＋是否進化）層：避免把「基本卡」與「同名進化卡」混在一起 ----

def is_evolve(type_str):
    return "エボルヴ" in (type_str or "")


def type_map(conn):
    """card_number → type（用來判斷是否進化卡）。"""
    return {r["card_number"]: r["type"] for r in conn.execute(
        "SELECT card_number, type FROM cards")}


def identity_key(name, evolve):
    """卡身分鍵：同名但基本/進化分開。用控制字元分隔避免與卡名衝突。"""
    return f"{name}{'E' if evolve else 'B'}"


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


def cheapest_price_by_identity_key(conn):
    """identity_key → 最便宜 jpy（給 engine.rank_decks 當 prices 用）。"""
    return {identity_key(nm, ev): v["jpy"]
            for (nm, ev), v in cheapest_by_identity(conn).items()}


def deck_as_identity_items(deck, nmap, tmap):
    """把一副牌的主(list)+進化(evolve) 合成 [{'card_number': identity_key, 'num': n}]，
    依「卡名＋是否進化」彙總（基本/進化分開算，各自不超過 3 張）。給 engine 直接用。"""
    agg = {}
    for items, default_ev in ((deck.get("list", []), False),
                              (deck.get("evolve", []), True)):
        for it in items:
            cn = it["card_number"]
            nm = nmap.get(cn) or cn
            ev = is_evolve(tmap[cn]) if cn in tmap else default_ev
            k = identity_key(nm, ev)
            agg[k] = agg.get(k, 0) + (it.get("num") or 0)
    return [{"card_number": k, "num": n} for k, n in agg.items()]
