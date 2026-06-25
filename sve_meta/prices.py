# sve_meta/prices.py
import re
import time
import requests
from bs4 import BeautifulSoup
from .config import YUYUTEI_SET_URL, USER_AGENT, REQUEST_DELAY


def parse_prices(html):
    """Parse yuyu-tei set page HTML and return {card_number: jpy_int}."""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for block in soup.select("div.card-product"):
        code_el = block.select_one("span.border")
        price_el = block.select_one("strong")
        if not code_el or not price_el:
            continue
        code = code_el.get_text(strip=True)
        m = re.search(r"[\d,]+", price_el.get_text())
        # 卡號一定含數字（如 BP06-001）；跳過無碼的版面雜訊（曾見過顯示為 "-"）
        if not code or not any(ch.isdigit() for ch in code) or not m:
            continue
        out[code] = int(m.group(0).replace(",", ""))
    return out


def _fetch_html(set_code):
    """Fetch the yuyu-tei set page HTML with rate-limiting."""
    time.sleep(REQUEST_DELAY)
    r = requests.get(
        YUYUTEI_SET_URL.format(set=set_code),
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()
    return r.text


def refresh_set(conn, set_code, fetcher=_fetch_html):
    """Fetch current prices for set_code and upsert into prices table.

    Skips cards that have is_manual=1 (manual overrides are preserved).
    """
    now = time.time()
    for cn, jpy in parse_prices(fetcher(set_code)).items():
        row = conn.execute(
            "SELECT is_manual FROM prices WHERE card_number=?", (cn,)
        ).fetchone()
        if row and row["is_manual"]:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO prices"
            "(card_number, jpy, fetched_at, source, is_manual) "
            "VALUES(?,?,?,?,0)",
            (cn, jpy, now, f"yuyu-tei:{set_code}"),
        )
    conn.commit()


def get_price(conn, card_number):
    """Return the JPY price for a single card, or None if not found."""
    row = conn.execute(
        "SELECT jpy FROM prices WHERE card_number=?", (card_number,)
    ).fetchone()
    return row["jpy"] if row else None


def get_all(conn):
    """Return all prices as {card_number: jpy}."""
    return {
        r["card_number"]: r["jpy"]
        for r in conn.execute("SELECT card_number, jpy FROM prices")
    }


def set_manual(conn, card_number, jpy):
    """Set a manual price override for card_number (is_manual=1)."""
    conn.execute(
        "INSERT OR REPLACE INTO prices"
        "(card_number, jpy, fetched_at, source, is_manual) "
        "VALUES(?,?,?,?,1)",
        (card_number, int(jpy), time.time(), "manual"),
    )
    conn.commit()
