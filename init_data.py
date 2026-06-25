"""一次性灌入卡表 + 價格。

用法：
    python init_data.py

會對「官方卡表」與「yuyu-tei」逐 set 抓取（每個請求間隔 1 秒，全部約 10+ 分鐘）。
容錯：單一 set 失敗不中斷整體，最後印出失敗清單。可重跑（INSERT OR REPLACE）。
手動填過的價（is_manual=1）不會被覆蓋。
"""
from sve_meta import db, cardmaster, prices
from sve_meta.config import DB_PATH

# 官方卡表的全部 expansion 代號（2026-06 抓自 shadowverse-evolve.com/cardlist/）。
# cardmaster 用大寫；prices 自動轉小寫對應 yuyu-tei 的 /sell/sev/s/{code}。
SETS = [
    "BP01", "BP02", "BP03", "BP04", "BP05", "BP06", "BP07", "BP08", "BP09", "BP10",
    "BP11", "BP12", "BP13", "BP14", "BP15", "BP16", "BP17", "BP18", "BP19", "BP20",
    "CP01", "CP02", "CP03", "CP04", "ECP01", "ECP02",
    "SD01", "SD02", "SD03", "SD04", "SD05", "SD06", "SD07", "SD08",
    "CSD01", "CSD02A", "CSD02B", "CSD02C", "CSD03A", "CSD03B", "DSD01",
    "EBD01", "EBD02", "EBD03", "EBD04", "ETD01", "ETD02", "ETD03",
    "LCS01", "PCS01", "SCS01", "SP01", "PR",
]


def main():
    c = db.get_conn(DB_PATH)
    db.init_db(c)
    card_fail, price_fail = [], []
    for i, s in enumerate(SETS, 1):
        try:
            cardmaster.refresh_set(c, s)
        except Exception as e:
            card_fail.append(s)
            print(f"  ✗ 卡表 {s}: {type(e).__name__}", flush=True)
        try:
            prices.refresh_set(c, s.lower())
        except Exception:
            price_fail.append(s)
            print(f"  · 無價 {s}（yuyu-tei 未上架）", flush=True)
        n = c.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        p = c.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        print(f"[{i}/{len(SETS)}] {s} 完成 | 累計卡 {n} · 價 {p}", flush=True)
    print("=== 全部完成 ===")
    print("卡表抓不到:", card_fail or "（無）")
    print("yuyu-tei 無價:", price_fail or "（無）")


if __name__ == "__main__":
    main()
