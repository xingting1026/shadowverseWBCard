# tests/test_prices.py
from pathlib import Path
from sve_meta import prices

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_prices_extracts_code_and_jpy():
    html = open(FIXTURES / "yuyutei_bp06.html", encoding="utf-8", errors="replace").read()
    table = prices.parse_prices(html)
    assert table["BP06-SP01"] == 9980
    assert all(isinstance(v, int) for v in table.values())
    assert len(table) >= 150


def test_refresh_and_manual_override(conn):
    def fake_fetch(set_code):
        return ('<div class="card-product"><span class="border">BP06-001</span>'
                '<strong>320 円</strong></div>')

    prices.refresh_set(conn, "bp06", fetcher=fake_fetch)
    assert prices.get_price(conn, "BP06-001") == 320

    prices.set_manual(conn, "BP06-001", 999)
    prices.refresh_set(conn, "bp06", fetcher=fake_fetch)
    assert prices.get_price(conn, "BP06-001") == 999
