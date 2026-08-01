import json
from sve_meta import sitebuild, events_store, byname


def seed(conn):
    cards = [
        # 同名兩種印刷：BP01-001 貴、BP01-101 便宜
        ("BP01-001", "火龍", "ドラゴン", "フォロワー", "BP01"),
        ("BP01-101", "火龍", "ドラゴン", "フォロワー", "BP01"),
        ("BP01-002", "水龍", "ドラゴン", "フォロワー", "BP01"),
        ("BP01-E01", "火龍", "ドラゴン", "フォロワー・エボルヴ", "BP01"),
    ]
    for cn, nm, cls, tp, st in cards:
        conn.execute("INSERT INTO cards(card_number,name,class,type,set_code) "
                     "VALUES(?,?,?,?,?)", (cn, nm, cls, tp, st))
    for cn, jpy in [("BP01-001", 1000), ("BP01-101", 100),
                    ("BP01-002", 50), ("BP01-E01", 200)]:
        conn.execute("INSERT INTO prices(card_number,jpy) VALUES(?,?)", (cn, jpy))
    conn.commit()


EVENTS = [{
    "event_id": "e1", "title": "殿堂賽", "store": "店A", "pref": "東京",
    "players": 16, "start_date": "2026-06-15",
    "rankings": [
        {"rank": 1, "class": "ドラゴン", "deck_code": "DK1",
         "list": [{"card_number": "BP01-001", "num": 3},
                  {"card_number": "BP01-002", "num": 2}],
         "evolve": [{"card_number": "BP01-E01", "num": 2}]},
        {"rank": 2, "class": "ウマ娘", "deck_code": None, "list": [], "evolve": []},
    ]}]


def test_cheapest_sections_swaps_to_cheapest_printing(conn):
    seed(conn)
    nmap, tmap = byname.name_map(conn), byname.type_map(conn)
    cheap = byname.cheapest_by_identity(conn)
    out = sitebuild.cheapest_sections(EVENTS[0]["rankings"][0], nmap, tmap, cheap)
    # 火龍×3 用便宜印刷 100、水龍×2 用 50、進化火龍×2 用 200
    assert out["cost"] == 3 * 100 + 2 * 50 + 2 * 200
    assert out["unpriced"] == []
    fire = [r for r in out["main"] if r["name"] == "火龍"][0]
    assert fire["cn"] == "BP01-101" and fire["unit"] == 100
    assert out["evo"][0]["cn"] == "BP01-E01"


def test_export_month_shape(conn):
    seed(conn)
    events_store.store_events(conn, [dict(e) for e in json.loads(json.dumps(EVENTS))])
    nmap, tmap = byname.name_map(conn), byname.type_map(conn)
    cheap = byname.cheapest_by_identity(conn)
    md = sitebuild.export_month(conn, "2026-06", nmap, tmap, cheap)
    assert md["month"] == "2026-06"
    assert len(md["events"]) == 1
    ev = md["events"][0]
    assert ev["rankings"][0] == {"rank": 1, "cls": "ドラゴン", "code": "DK1"}
    # 未公開牌組：code 為 None、職業正規化（ウマ娘→ニュートラル）
    assert ev["rankings"][1] == {"rank": 2, "cls": "ニュートラル", "code": None}
    assert md["decks"]["DK1"]["main"] == [["BP01-001", 3], ["BP01-002", 2]]
    assert md["champions"][0]["code"] == "DK1"
    assert md["champions"][0]["cost"] == md["cheapest"]["DK1"]["cost"] == 800
    assert md["champions"][0]["unpriced"] == 0


def test_export_site_writes_all_files(conn, tmp_path):
    seed(conn)
    events_store.store_events(conn, [dict(e) for e in json.loads(json.dumps(EVENTS))])
    web = tmp_path / "web"
    (web / "static").mkdir(parents=True)
    (web / "index.html").write_text("<html>", encoding="utf-8")
    cache = tmp_path / "img_cache"
    cache.mkdir()
    (cache / "BP01-101.jpg").write_bytes(b"jpg")
    out = tmp_path / "site"
    sitebuild.export_site(conn, out, cache, web_src=web,
                          fetch_images=False, log=None)
    idx = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    assert idx["months"] == ["2026-06"] and idx["latest"] == "2026-06"
    assert (out / "data" / "month" / "2026-06.json").exists()
    tiers = json.loads((out / "data" / "tiers.json").read_text(encoding="utf-8"))
    assert tiers["total_decks"] == 1        # 只有 1 副公開 → 全進 others
    cards = json.loads((out / "data" / "cards.json").read_text(encoding="utf-8"))
    assert cards["BP01-101"] == ["火龍", 100]   # 最省替換用到的印刷也在卡表裡
    assert (out / "index.html").exists()
    assert (out / "img" / "BP01-101.jpg").exists()
