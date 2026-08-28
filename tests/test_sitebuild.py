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
        conn.execute("INSERT INTO cards(card_number,name,class,type,set_code,text,flavor) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (cn, nm, cls, tp, st,
                      f"{nm}的效果", "flavor" if tp == "フォロワー" else ""))
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
        {"rank": 3, "class": "", "deck_code": None, "list": [], "evolve": []},
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
    # 職業空白（店家沒登錄）的名次整筆略過
    assert len(ev["rankings"]) == 2
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
    (out / "data").mkdir(parents=True)
    (out / "ai.html").write_text("retired", encoding="utf-8")
    (out / "data" / "ai-matrix.json").write_text("{}", encoding="utf-8")
    sitebuild.export_site(conn, out, cache, web_src=web,
                          fetch_images=False, log=None)
    idx = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    assert idx["months"] == ["2026-06"] and idx["latest"] == "2026-06"
    assert (out / "data" / "month" / "2026-06.json").exists()
    tiers = json.loads((out / "data" / "tiers.json").read_text(encoding="utf-8"))
    assert tiers["total_decks"] == 1        # 只有 1 副公開 → 全進 others
    cards = json.loads((out / "data" / "cards.json").read_text(encoding="utf-8"))
    assert cards["BP01-101"] == ["火龍", 100, 0]   # 最省替換用到的印刷也在卡表裡
    assert cards["BP01-E01"] == ["火龍", 200, 1]   # 進化卡帶旗標
    assert (out / "index.html").exists()
    assert not (out / "ai.html").exists()
    assert not (out / "data" / "ai-matrix.json").exists()
    assert (out / "img" / "BP01-101.jpg").exists()
    # 卡片查詢索引：冠軍 DK1 用了 BP01-001×3（主）與 BP01-E01×2（進化）
    usage = json.loads((out / "data" / "usage" / "BP01.json").read_text(encoding="utf-8"))
    assert usage["BP01-001"] == [["2026-06", "DK1", "殿堂賽", "2026-06-15", 16, 3]]
    assert usage["BP01-E01"][0][5] == 2
    # 牌效：同名印刷去重（火龍兩種印刷共一份）、基本/進化分開
    eff = json.loads((out / "data" / "effects.ja.json").read_text(encoding="utf-8"))
    assert eff["火龍"]["B"] == ["火龍的效果", "flavor"]
    assert eff["火龍"]["E"][0] == "火龍的效果"
    assert eff["水龍"]["B"][0] == "水龍的效果"


def test_build_usage_index_sorted_desc_and_champions_only():
    month_datas = [{
        "month": "2026-05",
        "decks": {"A": {"cls": "ドラゴン", "main": [["X-001", 3]], "evo": []},
                  "B": {"cls": "ドラゴン", "main": [["X-001", 2]], "evo": []}},
        "champions": [
            {"code": "A", "event": "會A", "date": "2026-05-01", "players": 10},
            {"code": "B", "event": "會B", "date": "2026-05-20", "players": 30}],
        "cheapest": {},
    }]
    usage = sitebuild.build_usage_index(month_datas)
    rows = usage["X"]["X-001"]
    assert [r[1] for r in rows] == ["B", "A"]      # 日期新到舊
    assert rows[0][5] == 2 and rows[1][5] == 3     # 各自的張數
