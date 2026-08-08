"""一次性回補：重抓全部 set 的官方卡表，補進日文牌效（text/flavor 欄位）。
可重跑；之後的新彈由每日 update_sets.py 自動帶到，不需再跑這支。"""
from sve_meta import db, cardmaster, setsync
from sve_meta.config import DB_PATH


def main():
    conn = db.get_conn(DB_PATH)
    db.init_db(conn)
    sets = [r[0] for r in conn.execute(
        "SELECT DISTINCT set_code FROM cards WHERE set_code != '' ORDER BY set_code")]
    fails = []
    for i, s in enumerate(sets, 1):
        ok = False
        for exp in setsync._expansion_candidates(s):
            try:
                cardmaster.refresh_set(conn, exp)
                ok = True
                break
            except Exception:
                continue
        if not ok:
            fails.append(s)
        n = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE text IS NOT NULL AND text != ''"
        ).fetchone()[0]
        print(f"[{i}/{len(sets)}] {s} {'✓' if ok else '✗'} | 有牌效累計 {n}", flush=True)
    print("抓不到的 set:", fails or "（無）")


if __name__ == "__main__":
    main()
