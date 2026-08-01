# sve_meta/tiering.py
"""近期 Meta 牌組一覽：把入賞牌組自動聚類成「原型」並分 T0~T5。

使用者不知道社群俗名（骰子夢、跳費龍…），而同原型的牌組彼此只差幾張卡。
做法：同職業內以「卡名＋基本/進化」身分的張數 multiset 算 Jaccard 相似度，
超過門檻視為同原型（union-find）。每群自動取「特徵卡」命名、產出「共識牌表」
（大家幾乎都帶的卡）與「彈性卡位」（部分人帶的卡）。

所有可調參數集中在下方常數。
"""
import math
import datetime
from collections import Counter
from . import byname
from .classmap import normalize_class

WINDOW_DAYS = 30          # 視窗：最新賽事日往回幾天
SIM_THRESHOLD = 0.5       # multiset Jaccard ≥ 此值視為同原型
MIN_CLUSTER_SIZE = 2      # 樣本數低於此的群歸入「其他」不列檔位
SIGNATURE_TOP = 2         # 命名用幾張特徵卡
CONSENSUS_MIN = 0.5       # 出現率 ≥ 此值進共識牌表
FLEXIBLE_MIN = 0.25       # 出現率在 [FLEXIBLE_MIN, CONSENSUS_MIN) 為彈性卡位
SAMPLES_TOP = 3           # 每群附幾副實際範例牌組

# 入賞計分：rank → 權重（沒列到的名次都算 1）
RANK_WEIGHTS = {1: 3.0, 2: 2.0, 3: 1.5, 4: 1.5}
DEFAULT_RANK_WEIGHT = 1.0

# 檔位門檻：(tier, 群分數 / 最強群分數 的下限)，由上往下取第一個符合的
TIER_CUTS = [(0, 0.70), (1, 0.45), (2, 0.25), (3, 0.12), (4, 0.05)]
LAST_TIER = 5


def rank_weight(rank):
    return RANK_WEIGHTS.get(rank, DEFAULT_RANK_WEIGHT)


def deck_vector(ranking, nmap, tmap):
    """一副牌 → Counter{identity_key: 張數}（主＋進化合併，同名基本/進化分開）。"""
    vec = Counter()
    for items, default_ev in ((ranking.get("list") or [], False),
                              (ranking.get("evolve") or [], True)):
        for it in items:
            cn = it["card_number"]
            nm = nmap.get(cn) or cn
            ev = byname.is_evolve(tmap[cn]) if cn in tmap else default_ev
            vec[byname.identity_key(nm, ev)] += it.get("num") or 0
    return vec


def similarity(a, b):
    """multiset Jaccard：Σmin / Σmax。兩空集合視為 0。"""
    keys = a.keys() | b.keys()
    smin = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    smax = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return smin / smax if smax else 0.0


def _cluster_indices(vecs, threshold=SIM_THRESHOLD):
    """union-find：兩兩相似度 ≥ threshold 併同群。回傳群列表（各為 index list）。"""
    parent = list(range(len(vecs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            if similarity(vecs[i], vecs[j]) >= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    groups = {}
    for i in range(len(vecs)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _split_identity(key):
    """identity_key → (name, is_evolve)。"""
    nm, flag = key.rsplit("\x01", 1)
    return nm, flag == "E"


def signature_names(cluster_vecs, class_vecs, top=SIGNATURE_TOP):
    """群的特徵卡名：群內出現率 × 職業內鑑別度（IDF）最高的『基本』卡。
    出現率 < 0.5 的卡不拿來命名（那是彈性卡不是核心卡）。"""
    n_cluster, n_class = len(cluster_vecs), len(class_vecs)
    presence = Counter()
    for v in cluster_vecs:
        presence.update({k for k in v if not _split_identity(k)[1]})
    df = Counter()
    for v in class_vecs:
        df.update({k for k in v if not _split_identity(k)[1]})
    scored = []
    for k, c in presence.items():
        p = c / n_cluster
        if p < 0.5:
            continue
        idf = math.log((n_class + 1) / (df[k] + 1)) + 0.1   # +0.1：全職業都帶也至少留出現率序
        scored.append((p * idf, p, _split_identity(k)[0]))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return [nm for _, _, nm in scored[:top]]


def _consensus_section(decks_items, nmap, tmap, default_ev, n_decks):
    """一個區（主/進化）的共識與彈性。decks_items: 每副牌該區的 [{card_number,num}]。
    回傳 (consensus_rows, flexible_names)；consensus_rows=[{cn,name,num}]，
    cn 取群內該卡名最常用的印刷（給前端顯示卡圖）。"""
    per_name_counts = {}    # name -> [各副牌張數]
    per_name_cns = {}       # name -> Counter{cn}
    for items in decks_items:
        agg = {}
        for it in items:
            cn = it["card_number"]
            nm = nmap.get(cn) or cn
            agg.setdefault(nm, [0, Counter()])
            agg[nm][0] += it.get("num") or 0
            agg[nm][1][cn] += it.get("num") or 0
        for nm, (num, cns) in agg.items():
            per_name_counts.setdefault(nm, []).append(num)
            per_name_cns.setdefault(nm, Counter()).update(cns)
    consensus, flexible = [], []
    for nm, counts in per_name_counts.items():
        p = len(counts) / n_decks
        if p >= CONSENSUS_MIN:
            counts_sorted = sorted(counts)
            med = counts_sorted[len(counts_sorted) // 2]
            consensus.append({"cn": per_name_cns[nm].most_common(1)[0][0],
                              "name": nm, "num": med, "p": round(p, 2)})
        elif p >= FLEXIBLE_MIN:
            flexible.append((p, nm))
    consensus.sort(key=lambda r: (-r["num"], -r["p"], r["name"]))
    flexible.sort(key=lambda t: (-t[0], t[1]))
    return consensus, [nm for _, nm in flexible]


def collect_entries(events, nmap, tmap, window_days=WINDOW_DAYS):
    """視窗內、有公開牌表的入賞 → entry 列表。視窗終點取「最新賽事日」
    （而非今天），就算爬蟲停更幾天，頁面仍顯示最後 30 天有資料的區間。"""
    dates = [(e.get("start_date") or "")[:10] for e in events]
    dates = [d for d in dates if d]
    if not dates:
        return [], None, None
    end = max(dates)
    start = (datetime.date.fromisoformat(end)
             - datetime.timedelta(days=window_days)).isoformat()
    entries = []
    for ev in events:
        d = (ev.get("start_date") or "")[:10]
        if not d or d < start or d > end:
            continue
        for r in ev.get("rankings", []):
            if not (r.get("list") or r.get("evolve")):
                continue
            entries.append({
                "code": r.get("deck_code"), "rank": r.get("rank"),
                "cls": normalize_class(r.get("class")),
                "event": ev.get("title") or "", "date": d,
                "players": ev.get("players") or 0,
                "list": r.get("list") or [], "evolve": r.get("evolve") or [],
                "vec": deck_vector(r, nmap, tmap),
            })
    return entries, start, end


def build_tiers(events, nmap, tmap, window_days=WINDOW_DAYS):
    """主入口：events（events_store.load_events 形狀）→ tiers 資料結構。"""
    entries, start, end = collect_entries(events, nmap, tmap, window_days)
    by_class = {}
    for e in entries:
        by_class.setdefault(e["cls"], []).append(e)

    clusters = []
    others_clusters = others_decks = 0
    for cls, group in by_class.items():
        vecs = [e["vec"] for e in group]
        for idxs in _cluster_indices(vecs):
            members = [group[i] for i in idxs]
            if len(members) < MIN_CLUSTER_SIZE:
                others_clusters += 1
                others_decks += len(members)
                continue
            score = sum(rank_weight(m["rank"]) for m in members)
            wins = sum(1 for m in members if m["rank"] == 1)
            sig = signature_names([m["vec"] for m in members], vecs)
            main_c, main_f = _consensus_section(
                [m["list"] for m in members], nmap, tmap, False, len(members))
            evo_c, evo_f = _consensus_section(
                [m["evolve"] for m in members], nmap, tmap, True, len(members))
            samples = sorted(members, key=lambda m: (m["rank"] or 99,
                                                     -m["players"], m["date"]))
            clusters.append({
                "cls": cls,
                "label": "＋".join(sig) if sig else "（無特徵卡）",
                "signature": sig, "score": round(score, 1),
                "n": len(members), "wins": wins,
                "consensus": {"main": main_c, "evo": evo_c},
                "flexible": main_f + [f for f in evo_f if f not in main_f],
                "samples": [{"code": m["code"], "month": m["date"][:7],
                             "rank": m["rank"], "event": m["event"],
                             "date": m["date"], "players": m["players"]}
                            for m in samples[:SAMPLES_TOP]],
            })

    clusters.sort(key=lambda c: -c["score"])
    total = sum(c["score"] for c in clusters) or 1.0
    max_score = clusters[0]["score"] if clusters else 1.0
    for c in clusters:
        ratio = c["score"] / max_score
        c["share"] = round(100 * c["score"] / total, 1)
        c["tier"] = LAST_TIER
        for tier, cut in TIER_CUTS:
            if ratio >= cut:
                c["tier"] = tier
                break

    return {"window": {"start": start, "end": end, "days": window_days},
            "total_decks": len(entries),
            "clusters": clusters,
            "others": {"clusters": others_clusters, "decks": others_decks}}
