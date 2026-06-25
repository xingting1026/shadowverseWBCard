# tests/test_db.py
def test_init_db_creates_tables(conn):
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"cards", "owned", "prices", "decks", "events"} <= names
