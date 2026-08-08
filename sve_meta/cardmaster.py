# sve_meta/cardmaster.py
import re
import time
import requests
from bs4 import BeautifulSoup
from .config import CARDLIST_URL, CARDLIST_PAGE_URL, USER_AGENT, REQUEST_DELAY


def _txt(el):
    return el.get_text(strip=True) if el else ""


def _stat(el):
    """Extract numeric stat from a status-Item span, stripping the heading sub-span text."""
    if not el:
        return ""
    text = el.get_text(strip=True)
    for heading in el.select("span.heading"):
        text = text.replace(heading.get_text(strip=True), "", 1).strip()
    return text


def _effect_text(el):
    """牌效/flavor 區塊 → 純文字。行內小圖示（コスト/攻擊力/職業…）轉成 [alt] 標記，
    <br> 轉換行，行首尾空白清掉。"""
    if not el:
        return ""
    el = BeautifulSoup(str(el), "lxml")   # 複製再改；lxml 能容錯官方未閉合的 <img>
    for img in el.find_all("img"):
        img.replace_with(f"[{img.get('alt', '')}]")
    for br in el.find_all("br"):
        br.replace_with("\n")
    lines = [ln.strip() for ln in el.get_text().split("\n")]
    return "\n".join(ln for ln in lines if ln)


def parse_cardlist(html):
    """Parse a cardlist page HTML and return a list of card dicts.

    Real DOM (verified against BP17 fixture 2026-06-23):
      ul.cardlist-Result_List > li > div.center-Txtarea.txt
        p.number       → card code  e.g. BP17-001
        p.ttl          → Japanese name
        div.status > span.status-Item  (first plain one) → type e.g. フォロワー
        span.status-Item.status-Item-Cost  (contains span.heading + text) → cost
        span.status-Item.status-Item-Power → atk
        span.status-Item.status-Item-Hp   → def
    """
    soup = BeautifulSoup(html, "lxml")
    cards = []
    for ul in soup.select("ul.cardlist-Result_List"):
        for li in ul.select("li"):
            num = li.select_one("p.number")
            if not num:
                continue
            code = _txt(num)

            # Type: first status-Item span that is NOT a stat item
            type_text = ""
            status_div = li.select_one("div.status")
            if status_div:
                for span in status_div.select("span.status-Item"):
                    cls = span.get("class", [])
                    if "status-Item-Cost" not in cls and \
                       "status-Item-Power" not in cls and \
                       "status-Item-Hp" not in cls:
                        type_text = _txt(span)
                        break

            # 官方頁的真實卡圖路徑（最準；新舊 set 的分隔符 -/_ 由此直接拿到）
            img_el = li.select_one("img")
            img_src = img_el.get("src", "") if img_el else ""
            img_rel = img_src.split("cardlist/")[-1] if "cardlist/" in img_src else ""

            cards.append({
                "card_number": code,
                "name": _txt(li.select_one("p.ttl")),
                "type": type_text,
                "cost": _stat(li.select_one("span.status-Item-Cost")),
                "atk": _stat(li.select_one("span.status-Item-Power")),
                "def": _stat(li.select_one("span.status-Item-Hp")),
                "set_code": code.split("-")[0] if "-" in code else "",
                "img": img_rel,
                "text": _effect_text(li.select_one("div.detail")),
                "flavor": _effect_text(li.select_one("div.speech")),
            })
    return cards


def parse_max_page(html):
    """Extract the max page count from the inline JS variable ``var max_page = N;``."""
    m = re.search(r"max_page\s*=\s*(\d+)", html)
    return int(m.group(1)) if m else 1


def _normalize_paginated_html(html):
    """Wrap bare ``li.ex-item`` elements (returned by the paginated endpoint) in a
    ``ul.cardlist-Result_List`` so that ``parse_cardlist`` can parse them normally.
    If the page already contains the expected ``ul``, it is returned unchanged."""
    soup = BeautifulSoup(html, "lxml")
    if soup.select("ul.cardlist-Result_List"):
        return html  # page 1 — already in the right format
    items = soup.select("li.ex-item")
    if not items:
        return html  # nothing to wrap
    return '<ul class="cardlist-Result_List">' + "".join(str(li) for li in items) + "</ul>"


def _fetch_page(set_code, page):
    time.sleep(REQUEST_DELAY)
    if page == 1:
        url = CARDLIST_URL.format(set=set_code)
    else:
        url = CARDLIST_PAGE_URL.format(set=set_code, page=page)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.text


def refresh_set(conn, set_code, fetcher=_fetch_page):
    # Page 1: also determines how many pages exist
    page1_html = fetcher(set_code, 1)
    max_page = parse_max_page(page1_html)
    all_cards = parse_cardlist(_normalize_paginated_html(page1_html))

    for page in range(2, max_page + 1):
        page_html = fetcher(set_code, page)
        all_cards.extend(parse_cardlist(_normalize_paginated_html(page_html)))

    for c in all_cards:
        conn.execute(
            "INSERT OR REPLACE INTO cards"
            "(card_number, name, class, type, cost, atk, def, set_code, rarity, img,"
            " text, flavor) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                c["card_number"],
                c["name"],
                c.get("class", ""),
                c["type"],
                c["cost"],
                c["atk"],
                c["def"],
                c["set_code"],
                c.get("rarity", ""),
                c.get("img", ""),
                c.get("text", ""),
                c.get("flavor", ""),
            ),
        )
    conn.commit()


def get(conn, card_number):
    row = conn.execute(
        "SELECT * FROM cards WHERE card_number=?", (card_number,)
    ).fetchone()
    return dict(row) if row else None


def by_set(conn):
    out = {}
    for r in conn.execute(
        "SELECT * FROM cards ORDER BY set_code, card_number"
    ):
        out.setdefault(r["set_code"], []).append(dict(r))
    return out
