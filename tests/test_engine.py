from sve_meta import engine

DECK = [{"card_number": "BP07-007", "num": 3},
        {"card_number": "BP07-010", "num": 2}]

def test_missing_counts_shortfall():
    owned = {"BP07-007": 1}
    assert engine.missing(DECK, owned) == {"BP07-007": 2, "BP07-010": 2}

def test_missing_empty_when_fully_owned():
    owned = {"BP07-007": 3, "BP07-010": 2}
    assert engine.missing(DECK, owned) == {}


def test_completion_cost_sums_missing_times_price():
    owned = {"BP07-007": 1}
    prices = {"BP07-007": 300, "BP07-010": 500}
    total, unpriced = engine.completion_cost(DECK, owned, prices)
    assert total == 2 * 300 + 2 * 500
    assert unpriced == []

def test_completion_cost_flags_unpriced():
    owned = {}
    prices = {"BP07-007": 300}
    total, unpriced = engine.completion_cost(DECK, owned, prices)
    assert total == 3 * 300
    assert unpriced == ["BP07-010"]


EVENTS = [
    {"event_id": "1", "players": 20, "rankings": [
        {"rank": 1, "class": "ロイヤル", "deck_code": "A"},
        {"rank": 2, "class": "ウィッチ", "deck_code": "B"},
        {"rank": 3, "class": "ロイヤル", "deck_code": "C"}]},
    {"event_id": "2", "players": 10, "rankings": [
        {"rank": 1, "class": "ウマ娘", "deck_code": "D"}]},
]

def test_aggregate_top8_counts_all_rankings_normalized():
    agg = engine.aggregate_meta(EVENTS, scope="top8")
    assert agg["total_events"] == 2
    assert agg["total_players"] == 30
    assert agg["counts"]["ロイヤル"] == 2
    assert agg["counts"]["ウィッチ"] == 1
    assert agg["counts"]["ニュートラル"] == 1
    assert len(agg["decks"]) == 4

def test_aggregate_first_only_counts_rank1():
    agg = engine.aggregate_meta(EVENTS, scope="first")
    assert agg["counts"] == {"ロイヤル": 1, "ニュートラル": 1}
    assert len(agg["decks"]) == 2


def test_pie_slices_empty():
    assert engine.pie_slices({}) == []

def test_pie_slices_single_class_full_circle():
    s = engine.pie_slices({"ロイヤル": 5})
    assert len(s) == 1
    assert s[0]["pct"] == 100.0
    assert s[0]["label"] == "ロイヤル"
    assert s[0]["path"].strip().startswith("M")

def test_pie_slices_sorted_desc_and_pct_sums_100():
    s = engine.pie_slices({"A": 1, "B": 3})
    assert [x["label"] for x in s] == ["B", "A"]      # 多的排前
    assert round(sum(x["pct"] for x in s)) == 100
    assert all(x["color"].startswith("#") for x in s)


def test_rank_decks_ascending_by_cost():
    decks = [
        {"deck_code": "X", "class": "ロイヤル",
         "list": [{"card_number": "BP07-007", "num": 3}]},
        {"deck_code": "Y", "class": "ウィッチ",
         "list": [{"card_number": "BP07-010", "num": 1}]},
    ]
    owned = {}
    prices = {"BP07-007": 100, "BP07-010": 50}
    ranked = engine.rank_decks(decks, owned, prices)
    assert [d["deck_code"] for d in ranked] == ["Y", "X"]
    assert ranked[0]["cost"] == 50
    assert ranked[1]["missing"] == {"BP07-007": 3}
