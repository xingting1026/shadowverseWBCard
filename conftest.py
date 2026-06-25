# conftest.py（專案根）
import pytest
from sve_meta import db

@pytest.fixture
def conn():
    c = db.get_conn(":memory:")
    db.init_db(c)
    yield c
    c.close()
