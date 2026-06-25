from sve_meta import collection

def test_set_and_get_owned(conn):
    collection.set_owned(conn, "BP07-007", 2)
    assert collection.get_owned(conn) == {"BP07-007": 2}

def test_set_owned_clamps_upper_to_3(conn):
    collection.set_owned(conn, "BP07-007", 9)
    assert collection.get_owned(conn)["BP07-007"] == 3

def test_set_owned_clamps_lower_to_0_and_is_excluded(conn):
    # 負數夾成 0，而 0 不會出現在 get_owned 結果中
    collection.set_owned(conn, "BP07-010", -5)
    assert "BP07-010" not in collection.get_owned(conn)

def test_get_owned_excludes_zero(conn):
    collection.set_owned(conn, "BP07-007", 0)
    assert "BP07-007" not in collection.get_owned(conn)
