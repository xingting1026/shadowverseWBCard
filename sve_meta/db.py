# sve_meta/db.py
import sqlite3
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
  card_number TEXT PRIMARY KEY, name TEXT, class TEXT, type TEXT,
  cost TEXT, atk TEXT, def TEXT, set_code TEXT, rarity TEXT, img TEXT,
  text TEXT, flavor TEXT
);
CREATE TABLE IF NOT EXISTS owned (
  card_number TEXT PRIMARY KEY, qty INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS prices (
  card_number TEXT PRIMARY KEY, jpy INTEGER, fetched_at REAL,
  source TEXT, is_manual INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS decks (
  code TEXT PRIMARY KEY, game_title_id INTEGER, class TEXT,
  list_json TEXT, evolve_json TEXT, fetched_at REAL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, title TEXT, store TEXT, pref TEXT,
  players INTEGER, start_date TEXT, rankings_json TEXT, fetched_at REAL
);
"""

def get_conn(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

_MIGRATIONS = (
    "ALTER TABLE decks ADD COLUMN evolve_json TEXT",   # 進化牌組（舊 DB 補欄位）
    "ALTER TABLE cards ADD COLUMN text TEXT",          # 日文牌效（官方 detail 區塊）
    "ALTER TABLE cards ADD COLUMN flavor TEXT",        # flavor text（官方 speech 區塊）
)

def init_db(conn):
    conn.executescript(SCHEMA)
    for stmt in _MIGRATIONS:                            # 對既有 DB 補欄位，已存在就略過
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()
