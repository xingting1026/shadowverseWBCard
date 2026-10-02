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


def test_effect_text_converts_icons_and_br():
    html = ('<ul class="cardlist-Result_List"><li><p class="number">BP21-003</p>'
            '<p class="ttl">無謬の偶像・ライル</p>'
            '<div class="detail"><p>【進化時】カードを1枚引く。<br>'
            'それは<img alt="攻撃力" src="x.png">+4/<img alt="体力" src="y.png">+4する。</p></div>'
            '<div class="speech">こんなところで。<br>……僕は。</div></li></ul>')
    c = cardmaster.parse_cardlist(html)[0]
    assert c["text"] == "【進化時】カードを1枚引く。\nそれは[攻撃力]+4/[体力]+4する。"
    assert c["flavor"] == "こんなところで。\n……僕は。"


def test_effect_text_empty_when_no_detail():
    html = ('<ul class="cardlist-Result_List"><li><p class="number">BP21-999</p>'
            '<p class="ttl">テスト</p></li></ul>')
    c = cardmaster.parse_cardlist(html)[0]
    assert c["text"] == "" and c["flavor"] == ""


# ---- 関連カード ----
_REL_HTML = (
    '<div class="cardlist-Detail_Relation"><div class="center-Txtarea">'
    '<h2 class="txtarea-Ttl Serif ja bold">関連カード</h2></div>'
    '<ul class="cardlist-Result_List cardlist-Result_List_Gallery">'
    '<li><a href="/cardlist/?cardno=BP19-020"><img src="x.png" alt="出航の咎人・バルバロス"></a></li>'
    '<li><a href="/cardlist/?cardno=BP19-T01"><img src="y.png" alt="戦慄の海賊旗"></a></li>'
    '<li><a href="/cardlist/?cardno=BP19-020"><img src="x.png" alt="重複"></a></li>'
    '</ul></div>'
    '<div class="cardlist-Detail_Products"><a href="/cardlist/cardsearch?expansion=BP19">カードリスト</a></div>'
)


def test_parse_relations_reads_official_block_in_order():
    assert cardmaster.parse_relations(_REL_HTML) == ["BP19-020", "BP19-T01"]


def test_parse_relations_without_block_is_empty():
    assert cardmaster.parse_relations("<html><body><p>nothing</p></body></html>") == []


def test_refresh_relations_only_fetches_unfetched_and_respects_limit(conn):
    for cn in ("BP19-019", "BP19-020", "BP19-T01"):
        conn.execute("INSERT INTO cards(card_number, name, set_code) VALUES(?,?,?)", (cn, cn, "BP19"))
    calls = []

    def fake(cn):
        calls.append(cn)
        return _REL_HTML if cn == "BP19-019" else "<html></html>"

    assert cardmaster.refresh_relations(conn, limit=2, fetcher=fake) == 2
    assert calls == ["BP19-019", "BP19-020"]
    assert cardmaster.relations_of(conn, "BP19-019") == ["BP19-020", "BP19-T01"]
    assert cardmaster.relations_of(conn, "BP19-020") == []
    # 第二次只補剩下那張；抓過的（含 0 筆的）不重抓
    calls.clear()
    assert cardmaster.refresh_relations(conn, fetcher=fake) == 1
    assert calls == ["BP19-T01"]
    assert cardmaster.refresh_relations(conn, fetcher=fake) == 0
