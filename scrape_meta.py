"""Shadowverse Evolve 大會結果爬取 + 持久化（牌組以名稱存）。資料最早到 2024-05-01。

用法：
  python scrape_meta.py                                   # 近 30 天、≥8 人（預設）
  python scrape_meta.py --days 14 --min 16                # 近 14 天、≥16 人
  python scrape_meta.py --from 2024-05-01 --to 2024-12-31 --min 8
  python scrape_meta.py --from 2024-05-01 --to 2026-06-30 --by-month   # 逐月抓（做歷史 meta 推薦）

提醒：每請求間隔 1 秒。整段歷史（約 3400+ 場）會跑很久（數十分鐘～數小時）。
做歷史 meta 建議用 --by-month：一個月一段、有進度、可隨時 Ctrl+C（已抓的月份會留著），
或提高 --min 只收大型賽事。可重跑（INSERT OR REPLACE）。卡名解析靠 cards 表，請先跑過 init_data.py。
"""
import argparse
import datetime
from sve_meta import db, bushinavi, events_store
from sve_meta.config import DB_PATH


def _scrape_range(c, start, end, minp):
    events = bushinavi.fetch_events(start, end, minp)
    events_store.resolve_and_nameify(c, events)
    events_store.store_events(c, events)
    return events


def _months(start, end):
    """產生 [(月初, 月末), ...] 覆蓋 start~end 的每個月。"""
    s = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    cur = datetime.date(s.year, s.month, 1)
    out = []
    while cur <= e:
        nxt = (datetime.date(cur.year + 1, 1, 1) if cur.month == 12
               else datetime.date(cur.year, cur.month + 1, 1))
        out.append((max(cur, s).isoformat(),
                    min(nxt - datetime.timedelta(days=1), e).isoformat()))
        cur = nxt
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="frm", help="起始日 YYYY-MM-DD")
    p.add_argument("--to", dest="to", help="結束日 YYYY-MM-DD")
    p.add_argument("--days", type=int, default=30, help="未給 --from 時，往回幾天（預設 30）")
    p.add_argument("--min", dest="minp", type=int, default=8, help="最小參賽人數（預設 8）")
    p.add_argument("--by-month", action="store_true", help="逐月抓取（適合大區間歷史）")
    p.add_argument("--delay", type=float, default=None,
                   help="每請求間隔秒數（預設 1.0；回補歷史可設 0.3~0.5 加速，但較可能被限流）")
    a = p.parse_args()

    if a.delay is not None:                 # 覆寫 decklog / bushinavi 的請求間隔
        from sve_meta import decklog, bushinavi
        decklog.REQUEST_DELAY = a.delay
        bushinavi.REQUEST_DELAY = a.delay
        print(f"請求間隔設為 {a.delay} 秒", flush=True)

    today = datetime.date.today()
    end = a.to or today.isoformat()
    start = a.frm or (today - datetime.timedelta(days=a.days)).isoformat()

    c = db.get_conn(DB_PATH)
    db.init_db(c)
    print(f"區間 {start} ~ {end}，最小人數 {a.minp}", flush=True)

    if a.by_month:
        total = 0
        for ms, me in _months(start, end):
            evs = _scrape_range(c, ms, me, a.minp)
            total += len(evs)
            print(f"  → {ms[:7]}：存 {len(evs)} 場（累計 {total}）", flush=True)
        print(f"✓ 逐月完成，共 {total} 場", flush=True)
    else:
        print("抓取 + 解析中（會打 Bushi-Navi + DeckLog，稍候）...", flush=True)
        evs = _scrape_range(c, start, end, a.minp)
        n = sum(len(e.get("rankings", [])) for e in evs)
        print(f"✓ 已存 {len(evs)} 場、{n} 副牌組", flush=True)


if __name__ == "__main__":
    main()
