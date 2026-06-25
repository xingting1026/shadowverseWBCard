import json
from pathlib import Path
from sve_meta import decklog

FIXTURES = Path(__file__).parent / "fixtures"

def _payload():
    return json.load(open(FIXTURES / "decklog_6DBH1.json", encoding="utf-8"))

def test_parse_deck_extracts_card_list():
    deck = decklog.parse_deck(_payload())
    assert deck["game_title_id"] == 6
    items = {i["card_number"]: i["num"] for i in deck["list"]}
    assert items["ECP02-016"] == 3        # adjust to the real first item if fixture differs
    assert all("card_number" in i and "num" in i for i in deck["list"])

def test_parse_deck_empty_payload_returns_empty_list():
    assert decklog.parse_deck([]) == {"game_title_id": None, "class": None,
                                       "list": [], "evolve": []}

def test_parse_deck_collects_sub_list_as_evolve():
    payload = {"game_title_id": 6, "deck_param1": "ネメシス",
               "list": [{"card_number": "BP19-019", "num": 3}],
               "sub_list": [{"card_number": "BP19-020", "num": 2}]}
    deck = decklog.parse_deck(payload)
    assert deck["list"] == [{"card_number": "BP19-019", "num": 3}]
    assert deck["evolve"] == [{"card_number": "BP19-020", "num": 2}]   # sub_list → evolve

def test_fetch_deck_uses_cache_and_calls_once(conn):
    calls = {"n": 0}
    def fake_poster(code):
        calls["n"] += 1
        return {"game_title_id": 6, "deck_param1": "ロイヤル",
                "list": [{"card_number": "BP07-007", "num": 3}]}
    d1 = decklog.fetch_deck(conn, "ZZZ1", poster=fake_poster)
    d2 = decklog.fetch_deck(conn, "ZZZ1", poster=fake_poster)
    assert d1["list"][0]["card_number"] == "BP07-007"
    assert d2 == d1
    assert calls["n"] == 1
