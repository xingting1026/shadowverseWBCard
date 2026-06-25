import datetime
from flask import Flask, render_template, request, jsonify, send_file
from .config import DB_PATH, IMG_CACHE_DIR
from . import (db, cardmaster, prices, decklog, bushinavi,
               engine, imgproxy, byname, events_store)

RECENT_DAYS = 30


def create_app(db_path=DB_PATH):
    app = Flask(__name__)
    app.config["DBFILE"] = str(db_path)

    _startup = db.get_conn(db_path)      # 啟動時建表一次
    db.init_db(_startup)
    _startup.close()

    def conn():
        return db.get_conn(db_path)

    def date_range():
        """檢視期間：?start=&end= 指定任意歷史區間；未給則預設近 RECENT_DAYS 天。"""
        today = datetime.date.today()
        end = request.args.get("end") or today.isoformat()
        start = request.args.get("start") or (
            today - datetime.timedelta(days=RECENT_DAYS)).isoformat()
        return start, end

    def available_months(c):
        return [r[0] for r in c.execute(
            "SELECT DISTINCT substr(start_date,1,7) m FROM events "
            "WHERE m != '' ORDER BY m")]

    def month_bounds(month):
        y, m = int(month[:4]), int(month[5:7])
        nxt = datetime.date(y + 1, 1, 1) if m == 12 else datetime.date(y, m + 1, 1)
        return f"{y:04d}-{m:02d}-01", (nxt - datetime.timedelta(days=1)).isoformat()

    def selected_month(c):
        """月份切換：?month=YYYY-MM；未給則用最新有資料的月份。"""
        months = available_months(c)
        sel = request.args.get("month")
        if sel not in months:
            sel = months[-1] if months else None
        return months, sel

    # ---------- 收藏（owned 只存瀏覽器 localStorage；伺服器只提供卡表）----------
    @app.route("/")
    def index():
        return render_template("collection.html", sets=cardmaster.by_set(conn()))

    @app.route("/collection")
    def collection_page():
        return index()

    # ---------- 抓賽果（持久化）----------
    @app.post("/api/fetch")
    def api_fetch():
        d = request.get_json()
        c = conn()
        events = bushinavi.fetch_events(d["start"], d["end"], int(d["min"]))
        events_store.resolve_and_nameify(c, events)
        events_store.store_events(c, events)
        return jsonify({"events": len(events),
                        "players": sum(e.get("players", 0) for e in events)})

    # ---------- Meta 總表（近一個月）----------
    @app.get("/meta")
    def meta_page():
        scope = request.args.get("scope", "top8")
        c = conn()
        start, end = date_range()
        events = events_store.load_events(c, start=start, end=end)
        agg = engine.aggregate_meta(events, scope=scope)
        pie = engine.pie_slices(agg["counts"])
        return render_template("meta.html", agg=agg, scope=scope, events=events,
                               pie=pie, start=start, end=end)

    # ---------- 牌組單卡 + diff ----------
    @app.get("/deck/<code>")
    def deck_page(code):
        c = conn()
        deck = decklog.fetch_deck(c, code)
        nmap = byname.name_map(c)
        tmap = byname.type_map(c)
        main_items, evo_items = deck.get("list", []), deck.get("evolve", [])

        # 最省組建模式：每張換成「同身分（卡名＋是否進化）最便宜印刷」，分主/進化兩區
        if request.args.get("cheapest") == "1":
            cheap_id = byname.cheapest_by_identity(c)
            any_cn = {}
            for cn, nm in nmap.items():
                any_cn.setdefault((nm, byname.is_evolve(tmap.get(cn))), cn)
            total, unpriced = [0], []

            def build(items, default_ev):
                agg = {}
                for it in items:
                    cn = it["card_number"]; nm = nmap.get(cn, cn)
                    ev = byname.is_evolve(tmap[cn]) if cn in tmap else default_ev
                    agg[(nm, ev)] = agg.get((nm, ev), 0) + (it.get("num") or 0)
                rows = []
                for (nm, ev), num in agg.items():
                    cp = cheap_id.get((nm, ev))
                    if cp:
                        total[0] += cp["jpy"] * num
                        rows.append({"card_number": cp["card_number"], "name": nm,
                                     "num": num, "unit": cp["jpy"], "unpriced": False})
                    else:
                        unpriced.append(nm)
                        rows.append({"card_number": any_cn.get((nm, ev), nm), "name": nm,
                                     "num": num, "unit": None, "unpriced": True})
                return rows

            sections = [{"title": "主牌組", "rows": build(main_items, False)},
                        {"title": "進化牌組", "rows": build(evo_items, True)}]
            return render_template("deck.html", code=code, deck=deck, sections=sections,
                                   cost=total[0], unpriced=unpriced, cheapest=True)

        # 一般模式：渲染卡 + 每張單價（data-price）；有/缺/補完成本由瀏覽器用 localStorage 即時算
        price_table = prices.get_all(c)

        def nrows(items):
            out = []
            for it in items:
                cn = it["card_number"]
                out.append({"card_number": cn, "name": nmap.get(cn, cn),
                            "num": it["num"], "price": price_table.get(cn)})
            return out

        sections = [{"title": "主牌組", "rows": nrows(main_items)},
                    {"title": "進化牌組", "rows": nrows(evo_items)}]
        return render_template("deck.html", code=code, deck=deck, sections=sections,
                               cheapest=False)

    # ---------- 排行榜1：補完成本（依你的收藏，卡號）----------
    @app.get("/ranking")
    def ranking_page():
        # 伺服器只給「該月每副牌的卡表 + 價格表」；補完成本由瀏覽器用 localStorage 收藏即時算
        c = conn()
        months, sel = selected_month(c)
        decks, price_cns = [], set()
        if sel:
            for ev in events_store.load_events(c, *month_bounds(sel)):
                for r in ev["rankings"]:
                    cards = r.get("list", []) + r.get("evolve", [])
                    if not cards:
                        continue
                    decks.append({"code": r["deck_code"], "cls": r["class"],
                                  "cards": [{"cn": x["card_number"], "num": x["num"]}
                                            for x in cards]})
                    price_cns.update(x["card_number"] for x in cards)
        allp = prices.get_all(c)
        pricemap = {cn: allp[cn] for cn in price_cns if cn in allp}
        return render_template("ranking.html", months=months, sel=sel,
                               data={"decks": decks, "prices": pricemap})

    # ---------- 排行榜2：全新組建最省（該月第1名，名稱取最便宜印刷）----------
    @app.get("/ranking2")
    def ranking2_page():
        c = conn()
        months, sel = selected_month(c)
        nmap = byname.name_map(c)
        tmap = byname.type_map(c)
        price_by_id = byname.cheapest_price_by_identity_key(c)
        events = events_store.load_events(c, *month_bounds(sel)) if sel else []
        decks = []
        for ev in events:
            for r in ev["rankings"]:
                if r.get("rank") == 1 and (r.get("list") or r.get("evolve")):
                    deckobj = {"list": r.get("list", []), "evolve": r.get("evolve", [])}
                    decks.append({"deck_code": r["deck_code"], "class": r["class"],
                                  "event": ev.get("title", ""),
                                  "list": byname.deck_as_identity_items(deckobj, nmap, tmap)})
        ranked = engine.rank_decks(decks, {}, price_by_id)   # owned={} → 全新組建成本（主+進化）
        return render_template("ranking2.html", ranked=ranked, months=months, sel=sel)

    # ---------- 卡圖代理 ----------
    @app.get("/img/<card_number>")
    def img(card_number):
        card = cardmaster.get(conn(), card_number)
        img_rel = (card.get("img") or None) if card else None
        path = imgproxy.fetch_image(card_number, img=img_rel, cache_dir=IMG_CACHE_DIR)
        return send_file(path, mimetype="image/png")

    return app
