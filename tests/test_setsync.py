import json
from sve_meta import setsync, events_store


def _add_deck(conn, code, cards):
    conn.execute("INSERT INTO decks(code, list_json, evolve_json) VALUES(?,?,?)",
                 (code, json.dumps([{"card_number": cn, "num": 3} for cn in cards]),
                  json.dumps([])))
    conn.commit()


def _add_card(conn, cn, set_code):
    conn.execute("INSERT INTO cards(card_number, name, set_code) VALUES(?,?,?)",
                 (cn, "卡" + cn, set_code))
    conn.commit()


def test_unknown_sets_detects_new_expansion(conn):
    _add_card(conn, "BP20-001", "BP20")
    _add_deck(conn, "D1", ["BP20-001", "BP21-001", "BP21-002", "ECP03-005"])
    assert setsync.unknown_sets(conn) == ["BP21", "ECP03"]


def test_unknown_sets_empty_when_all_known(conn):
    _add_card(conn, "BP20-001", "BP20")
    _add_deck(conn, "D1", ["BP20-001"])
    assert setsync.unknown_sets(conn) == []


def test_recent_sets_windowed(conn):
    old = {"event_id": "old", "start_date": "2026-01-01", "players": 8, "rankings": [
        {"rank": 1, "deck_code": "A", "class": "ドラゴン",
         "list": [{"card_number": "SD01-001", "num": 3}], "evolve": []}]}
    new = {"event_id": "new", "start_date": "2026-06-20", "players": 8, "rankings": [
        {"rank": 1, "deck_code": "B", "class": "ドラゴン",
         "list": [{"card_number": "BP21-001", "num": 3}],
         "evolve": [{"card_number": "BP20-002", "num": 2}]}]}
    events_store.store_events(conn, [old, new])
    assert setsync.recent_sets(conn, days=30) == ["BP20", "BP21"]


def test_expansion_candidates_strip_trailing_lowercase():
    assert setsync._expansion_candidates("BP21") == ["BP21"]
    assert setsync._expansion_candidates("DSD01b") == ["DSD01B", "DSD01"]


def test_sync_fetches_new_set_with_stubbed_fetchers(conn, monkeypatch):
    from sve_meta import cardmaster, prices

    def fake_card_refresh(c, exp):
        assert exp == "BP21"
        c.execute("INSERT INTO cards(card_number, name, set_code) VALUES(?,?,?)",
                  ("BP21-001", "新卡", "BP21"))
        c.commit()

    fetched_prices = []
    monkeypatch.setattr(cardmaster, "refresh_set", fake_card_refresh)
    monkeypatch.setattr(prices, "refresh_set",
                        lambda c, s: fetched_prices.append(s))

    _add_deck(conn, "D1", ["BP21-001"])
    out = setsync.sync(conn, price_days=None, log=None)
    assert out["new_sets"] == ["BP21"]
    assert fetched_prices == ["bp21"]
    assert setsync.unknown_sets(conn) == []     # 補完後不再是未知 set
