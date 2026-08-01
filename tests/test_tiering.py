from collections import Counter
from sve_meta import tiering


# ---- 測試用小卡池：A 原型 a1..a5、B 原型 b1..b5、staple s1（兩邊都帶）----
NMAP = {**{f"a{i}": f"卡A{i}" for i in range(1, 6)},
        **{f"b{i}": f"卡B{i}" for i in range(1, 6)},
        "s1": "中堅卡", "e1": "進化卡"}
TMAP = {**{cn: "フォロワー" for cn in NMAP}, "e1": "フォロワー・エボルヴ"}


def deck(cns, evolve=None):
    return {"list": [{"card_number": cn, "num": 3} for cn in cns],
            "evolve": [{"card_number": cn, "num": 2} for cn in (evolve or [])]}


def ev(eid, date, rankings, players=16):
    return {"event_id": eid, "title": f"大會{eid}", "players": players,
            "start_date": date, "rankings": rankings}


def rk(rank, cls, code, cns, evolve=None):
    return {"rank": rank, "class": cls, "deck_code": code, **deck(cns, evolve)}


def test_similarity_identical_and_disjoint():
    a = Counter({"x": 3, "y": 2})
    assert tiering.similarity(a, a) == 1.0
    assert tiering.similarity(a, Counter({"z": 3})) == 0.0
    assert tiering.similarity(Counter(), Counter()) == 0.0


def test_similarity_partial_overlap():
    a = Counter({"x": 3, "y": 3})
    b = Counter({"x": 3, "z": 3})
    assert abs(tiering.similarity(a, b) - 3 / 9) < 1e-9


def test_deck_vector_separates_evolve_and_merges_sections():
    vec = tiering.deck_vector(deck(["a1"], evolve=["e1"]), NMAP, TMAP)
    keys = set(vec)
    assert len(keys) == 2
    assert any(k.endswith("E") for k in keys)
    assert vec[[k for k in keys if k.endswith("B")][0]] == 3


def test_clusters_same_archetype_despite_small_diffs():
    # A 原型 3 副（差 1 張卡）、B 原型 2 副、同職業 → 兩群
    events = [ev("1", "2026-06-10", [
        rk(1, "ドラゴン", "A1", ["a1", "a2", "a3", "a4", "s1"]),
        rk(2, "ドラゴン", "B1", ["b1", "b2", "b3", "b4", "s1"]),
    ]), ev("2", "2026-06-20", [
        rk(1, "ドラゴン", "A2", ["a1", "a2", "a3", "a5", "s1"]),
        rk(1, "ドラゴン", "B2", ["b1", "b2", "b3", "b5", "s1"]),
    ]), ev("3", "2026-06-25", [
        rk(1, "ドラゴン", "A3", ["a1", "a2", "a3", "a4", "a5"]),
    ])]
    out = tiering.build_tiers(events, NMAP, TMAP)
    assert len(out["clusters"]) == 2
    ns = sorted(c["n"] for c in out["clusters"])
    assert ns == [2, 3]


def test_different_class_never_merges():
    events = [ev("1", "2026-06-10", [
        rk(1, "ドラゴン", "X", ["a1", "a2", "a3"]),
        rk(2, "エルフ", "Y", ["a1", "a2", "a3"]),
        rk(3, "ドラゴン", "X2", ["a1", "a2", "a3"]),
        rk(4, "エルフ", "Y2", ["a1", "a2", "a3"]),
    ])]
    out = tiering.build_tiers(events, NMAP, TMAP)
    assert len(out["clusters"]) == 2
    assert {c["cls"] for c in out["clusters"]} == {"ドラゴン", "エルフ"}


def test_signature_prefers_distinctive_over_staple():
    a_vecs = [Counter({"卡A1\x01B": 3, "中堅卡\x01B": 3}),
              Counter({"卡A1\x01B": 3, "中堅卡\x01B": 3})]
    b_vecs = [Counter({"卡B1\x01B": 3, "中堅卡\x01B": 3}),
              Counter({"卡B1\x01B": 3, "中堅卡\x01B": 3})]
    sig = tiering.signature_names(a_vecs, a_vecs + b_vecs)
    assert sig[0] == "卡A1"          # 鑑別度高的排最前，staple 不會當第一特徵


def test_tier0_for_dominant_cluster_and_scores():
    # A 原型 3 個冠軍（score 9）、B 原型 2 個八強（score 2）→ A=T0、B 較低檔
    events = [ev("1", "2026-06-10", [
        rk(1, "ドラゴン", "A1", ["a1", "a2", "a3", "a4"]),
        rk(5, "ドラゴン", "B1", ["b1", "b2", "b3", "b4"]),
    ]), ev("2", "2026-06-15", [
        rk(1, "ドラゴン", "A2", ["a1", "a2", "a3", "a4"]),
        rk(6, "ドラゴン", "B2", ["b1", "b2", "b3", "b4"]),
    ]), ev("3", "2026-06-20", [
        rk(1, "ドラゴン", "A3", ["a1", "a2", "a3", "a4"]),
    ])]
    out = tiering.build_tiers(events, NMAP, TMAP)
    top, low = out["clusters"][0], out["clusters"][1]
    assert top["score"] == 9.0 and top["tier"] == 0 and top["wins"] == 3
    assert low["score"] == 2.0 and low["tier"] > 0


def test_consensus_and_flexible():
    # a4 三副都有(3張)、a5 只有一副(1/3 ≈ 0.33) → a5 進彈性不進共識
    events = [ev("1", "2026-06-10", [
        rk(1, "ドラゴン", "A1", ["a1", "a2", "a3", "a4"]),
        rk(2, "ドラゴン", "A2", ["a1", "a2", "a3", "a4"]),
        rk(3, "ドラゴン", "A3", ["a1", "a2", "a3", "a4", "a5"]),
    ])]
    out = tiering.build_tiers(events, NMAP, TMAP)
    c = out["clusters"][0]
    names = {r["name"] for r in c["consensus"]["main"]}
    assert "卡A4" in names and "卡A5" not in names
    assert "卡A5" in c["flexible"]
    assert all(r["num"] == 3 for r in c["consensus"]["main"])


def test_singleton_goes_to_others_and_hidden_deck_excluded():
    events = [ev("1", "2026-06-10", [
        rk(1, "ドラゴン", "A1", ["a1", "a2", "a3"]),
        rk(2, "ドラゴン", "A2", ["a1", "a2", "a3"]),
        rk(3, "エルフ", "LONE", ["b1", "b2", "b3"]),
        {"rank": 4, "class": "エルフ", "deck_code": None,
         "list": [], "evolve": []},                       # 未公開牌組
    ])]
    out = tiering.build_tiers(events, NMAP, TMAP)
    assert len(out["clusters"]) == 1
    assert out["others"] == {"clusters": 1, "decks": 1}
    assert out["total_decks"] == 3


def test_window_filters_old_events():
    events = [ev("old", "2026-01-01", [rk(1, "ドラゴン", "OLD", ["a1", "a2"]),
                                       rk(2, "ドラゴン", "OLD2", ["a1", "a2"])]),
              ev("new", "2026-06-20", [rk(1, "ドラゴン", "N1", ["b1", "b2"]),
                                       rk(2, "ドラゴン", "N2", ["b1", "b2"])])]
    out = tiering.build_tiers(events, NMAP, TMAP, window_days=30)
    assert out["total_decks"] == 2
    assert out["clusters"][0]["samples"][0]["code"] in ("N1", "N2")
