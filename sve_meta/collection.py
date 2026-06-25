def set_owned(conn, card_number, qty):
    qty = max(0, min(3, int(qty)))
    conn.execute(
        "INSERT INTO owned(card_number, qty) VALUES(?,?) "
        "ON CONFLICT(card_number) DO UPDATE SET qty=excluded.qty",
        (card_number, qty))
    conn.commit()

def get_owned(conn):
    """只回 qty>0 的卡（被夾成 0 的卡不會出現在結果裡）。"""
    rows = conn.execute("SELECT card_number, qty FROM owned WHERE qty>0")
    return {r["card_number"]: r["qty"] for r in rows}
