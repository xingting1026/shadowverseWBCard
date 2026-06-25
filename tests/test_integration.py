from sve_meta import collection, decklog, bushinavi, prices, engine


def test_end_to_end_pipeline(conn, monkeypatch):
    # 1) 收藏：BP07-007 有 1 張
    collection.set_owned(conn, "BP07-007", 1)
    # 2) 假賽果：一場、一副第一名（ロイヤル）
    events = [{"event_id": "1", "title": "T", "store": "S", "players": 20,
               "start_date": "2026-06-01", "rankings": [
                 {"rank": 1, "player": "p", "class": "ロイヤル", "deck_code": "AAA"}]}]
    monkeypatch.setattr(bushinavi, "fetch_events", lambda *a, **k: events)
    # 3) 假 DeckLog 拆解
    monkeypatch.setattr(decklog, "fetch_deck", lambda c, code: {
        "game_title_id": 6, "class": "ロイヤル",
        "list": [{"card_number": "BP07-007", "num": 3},
                 {"card_number": "BP07-010", "num": 2}]})
    # 4) 價格（手動填）
    prices.set_manual(conn, "BP07-007", 100)
    prices.set_manual(conn, "BP07-010", 50)

    # --- 串起整條 pipeline ---
    evs = bushinavi.fetch_events("a", "b", 1)
    for ev in evs:
        for r in ev["rankings"]:
            r["list"] = decklog.fetch_deck(conn, r["deck_code"])["list"]
    decks = [{"deck_code": r["deck_code"], "class": r["class"], "list": r["list"]}
             for ev in evs for r in ev["rankings"]]

    ranked = engine.rank_decks(decks, collection.get_owned(conn), prices.get_all(conn))
    assert ranked[0]["missing"] == {"BP07-007": 2, "BP07-010": 2}
    assert ranked[0]["cost"] == 2 * 100 + 2 * 50      # 缺2張×100 + 缺2張×50 = 300

    agg = engine.aggregate_meta(evs, scope="first")
    assert agg["counts"] == {"ロイヤル": 1}
