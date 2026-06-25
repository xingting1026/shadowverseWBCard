import json
from pathlib import Path
from sve_meta import bushinavi

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_event_list_returns_rows_with_players():
    payload = json.load(open(FIXTURES / "bushinavi_list.json", encoding="utf-8"))
    rows = bushinavi.parse_event_list(payload)
    assert len(rows) >= 1
    r = rows[0]
    assert set(["event_id", "title", "store", "players", "start_date"]) <= set(r)
    assert isinstance(r["players"], int)


def test_parse_event_detail_returns_rankings_with_deck_codes():
    payload = json.load(open(FIXTURES / "bushinavi_detail.json", encoding="utf-8"))
    detail = bushinavi.parse_event_detail(payload)
    assert detail["players"] >= 1
    top = detail["rankings"][0]
    assert set(["rank", "player", "class", "deck_code"]) <= set(top)


def test_fetch_events_filters_by_min_players():
    pages = {0: {"success": {"events": [
                 {"event_id": 1, "event_title": "A", "place": "店1",
                  "pref_code": "G", "joined_player_count": 20, "start_datetime": "2026-06-01"},
                 {"event_id": 2, "event_title": "B", "place": "店2",
                  "pref_code": "G", "joined_player_count": 5, "start_datetime": "2026-06-02"}]}},
             50: {"success": {"events": []}}}
    detail = {"success": {"joined_player_count": 20, "grouped_rankings": {
                 "g1": {"t1": {"rank": 1, "team_member": [
                     {"player_name": "p", "deck_param1": "ロイヤル", "deck_recipe_id": "AAA"}]}}}}}
    def fake_getter(url):
        if "/list" in url:
            off = 50 if "offset=50" in url else 0
            return pages[off]
        return detail
    events = bushinavi.fetch_events("2026-06-01", "2026-06-30", min_players=10,
                                    getter=fake_getter)
    assert [e["event_id"] for e in events] == ["1"]
    assert events[0]["rankings"][0]["deck_code"] == "AAA"
