import math
from collections import Counter
from .classmap import normalize_class

_PIE_PALETTE = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
                "#911eb4", "#46f0f0", "#f032e6", "#808080", "#9a6324"]


def missing(deck, owned):
    """deck: [{'card_number','num'}], owned: {cn: qty} -> {cn: shortfall>0}"""
    out = {}
    for item in deck:
        cn, need = item["card_number"], item["num"]
        have = owned.get(cn, 0)
        if need > have:
            out[cn] = need - have
    return out


def completion_cost(deck, owned, prices):
    """回傳 (總日幣, 未定價卡號清單)。未定價的卡不計入總額。"""
    total = 0
    unpriced = []
    for cn, shortfall in missing(deck, owned).items():
        price = prices.get(cn)
        if price is None:
            unpriced.append(cn)
        else:
            total += shortfall * price
    return total, unpriced


def aggregate_meta(events, scope="top8"):
    """聚合甜甜圈資料。scope 語意為二元：'first' 只計各活動第 1 名，
    其餘任何值（含預設 'top8'）計入全部名次。class 透過 normalize_class 正規化，
    缺 class 的名次會落到 '不明'。"""
    counts = Counter()
    decks = []
    total_players = 0
    for ev in events:
        total_players += ev.get("players", 0)
        for r in ev.get("rankings", []):
            if scope == "first" and r.get("rank") != 1:
                continue
            cls = normalize_class(r.get("class"))
            counts[cls] += 1
            decks.append({"event_id": ev["event_id"], "rank": r.get("rank"),
                          "class": cls, "deck_code": r.get("deck_code")})
    return {"total_events": len(events), "total_players": total_players,
            "counts": dict(counts), "decks": decks}


def pie_slices(counts, cx=110, cy=110, r=100):
    """{label: n} → SVG 圓餅切片清單 [{label, n, pct, color, path}]，依 n 由大到小。
    單一切片占滿時用整圓路徑避免 arc 退化。"""
    total = sum(counts.values())
    if total <= 0:
        return []
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out = []
    start = -90.0
    for i, (label, n) in enumerate(items):
        frac = n / total
        end = start + frac * 360.0
        if frac >= 0.99999:
            path = (f"M {cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 "
                    f"a {r} {r} 0 1 0 {-2 * r} 0 Z")
        else:
            x1 = cx + r * math.cos(math.radians(start))
            y1 = cy + r * math.sin(math.radians(start))
            x2 = cx + r * math.cos(math.radians(end))
            y2 = cy + r * math.sin(math.radians(end))
            large = 1 if (end - start) > 180 else 0
            path = (f"M {cx} {cy} L {x1:.2f} {y1:.2f} "
                    f"A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f} Z")
        out.append({"label": label, "n": n, "pct": round(frac * 100, 1),
                    "color": _PIE_PALETTE[i % len(_PIE_PALETTE)], "path": path})
        start = end
    return out


def rank_decks(decks, owned, prices):
    """每副牌依補完成本升冪排序。
    輸入的每個 deck 必須含 'deck_code' 與 'list'（[{'card_number','num'}]，
    即 decklog 拆解後的牌表）—— 注意這與 aggregate_meta 產出的牌組摘要（無 'list'）不同。"""
    annotated = []
    for d in decks:
        miss = missing(d["list"], owned)
        cost, unpriced = completion_cost(d["list"], owned, prices)
        annotated.append({**d, "cost": cost, "missing": miss, "unpriced": unpriced})
    annotated.sort(key=lambda d: (d["cost"], len(d["unpriced"]), d.get("deck_code") or ""))
    return annotated
