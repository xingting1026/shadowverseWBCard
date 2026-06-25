from sve_meta import byname


def test_deck_by_name_aggregates_across_printings():
    # 同名兩個稀有度（不同 card_number）→ 合併成一個名稱的需求
    nmap = {"BP17-001": "アリサ", "BP17-101": "アリサ", "BP17-050": "ラティカ"}
    deck = [{"card_number": "BP17-001", "num": 2},
            {"card_number": "BP17-101", "num": 1},
            {"card_number": "BP17-050", "num": 3}]
    result = {d["card_number"]: d["num"] for d in byname.deck_by_name(deck, nmap)}
    assert result == {"アリサ": 3, "ラティカ": 3}

def test_deck_by_name_unknown_code_falls_back_to_code():
    deck = [{"card_number": "ZZ99-001", "num": 2}]
    result = byname.deck_by_name(deck, {})
    assert result == [{"card_number": "ZZ99-001", "num": 2}]

def test_owned_by_name_sums_across_printings():
    nmap = {"BP17-001": "アリサ", "BP17-101": "アリサ"}
    owned = {"BP17-001": 2, "BP17-101": 1}
    assert byname.owned_by_name(owned, nmap) == {"アリサ": 3}

def test_name_map_from_db(conn):
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-001','アリサ')")
    conn.commit()
    assert byname.name_map(conn)["BP17-001"] == "アリサ"

def test_cheapest_prices_by_name_takes_min_across_printings(conn):
    # アリサ 有兩個印刷：300 / 50 → 取 50；ラティカ 只有一個有價：80
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-001','アリサ')")
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-101','アリサ')")
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-050','ラティカ')")
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-060','ノープライス')")
    conn.execute("INSERT INTO prices(card_number, jpy, is_manual) VALUES('BP17-001',300,0)")
    conn.execute("INSERT INTO prices(card_number, jpy, is_manual) VALUES('BP17-101',50,0)")
    conn.execute("INSERT INTO prices(card_number, jpy, is_manual) VALUES('BP17-050',80,0)")
    conn.commit()
    cheap = byname.cheapest_prices_by_name(conn)
    assert cheap["アリサ"] == 50
    assert cheap["ラティカ"] == 80
    assert "ノープライス" not in cheap     # 沒價的名稱不出現


def test_cheapest_printing_by_name_returns_card_number(conn):
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-001','アリサ')")
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-101','アリサ')")
    conn.execute("INSERT INTO prices(card_number, jpy, is_manual) VALUES('BP17-001',300,0)")
    conn.execute("INSERT INTO prices(card_number, jpy, is_manual) VALUES('BP17-101',50,0)")
    conn.commit()
    p = byname.cheapest_printing_by_name(conn)
    assert p["アリサ"] == {"card_number": "BP17-101", "jpy": 50}    # 換成最便宜那張卡號


def test_cheapest_by_identity_separates_base_and_evolve(conn):
    # 同名「バル」：基本兩印刷 300/200、進化一印刷 50
    conn.execute("INSERT INTO cards(card_number,name,type) VALUES('A1','バル','フォロワー')")
    conn.execute("INSERT INTO cards(card_number,name,type) VALUES('A2','バル','フォロワー')")
    conn.execute("INSERT INTO cards(card_number,name,type) VALUES('A3','バル','フォロワー・エボルヴ')")
    for cn, jpy in [("A1", 300), ("A2", 200), ("A3", 50)]:
        conn.execute("INSERT INTO prices(card_number,jpy,is_manual) VALUES(?,?,0)", (cn, jpy))
    conn.commit()
    ci = byname.cheapest_by_identity(conn)
    assert ci[("バル", False)] == {"card_number": "A2", "jpy": 200}  # 基本取200，不會掉到進化的50
    assert ci[("バル", True)] == {"card_number": "A3", "jpy": 50}    # 進化獨立一個身分


def test_deck_as_identity_items_keeps_base_and_evolve_separate(conn):
    conn.execute("INSERT INTO cards(card_number,name,type) VALUES('A1','バル','フォロワー')")
    conn.execute("INSERT INTO cards(card_number,name,type) VALUES('A3','バル','フォロワー・エボルヴ')")
    conn.commit()
    nmap, tmap = byname.name_map(conn), byname.type_map(conn)
    deck = {"list": [{"card_number": "A1", "num": 3}],
            "evolve": [{"card_number": "A3", "num": 2}]}
    items = {i["card_number"]: i["num"] for i in byname.deck_as_identity_items(deck, nmap, tmap)}
    assert items[byname.identity_key("バル", False)] == 3   # 基本3
    assert items[byname.identity_key("バル", True)] == 2    # 進化2（沒被合併成5、沒超過3）
    assert max(items.values()) <= 3
