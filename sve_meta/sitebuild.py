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
            if cls == "不明":       # 店家沒登錄職業的名次：不顯示（之後補登會自動回來）
                continue
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


def export_effects(conn, used_cns, nmap, tmap):
    """日文牌效：{卡名: {"B"|"E": [牌效, flavor]}}。
    同名所有印刷共用一份（規則上同名同效），基本/進化分開；
    只含牌組用到的卡名，代表文字取卡號最小且有牌效的印刷。"""
    wanted = {(nmap.get(cn, cn), byname.is_evolve(tmap.get(cn))) for cn in used_cns}
    eff = {}
    rows = conn.execute(
        "SELECT card_number, name, type, text, flavor FROM cards "
        "WHERE text IS NOT NULL AND text != '' "
        "ORDER BY text_full DESC, card_number")   # 優先用單卡頁抓的完整全文
    for r in rows:
        ev = byname.is_evolve(r["type"])
        if (r["name"], ev) not in wanted:
            continue
        eff.setdefault(r["name"], {}).setdefault(
            "E" if ev else "B", [r["text"], r["flavor"] or ""])
    return eff


def build_usage_index(month_datas):
    """卡片查詢用的反向索引：卡號 → 用過它的『第 1 名』牌組清單。
    依 set 拆檔（查一張卡只需下載該 set 的小 JSON）。
    回傳 {set_code: {cn: [[月份, 牌組碼, 活動, 日期, 人數, 張數], ...]}}，
    每張卡的清單按日期新到舊。"""
    usage = {}
    for md in month_datas:
        for ch in md["champions"]:
            deck = md["decks"].get(ch["code"])
            if not deck:
                continue
            copies = {}
            for cn, num in deck["main"] + deck["evo"]:
                copies[cn] = copies.get(cn, 0) + num
            for cn, num in copies.items():
                usage.setdefault(cn.split("-")[0], {}).setdefault(cn, []).append(
                    [md["month"], ch["code"], ch["event"], ch["date"],
                     ch["players"], num])
    for by_cn in usage.values():
        for rows in by_cn.values():
            rows.sort(key=lambda r: r[3], reverse=True)
    return usage


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
    todo = [cn for cn in sorted(cns)
            if not (cache_dir / f"{cn}.jpg").exists()
            or imgproxy.is_placeholder(cache_dir / f"{cn}.jpg")]  # 佔位圖每天重試
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
    # [卡名, 單價, 是否進化卡]——進化旗標讓前端按名字合併使用紀錄時，基本/進化分開計
    _write_json(out / "data" / "cards.json",
                {cn: [nmap.get(cn, cn), price_table.get(cn),
                      1 if byname.is_evolve(tmap.get(cn)) else 0] for cn in used})

    usage = build_usage_index(month_datas)
    for set_code, by_cn in usage.items():
        _write_json(out / "data" / "usage" / f"{set_code}.json", by_cn)

    effects = export_effects(conn, used, nmap, tmap)
    _write_json(out / "data" / "effects.ja.json", effects)
    zh_path = Path(__file__).resolve().parent.parent / "translations" / "effects.zh.json"
    if zh_path.exists():                    # 繁中翻譯（人工/AI 維護，缺卡由前端 fallback 日文）
        _write_json(out / "data" / "effects.zh.json",
                    json.loads(zh_path.read_text(encoding="utf-8")))

    ai_path = Path(__file__).resolve().parent.parent / "ai_matrix.json"
    if ai_path.exists():                    # AI 對局勝率表（模擬器盲測結果，人工維護）
        _write_json(out / "data" / "ai-matrix.json",
                    json.loads(ai_path.read_text(encoding="utf-8")))

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
        # 佔位圖事後補成真圖時內容會變，所以比大小決定要不要重複製
        if src.exists() and (not dst.exists()
                             or dst.stat().st_size != src.stat().st_size):
            shutil.copy2(src, dst)
            copied += 1
    if log:
        log(f"site 產出完成：{len(months)} 個月份、{len(used)} 張卡、"
            f"{len(tiers['clusters'])} 個原型；複製卡圖 {copied} 張")
    return {"months": months, "cards": len(used), "clusters": len(tiers["clusters"])}
