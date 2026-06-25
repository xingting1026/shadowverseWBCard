# sve_meta/imgproxy.py
import base64
import time
import requests
from pathlib import Path
from .config import (DECKLOG_IMG_BASE, DECKLOG_IMG_REFERER, USER_AGENT,
                     IMG_CACHE_DIR, REQUEST_DELAY)

# 1x1 透明 PNG。官方圖抓不到時用它佔位並快取，避免每次 render 重打 404、避免 /img 回 500。
_PLACEHOLDER = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def image_url_candidates(card_number, img=None):
    """要嘗試的卡圖 URL 清單。
    有官方頁記錄的相對路徑 img（最準）就只用它；否則自行組——檔名小寫，
    且新舊 set 的分隔符不同（新: bp07-001.png / 舊: bp01_001.png），兩種都試。"""
    if img:
        return [DECKLOG_IMG_BASE + img.lstrip("/")]
    set_code = card_number.split("-")[0]
    stem = card_number.lower()
    return [
        f"{DECKLOG_IMG_BASE}{set_code}/{stem}.png",                    # 新 set：連字號
        f"{DECKLOG_IMG_BASE}{set_code}/{stem.replace('-', '_')}.png",  # 舊 set：底線
    ]


def _http_get(url, headers):
    time.sleep(REQUEST_DELAY)
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.content


def fetch_image(card_number, img=None, cache_dir=IMG_CACHE_DIR, getter=_http_get):
    """帶 Referer 抓官方卡圖（避開防盜連 404），存磁碟快取；命中快取就不再抓。
    依序嘗試候選 URL，全部失敗就快取透明佔位圖並回傳（不丟例外）。"""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{card_number}.png"
    if path.exists():
        return path
    headers = {"User-Agent": USER_AGENT, "Referer": DECKLOG_IMG_REFERER}
    for url in image_url_candidates(card_number, img):
        try:
            path.write_bytes(getter(url, headers))
            return path
        except Exception:
            continue
    path.write_bytes(_PLACEHOLDER)   # 全部抓不到 → 透明佔位，永不再重試、永不 500
    return path
