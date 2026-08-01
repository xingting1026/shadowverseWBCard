# sve_meta/sitebuild.py
"""把 sve_meta.db 匯出成純靜態網站（GitHub Pages 可直接部署）。

產出結構（out_dir，預設 site/）：
  index.html / tiers.html / champions.html / deck.html / static/*   ← 從 web/ 複製
  data/index.json                月份清單 + 產生時間
  data/month/YYYY-MM.json        該月賽事、牌組明細、冠軍最省組件
  data/tiers.json                近 30 天原型聚類（T0~T5）
  data/cards.json                {cn: [卡名, 單價或 null]}（只含用到的卡）
  img/{cn}.jpg                   卡圖縮圖（從 img_cache/ 複製；缺的先抓）
"""
import json
import time
import shutil
import hashlib
import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import byname, prices, events_store, tiering, cardmaster, imgproxy
from .classmap import normalize_class

WEB_SRC = Path(__file__).resolve().parent.parent / "web"


def month_bounds(month):
    y, m = int(month[:4]), int(month[5:7])
    nxt = datetime.date(y + 1, 1, 1) if m == 12 else datetime.date(y, m + 1, 1)
    return f"{y:04d}-{m:02d}-01", (nxt - datetime.timedelta(days=1)).isoformat()


def available_months(conn):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(start_date,1,7) m FROM events "
        "WHERE m != '' ORDER BY m")]


def cheapest_sections(ranking, nmap, tmap, cheap_id):
    """一副牌 → 最省組件版：每張換成同身分（卡名＋基本/進化）最便宜印刷。
    回傳 {"cost", "unpriced":[卡名], "main":[{cn,name,num,unit}], "evo":[...]}。"""
    any_cn = {}
    for cn, nm in nmap.items():
        any_cn.setdefault((nm, byname.is_evolve(tmap.get(cn))), cn)
    total, unpriced = 0, []

    def build(items, default_ev):
        nonlocal total
        agg = {}
        for it in items:
            cn = it["card_number"]
            nm = nmap.get(cn, cn)
            ev = byname.is_evolve(tmap[cn]) if cn in tmap else default_ev
            agg[(nm, ev)] = agg.get((nm, ev), 0) + (it.get("num") or 0)
        rows = []
        for (nm, ev), num in agg.items():
            cp = cheap_id.get((nm, ev))
            if cp:
                total += cp["jpy"] * num
                rows.append({"cn": cp["card_number"], "name": nm,
                             "num": num, "unit": cp["jpy"]})
            else:
                unpriced.append(nm)
                rows.append({"cn": any_cn.get((nm, ev), nm), "name": nm,
                             "num": num, "unit": None})
        rows.sort(key=lambda r: (-(r["unit"] or 0) * r["num"], r["name"]))
        return rows

    main = build(ranking.get("list") or [], False)
    evo = build(ranking.get("evolve") or [], True)
    return {"cost": total, "unpriced": unpriced, "main": main, "evo": evo}


def export_month(conn, month, nmap, tmap, cheap_id):
    """一個月份 → month JSON dict。"""
    events = events_store.load_events(conn, *month_bounds(month))
    evs_out, decks, champions, cheapest = [], {}, [], {}
    for ev in events:
        rks = []
        for r in ev.get("rankings", []):
            code = r.get("deck_code") or None
            cls = normalize_class(r.get("class"))
            has_list = bool(r.get("list") or r.get("evolve"))
            rks.append({"rank": r.get("rank"), "cls": cls,
                        "code": code if has_list else None})
            if code and has_list and code not in decks:
                decks[code] = {
                    "cls": cls,
                    "main": [[it["card_number"], it.get("num") or 0]
                             for it in r.get("list") or []],
                    "evo": [[it["card_number"], it.get("num") or 0]
                            for it in r.get("evolve") or []]}
            if code and has_list and r.get("rank") == 1:
                ch = cheapest_sections(r, nmap, tmap, cheap_id)
                cheapest[code] = ch
                champions.append({"code": code, "cls": cls,
                                  "event": ev.get("title") or "",
                                  "date": (ev.get("start_date") or "")[:10],
                                  "players": ev.get("players") or 0,
                                  "cost": ch["cost"],
                                  "unpriced": len(ch["unpriced"])})
        evs_out.append({"id": ev["event_id"], "title": ev.get("title") or "",
                        "store": ev.get("store") or "",
                        "players": ev.get("players") or 0,
                        "date": (ev.get("start_date") or "")[:10],
                        "rankings": rks})
    champions.sort(key=lambda d: (d["cost"], d["unpriced"], d["code"]))
    return {"month": month, "events": evs_out, "decks": decks,
            "champions": champions, "cheapest": cheapest}


def _used_card_numbers(month_datas, tiers):
    used = set()
    for md in month_datas:
        for d in md["decks"].values():
            used.update(cn for cn, _ in d["main"])
            used.update(cn for cn, _ in d["evo"])
        for ch in md["cheapest"].values():
            used.update(r["cn"] for r in ch["main"] + ch["evo"])
    for c in tiers["clusters"]:
        used.update(r["cn"] for r in c["consensus"]["main"] + c["consensus"]["evo"])
    return used


def _stamp_assets(out):
    """HTML 裡的 css/js 連結加上內容雜湊（?v=xxx）破快取：
    GitHub Pages/瀏覽器會快取靜態資產，改版後舊 JS 可能繼續用；
    內容一變雜湊就變，瀏覽器視為新網址立即重抓。"""
    for name in ("static/style.css", "static/app.js"):
        p = out / name
        if not p.exists():
            continue
        v = hashlib.md5(p.read_bytes()).hexdigest()[:10]
        for html in out.glob("*.html"):
            s = html.read_text(encoding="utf-8")
            html.write_text(s.replace(f'"{name}"', f'"{name}?v={v}"'),
                            encoding="utf-8")


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def fetch_missing_images(conn, cns, cache_dir, delay=0.1, workers=4, log=print):
    """把還沒有縮圖的卡抓進 img_cache。少量 worker 平行（每張圖網路延遲遠大於下載量），
    每張之間仍留 delay 秒禮貌間隔。回傳新抓張數。
    DB 查詢先在主執行緒做完，worker 只做 HTTP + 寫檔（sqlite 連線不跨執行緒）。"""
    cache_dir = Path(cache_dir)
    todo = [cn for cn in sorted(cns) if not (cache_dir / f"{cn}.jpg").exists()]
    if not todo:
        return 0
    imgs = {}
    for cn in todo:
        card = cardmaster.get(conn, cn)
        imgs[cn] = (card.get("img") or None) if card else None

    def one(cn):
        imgproxy.fetch_image(cn, img=imgs[cn], cache_dir=cache_dir)
        if delay:
            time.sleep(delay)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, _ in enumerate(ex.map(one, todo)):
            if log and (i + 1) % 200 == 0:
                log(f"  卡圖 {i + 1}/{len(todo)}")
    return len(todo)


def export_site(conn, out_dir, img_cache_dir, web_src=WEB_SRC,
                fetch_images=True, image_delay=0.1, log=print):
    """完整產站。"""
    out = Path(out_dir)
    nmap = byname.name_map(conn)
    tmap = byname.type_map(conn)
    cheap_id = byname.cheapest_by_identity(conn)

    months = available_months(conn)
    month_datas = []
    for m in months:
        md = export_month(conn, m, nmap, tmap, cheap_id)
        _write_json(out / "data" / "month" / f"{m}.json", md)
        month_datas.append(md)

    all_events = events_store.load_events(conn)
    tiers = tiering.build_tiers(all_events, nmap, tmap)
    _write_json(out / "data" / "tiers.json", tiers)

    used = _used_card_numbers(month_datas, tiers)
    price_table = prices.get_all(conn)
    _write_json(out / "data" / "cards.json",
                {cn: [nmap.get(cn, cn), price_table.get(cn)] for cn in used})

    _write_json(out / "data" / "index.json",
                {"generated_at": datetime.datetime.now(datetime.timezone.utc)
                    .strftime("%Y-%m-%d %H:%M UTC"),
                 "months": months, "latest": months[-1] if months else None})

    if fetch_images:
        n = fetch_missing_images(conn, used, img_cache_dir, delay=image_delay, log=log)
        if log:
            log(f"新抓卡圖 {n} 張")

    # 靜態頁 + 卡圖進 site/
    shutil.copytree(web_src, out, dirs_exist_ok=True)
    _stamp_assets(out)
    img_out = out / "img"
    img_out.mkdir(parents=True, exist_ok=True)
    copied = 0
    for cn in used:
        src = Path(img_cache_dir) / f"{cn}.jpg"
        dst = img_out / f"{cn}.jpg"
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            copied += 1
    if log:
        log(f"site 產出完成：{len(months)} 個月份、{len(used)} 張卡、"
            f"{len(tiers['clusters'])} 個原型；複製卡圖 {copied} 張")
    return {"months": months, "cards": len(used), "clusters": len(tiers["clusters"])}
