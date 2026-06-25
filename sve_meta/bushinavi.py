import time
import requests
from .config import (BUSHINAVI_API, BUSHINAVI_HEADERS,
                     GAME_TITLE_ID_SVE, REQUEST_DELAY)


def parse_event_list(payload):
    """Parse the /event/result/list response.

    Real structure: payload["success"]["events"] — list of event objects,
    each with event_id, event_title, place, pref_code, joined_player_count,
    start_datetime.
    """
    events = payload.get("success", {}).get("events", []) or payload.get("events", [])
    out = []
    for e in events:
        out.append({
            "event_id": str(e.get("event_id")),
            "title": e.get("event_title"),
            "store": e.get("place"),
            "pref": e.get("pref_code"),
            "players": int(e.get("joined_player_count") or 0),
            "start_date": e.get("start_datetime"),
        })
    return out


def parse_event_detail(payload):
    """Parse the /event/result/detail/<id> response.

    Real structure (verified against live API):
      payload["success"]["joined_player_count"]   — int, participant count
      payload["success"]["grouped_rankings"]      — TWO-level dict:
          { <group_key>: { <team_id>: { "rank": N, "team_member": [...] } } }
        Each team_member has: player_name, deck_param1, deck_recipe_id.

    NOTE: The original spec assumed one level of grouped_rankings; the real
    API has an extra outer grouping key (often "" or a group label), so we
    iterate both levels here.
    """
    s = payload.get("success", payload)
    players = int(s.get("joined_player_count") or 0)
    rankings = []
    grouped = s.get("grouped_rankings", {}) or {}
    for group in grouped.values():
        # group is { team_id: {"rank": N, "team_member": [...]} }
        for entry in group.values():
            rank = entry.get("rank")
            for m in entry.get("team_member", []):
                rankings.append({
                    "rank": rank,
                    "player": m.get("player_name"),
                    "class": m.get("deck_param1"),
                    "deck_code": m.get("deck_recipe_id"),
                })
    rankings.sort(key=lambda r: (r["rank"] is None, r["rank"]))
    return {"players": players, "rankings": rankings}


def _get(url):
    time.sleep(REQUEST_DELAY)
    r = requests.get(url, headers=BUSHINAVI_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_events(start, end, min_players, limit=50, getter=_get):
    """走 list 分頁 → client 端依 players 過濾 → 逐筆抓 detail 併入 rankings。"""
    collected, offset = [], 0
    while True:
        url = (f"{BUSHINAVI_API}/api/user/event/result/list"
               f"?game_title_id[]={GAME_TITLE_ID_SVE}"
               f"&start_date={start}&end_date={end}&limit={limit}&offset={offset}")
        rows = parse_event_list(getter(url))
        if not rows:
            break
        collected.extend(rows)
        offset += limit
    events = []
    for ev in collected:
        if ev["players"] < min_players:
            continue
        detail = parse_event_detail(
            getter(f"{BUSHINAVI_API}/api/user/event/result/detail/{ev['event_id']}"))
        events.append({**ev, "players": detail["players"] or ev["players"],
                       "rankings": detail["rankings"]})
    return events
