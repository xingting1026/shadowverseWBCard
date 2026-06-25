# tests/test_cardmaster.py
from pathlib import Path
from sve_meta import cardmaster

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_cardlist_extracts_cards():
    html = open(FIXTURES / "cardlist_bp17.html", encoding="utf-8", errors="replace").read()
    cards = cardmaster.parse_cardlist(html)
    assert len(cards) >= 1
    c = cards[0]
    # Verified from real fixture: BP17-001 is 深緑の弓使い・アリサ
    assert c["card_number"] == "BP17-001"
    assert c["name"] == "深緑の弓使い・アリサ"
    assert c["card_number"].startswith("BP17-")
    assert c["name"]
    assert set(["card_number", "name", "type", "cost", "atk", "def"]) <= set(c)
    # Stat values
    assert c["cost"] == "1"
    assert c["atk"] == "2"
    assert c["def"] == "2"
    assert c["type"] == "フォロワー"
    assert c["set_code"] == "BP17"


def test_parse_cardlist_returns_all_cards():
    html = open(FIXTURES / "cardlist_bp17.html", encoding="utf-8", errors="replace").read()
    cards = cardmaster.parse_cardlist(html)
    # Page has 15 cards in the fixture
    assert len(cards) == 15
    codes = [c["card_number"] for c in cards]
    assert "BP17-001" in codes


def test_refresh_set_stores_cards(conn):
    def fake_fetch(set_code, page):
        # Matches the real DOM structure verified from fixture.
        # Include max_page = 1 so refresh_set stops after page 1.
        return (
            '<script>var max_page = 1;</script>'
            '<ul class="cardlist-Result_List"><li>'
            '<div class="center-Txtarea txt">'
            '<p class="number">BP17-001</p>'
            '<p class="ttl">テスト</p>'
            '<div class="status">'
            '<span class="status-Item">フォロワー</span>'
            '<span class="status-Item status-Item-Cost">'
            '<span class="heading heading-Cost">コスト</span>2</span>'
            '<span class="status-Item status-Item-Power">'
            '<span class="heading heading-Power">攻撃力</span>2</span>'
            '<span class="status-Item status-Item-Hp">'
            '<span class="heading heading-Hp">体力</span>2</span>'
            '</div></div></li></ul>'
        )

    cardmaster.refresh_set(conn, "BP17", fetcher=fake_fetch)
    c = cardmaster.get(conn, "BP17-001")
    assert c is not None
    assert c["name"] == "テスト"
    assert c["set_code"] == "BP17"
    assert c["type"] == "フォロワー"
    assert c["cost"] == "2"
    assert c["atk"] == "2"
    assert c["def"] == "2"
    assert "BP17" in cardmaster.by_set(conn)


def test_get_missing_returns_none(conn):
    assert cardmaster.get(conn, "BP17-999") is None


def test_by_set_groups_correctly(conn):
    def fake_fetch(set_code, page):
        return (
            '<script>var max_page = 1;</script>'
            '<ul class="cardlist-Result_List">'
            '<li><div class="center-Txtarea txt">'
            '<p class="number">BP17-001</p><p class="ttl">カードA</p>'
            '<div class="status">'
            '<span class="status-Item">フォロワー</span>'
            '<span class="status-Item status-Item-Cost"><span class="heading heading-Cost">コスト</span>1</span>'
            '<span class="status-Item status-Item-Power"><span class="heading heading-Power">攻撃力</span>1</span>'
            '<span class="status-Item status-Item-Hp"><span class="heading heading-Hp">体力</span>1</span>'
            '</div></div></li>'
            '<li><div class="center-Txtarea txt">'
            '<p class="number">BP17-002</p><p class="ttl">カードB</p>'
            '<div class="status">'
            '<span class="status-Item">スペル</span>'
            '<span class="status-Item status-Item-Cost"><span class="heading heading-Cost">コスト</span>3</span>'
            '<span class="status-Item status-Item-Power"><span class="heading heading-Power">攻撃力</span>-</span>'
            '<span class="status-Item status-Item-Hp"><span class="heading heading-Hp">体力</span>-</span>'
            '</div></div></li>'
            '</ul>'
        )

    cardmaster.refresh_set(conn, "BP17", fetcher=fake_fetch)
    result = cardmaster.by_set(conn)
    assert "BP17" in result
    assert len(result["BP17"]) == 2


def test_refresh_set_paginates_all_pages(conn):
    pages = {
        1: (
            '<script>var max_page = 2;</script>'
            '<ul class="cardlist-Result_List"><li>'
            '<div class="center-Txtarea txt">'
            '<p class="number">BP17-001</p><p class="ttl">一頁卡</p>'
            '<div class="status">'
            '<span class="status-Item">フォロワー</span>'
            '<span class="status-Item status-Item-Cost"><span class="heading heading-Cost">コスト</span>1</span>'
            '<span class="status-Item status-Item-Power"><span class="heading heading-Power">攻撃力</span>1</span>'
            '<span class="status-Item status-Item-Hp"><span class="heading heading-Hp">体力</span>1</span>'
            '</div></div></li></ul>'
        ),
        2: (
            '<ul class="cardlist-Result_List"><li>'
            '<div class="center-Txtarea txt">'
            '<p class="number">BP17-016</p><p class="ttl">二頁卡</p>'
            '<div class="status">'
            '<span class="status-Item">フォロワー</span>'
            '<span class="status-Item status-Item-Cost"><span class="heading heading-Cost">コスト</span>2</span>'
            '<span class="status-Item status-Item-Power"><span class="heading heading-Power">攻撃力</span>2</span>'
            '<span class="status-Item status-Item-Hp"><span class="heading heading-Hp">体力</span>2</span>'
            '</div></div></li></ul>'
        ),
    }

    def fake_fetch(set_code, page):
        return pages[page]

    cardmaster.refresh_set(conn, "BP17", fetcher=fake_fetch)
    assert cardmaster.get(conn, "BP17-001")["name"] == "一頁卡"
    assert cardmaster.get(conn, "BP17-016")["name"] == "二頁卡"   # page 2 も抓到了
