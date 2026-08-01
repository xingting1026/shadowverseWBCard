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

def test_name_map_from_db(conn):
    conn.execute("INSERT INTO cards(card_number, name) VALUES('BP17-001','アリサ')")
    conn.commit()
    assert byname.name_map(conn)["BP17-001"] == "アリサ"


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
