import datetime
import json
import re
import pytest
from sve_meta import web, db

TODAY = datetime.date.today().isoformat()


@pytest.fixture
def client(tmp_path):
    dbfile = tmp_path / "t.db"
    c = db.get_conn(dbfile)
    db.init_db(c)
    c.execute("INSERT INTO cards(card_number, name, set_code) VALUES(?,?,?)",
              ("BP17-001", "テスト", "BP17"))
    c.commit()
    c.close()
    app = web.create_app(dbfile)
    app.config["TESTING"] = True
    return app.test_client()


def test_collection_page_lists_cards(client):
    r = client.get("/collection")
    assert r.status_code == 200
    assert b"BP17-001" in r.data
    assert b"/static/owned.js" in r.data          # 收藏存 localStorage 的腳本有載入


def test_fetch_persists_and_meta_shows_pie(client, monkeypatch):
    from sve_meta import bushinavi, decklog
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: [
        {"event_id": "1", "title": "T", "store": "S", "players": 20,
         "start_date": TODAY, "rankings": [
            {"rank": 1, "player": "p", "class": "ロイヤル", "deck_code": "AAA"}]}])
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id": 6, "class": "ロイヤル",
        "list": [{"card_number": "BP17-001", "num": 3}], "evolve": []})
    r = client.post("/api/fetch", json={"start": TODAY, "end": TODAY, "min": 8})
    assert r.status_code == 200 and r.get_json()["events"] == 1
    meta = client.get("/meta?scope=first")
    assert "ロイヤル".encode() in meta.data
    assert b"<svg" in meta.data


def test_meta_survives_restart(client, monkeypatch):
    from sve_meta import bushinavi, decklog
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: [
        {"event_id": "9", "title": "持久", "store": "S", "players": 12,
         "start_date": TODAY, "rankings": [
            {"rank": 1, "player": "p", "class": "ドラゴン", "deck_code": "AAA"}]}])
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id": 6, "class": "ドラゴン", "list": [], "evolve": []})
    client.post("/api/fetch", json={"start": TODAY, "end": TODAY, "min": 1})
    app2 = web.create_app(client.application.config["DBFILE"])
    assert "ドラゴン".encode() in app2.test_client().get("/meta").data


def test_deck_normal_embeds_price_for_client_calc(client, monkeypatch):
    # 一般模式不再用伺服器收藏：渲染卡 + data-price，瀏覽器自己用 localStorage 算缺/成本
    from sve_meta import decklog, db as dbmod
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id": 6, "class": "ロイヤル",
        "list": [{"card_number": "BP17-001", "num": 3}], "evolve": []})
    c = dbmod.get_conn(client.application.config["DBFILE"])
    dbmod.init_db(c)
    c.execute("INSERT OR REPLACE INTO prices(card_number,jpy,is_manual) VALUES('BP17-001',100,0)")
    c.commit()
    c.close()
    r = client.get("/deck/AAA")
    assert r.status_code == 200
    assert b"data-deck-normal" in r.data
    assert b'data-cn="BP17-001"' in r.data
    assert b'data-num="3"' in r.data
    assert b'data-price="100"' in r.data


def test_ranking_embeds_deck_data_for_client(client, monkeypatch):
    from sve_meta import bushinavi, decklog, prices, db as dbmod
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: [
        {"event_id": "1", "title": "T", "store": "S", "players": 20,
         "start_date": TODAY, "rankings": [
            {"rank": 1, "player": "p", "class": "ロイヤル", "deck_code": "X"}]}])
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "list": [{"card_number": "BP17-001", "num": 3}], "evolve": []})
    c = dbmod.get_conn(client.application.config["DBFILE"])
    dbmod.init_db(c)
    prices.set_manual(c, "BP17-001", 100)
    c.close()
    client.post("/api/fetch", json={"start": TODAY, "end": TODAY, "min": 1})
    r = client.get("/ranking")
    assert r.status_code == 200
    blob = re.search(rb'<script id="rank-data"[^>]*>(.*?)</script>', r.data, re.S).group(1)
    data = json.loads(blob)
    assert data["decks"][0]["code"] == "X"
    assert {"cn": "BP17-001", "num": 3} in data["decks"][0]["cards"]
    assert data["prices"]["BP17-001"] == 100      # 價格表嵌好，瀏覽器即時算


def test_ranking2_cheapest_total_build_by_name(client, monkeypatch):
    from sve_meta import bushinavi, decklog, db as dbmod
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: [
        {"event_id": "1", "title": "杯賽", "store": "S", "players": 20,
         "start_date": TODAY, "rankings": [
            {"rank": 1, "player": "p", "class": "ドラゴン", "deck_code": "X"},
            {"rank": 1, "player": "q", "class": "エルフ", "deck_code": "Y"}]}])
    decks = {"X": [{"card_number": "BP18-001", "num": 3}],
             "Y": [{"card_number": "BP18-002", "num": 1}]}
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {"list": decks[code]})
    c = dbmod.get_conn(client.application.config["DBFILE"])
    dbmod.init_db(c)
    for cn, nm in [("BP18-001", "ドラゴン"), ("BP18-009", "ドラゴン"), ("BP18-002", "妖精")]:
        c.execute("INSERT OR REPLACE INTO cards(card_number,name) VALUES(?,?)", (cn, nm))
    for cn, jpy in [("BP18-001", 300), ("BP18-009", 30), ("BP18-002", 50)]:
        c.execute("INSERT OR REPLACE INTO prices(card_number,jpy,is_manual) VALUES(?,?,0)", (cn, jpy))
    c.commit()
    c.close()
    client.post("/api/fetch", json={"start": TODAY, "end": TODAY, "min": 1})
    r = client.get("/ranking2")
    assert r.status_code == 200
    assert r.data.find(b"/deck/Y") < r.data.find(b"/deck/X")     # 全新組建較省的在前（server 算）
    assert b"90" in r.data and b"50" in r.data


def test_deck_cheapest_mode_swaps_to_cheapest_printing(client, monkeypatch):
    from sve_meta import decklog, db as dbmod
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id": 6, "class": "ドラゴン",
        "list": [{"card_number": "BP18-001", "num": 3}]})
    c = dbmod.get_conn(client.application.config["DBFILE"])
    dbmod.init_db(c)
    for cn, nm in [("BP18-001", "竜"), ("BP18-009", "竜")]:
        c.execute("INSERT OR REPLACE INTO cards(card_number,name) VALUES(?,?)", (cn, nm))
    c.execute("INSERT OR REPLACE INTO prices(card_number,jpy,is_manual) VALUES('BP18-001',9000,0)")
    c.execute("INSERT OR REPLACE INTO prices(card_number,jpy,is_manual) VALUES('BP18-009',40,0)")
    c.commit()
    c.close()
    r = client.get("/deck/ZZ?cheapest=1")
    assert r.status_code == 200
    assert b"BP18-009" in r.data
    assert b"BP18-001" not in r.data
    assert b"120" in r.data


def test_ranking_month_switcher(client):
    from sve_meta import events_store, db as dbmod
    c = dbmod.get_conn(client.application.config["DBFILE"])
    dbmod.init_db(c)
    events_store.store_events(c, [
        {"event_id": "a", "title": "五月賽", "store": "S", "pref": "G", "players": 20,
         "start_date": "2025-05-10", "rankings": [
            {"rank": 1, "player": "p", "class": "ロイヤル", "deck_code": "M5",
             "list": [{"card_number": "BP17-001", "num": 3}], "evolve": [], "cards": []}]},
        {"event_id": "b", "title": "八月賽", "store": "S", "pref": "G", "players": 20,
         "start_date": "2025-08-10", "rankings": [
            {"rank": 1, "player": "q", "class": "エルフ", "deck_code": "M8",
             "list": [{"card_number": "BP17-001", "num": 3}], "evolve": [], "cards": []}]}])
    c.close()
    r = client.get("/ranking2")                          # 預設 = 最新月份 2025-08
    assert b"2025-05" in r.data and b"2025-08" in r.data  # 月份膠囊
    assert b"/deck/M8" in r.data and b"/deck/M5" not in r.data
    r2 = client.get("/ranking2?month=2025-05")
    assert b"/deck/M5" in r2.data and b"/deck/M8" not in r2.data


def test_img_route_returns_cached_png(client, monkeypatch, tmp_path):
    from sve_meta import imgproxy
    png = tmp_path / "x.png"
    png.write_bytes(b"PNG")
    monkeypatch.setattr(imgproxy, "fetch_image", lambda cn, **k: png)
    r = client.get("/img/BP17-001")
    assert r.status_code == 200
    assert r.data == b"PNG"
