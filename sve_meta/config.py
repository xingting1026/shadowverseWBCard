# sve_meta/config.py
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "sve_meta.db"
IMG_CACHE_DIR = ROOT / "img_cache"

GAME_TITLE_ID_SVE = 6
REQUEST_DELAY = 1.0    # 秒，爬蟲（Bushi-Navi/DeckLog/yuyu-tei/卡表）對外請求間隔
IMG_FETCH_DELAY = 0.0  # 卡圖代理不套禮貌延遲：抓一次就永久快取，且頁面一次載很多張
PRICE_TTL_SECONDS = 24 * 3600

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

BUSHINAVI_API = "https://api-user.bushi-navi.com"
BUSHINAVI_HEADERS = {"X-Accept-Version": "v1", "User-Agent": USER_AGENT}

DECKLOG_VIEW_API = "https://decklog.bushiroad.com/system/app/api/view/{code}"
DECKLOG_REFERER = "https://decklog.bushiroad.com/view/{code}"
DECKLOG_IMG_BASE = "https://shadowverse-evolve.com/wordpress/wp-content/images/cardlist/"
DECKLOG_IMG_REFERER = "https://decklog.bushiroad.com/"

YUYUTEI_SET_URL = "https://yuyu-tei.jp/sell/sev/s/{set}"
CARDLIST_URL = "https://shadowverse-evolve.com/cardlist/cardsearch/?expansion={set}&view=text"
CARDLIST_PAGE_URL = "https://shadowverse-evolve.com/cardlist/cardsearch_ex?expansion={set}&view=text&page={page}"
