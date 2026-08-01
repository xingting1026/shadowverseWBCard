"""補新彈資料 + 刷新近期價格（每日自動更新的一環，也可手動跑）。

用法：
  python update_sets.py                # 補新彈卡表+價格，並刷新近 30 天用到的 set 價格
  python update_sets.py --no-prices   # 只補新彈，不刷價
"""
import argparse
from sve_meta import db, setsync
from sve_meta.config import DB_PATH


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-prices", action="store_true", help="不刷新近期 set 價格")
    p.add_argument("--price-days", type=int, default=30,
                   help="刷新近幾天入賞牌組用到的 set 價格（預設 30）")
    a = p.parse_args()
    conn = db.get_conn(DB_PATH)
    db.init_db(conn)
    setsync.sync(conn, price_days=None if a.no_prices else a.price_days)


if __name__ == "__main__":
    main()
