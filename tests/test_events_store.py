from sve_meta import events_store, decklog


def test_store_and_load_events(conn):
    events = [{"event_id": "1", "title": "T", "store": "S", "pref": "G", "players": 20,
               "start_date": "2026-06-10", "rankings": [
                 {"rank": 1, "player": "p", "class": "ロイヤル", "deck_code": "AAA",
                  "list": [{"card_number": "BP17-001", "num": 3}],
                  "cards": [{"name": "アリサ", "count": 3}]}]}]
    events_store.store_events(conn, events)
    loaded = events_store.load_events(conn)
    assert len(loaded) == 1
    assert loaded[0]["rankings"][0]["cards"][0]["name"] == "アリサ"
    assert loaded[0]["players"] == 20

def test_load_events_date_filter(conn):
    evs = [{"event_id": "1", "title": "a", "store": "", "pref": "", "players": 10,
            "start_date": "2026-05-01", "rankings": []},
           {"event_id": "2", "title": "b", "store": "", "pref": "", "players": 10,
            "start_date": "2026-06-20", "rankings": []}]
    events_store.store_events(conn, evs)
    got = events_store.load_events(conn, start="2026-06-01", end="2026-06-30")
    assert [e["event_id"] for e in got] == ["2"]

def test_resolve_and_nameify_aggregates_printings(conn, monkeypatch):
    conn.execute("INSERT INTO cards(card_number,name) VALUES('BP17-001','アリサ')")
    conn.execute("INSERT INTO cards(card_number,name) VALUES('BP17-101','アリサ')")
    conn.commit()
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {"list": [
        {"card_number": "BP17-001", "num": 2}, {"card_number": "BP17-101", "num": 1}]})
    events = [{"event_id": "1", "rankings": [{"rank": 1, "deck_code": "X"}]}]
    events_store.resolve_and_nameify(conn, events)
    r = events[0]["rankings"][0]
    assert r["cards"] == [{"name": "アリサ", "count": 3}]   # 兩印刷合併成一名稱
    assert r["list"][0]["card_number"] == "BP17-001"

def test_resolve_handles_hidden_deck(conn):
    events = [{"event_id": "1", "rankings": [{"rank": 1, "deck_code": None}]}]
    events_store.resolve_and_nameify(conn, events)
    r = events[0]["rankings"][0]
    assert r["list"] == [] and r["cards"] == []
