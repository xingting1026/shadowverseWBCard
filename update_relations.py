"""抓官方單卡頁的「関連カード」存進 DB（每日自動更新的一環，也可手動跑）。

只抓還沒抓過的卡，所以首次回補全卡池要跑很久（約 7600 張 × 請求間隔），
之後每天只補新彈的卡。

用法：
  python update_relations.py                 # 補全部還沒抓的卡
  python update_relations.py --limit 400     # 這次最多抓 400 張（Actions 用，避免超時）
  python update_relations.py --delay 0.5     # 覆寫請求間隔（預設 config.REQUEST_DELAY）
"""
import argparse
from sve_meta import db, cardmaster
from sve_meta.config import DB_PATH


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="這次最多抓幾張")
    p.add_argument("--delay", type=float, default=None, help="每請求間隔秒數")
    a = p.parse_args()
    if a.delay is not None:
        cardmaster.REQUEST_DELAY = a.delay
    conn = db.get_conn(DB_PATH)
    db.init_db(conn)
    todo = conn.execute(
        "SELECT COUNT(*) FROM cards WHERE card_number NOT IN (SELECT card_number FROM relation_fetch)"
    ).fetchone()[0]
    print(f"還沒抓関連カード的卡：{todo} 張", flush=True)
    n = cardmaster.refresh_relations(conn, limit=a.limit, log=lambda s: print(s, flush=True))
    total = conn.execute("SELECT COUNT(DISTINCT card_number) FROM relations").fetchone()[0]
    print(f"這次抓了 {n} 張；目前 {total} 張卡有關聯資料")


if __name__ == "__main__":
    main()
