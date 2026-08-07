# sve_meta/imgproxy.py
import io
import re
import time
import requests
from pathlib import Path
from PIL import Image
from .config import (DECKLOG_IMG_BASE, DECKLOG_IMG_REFERER, USER_AGENT,
                     IMG_CACHE_DIR, IMG_FETCH_DELAY, IMG_THUMB_WIDTH)


def _make_placeholder():
    """抓不到圖時用的小灰卡（JPEG），與縮圖同為 .jpg 方便統一處理。"""
    buf = io.BytesIO()
    Image.new("RGB", (IMG_THUMB_WIDTH, round(IMG_THUMB_WIDTH * 7 / 5)),
              (24, 23, 32)).save(buf, "JPEG", quality=60)
    return buf.getvalue()


_PLACEHOLDER = _make_placeholder()


def is_placeholder(path):
    """此快取檔是否為「抓不到圖」的灰卡佔位圖（每天重試的依據）。"""
    try:
        return Path(path).read_bytes() == _PLACEHOLDER
    except OSError:
        return False


def image_url_candidates(card_number, img=None):
    """要嘗試的卡圖 URL 清單。有官方頁記錄的相對路徑 img 就只用它；
    否則自行組——檔名小寫，新舊 set 分隔符不同（新 bp07-001 / 舊 bp01_001）兩種都試。"""
    if img:
        return [DECKLOG_IMG_BASE + img.lstrip("/")]
    set_code = card_number.split("-")[0]
    stem = card_number.lower()
    folders = [set_code]
    stripped = re.sub(r"[a-z]+$", "", set_code)     # DSD01a→DSD01（圖檔資料夾去掉結尾小寫）
    if stripped and stripped != set_code:
        folders.append(stripped)
    urls = []
    for f in folders:                               # 每個資料夾都試連字號與底線檔名
        urls.append(f"{DECKLOG_IMG_BASE}{f}/{stem}.png")
        urls.append(f"{DECKLOG_IMG_BASE}{f}/{stem.replace('-', '_')}.png")
    return urls


def _http_get(url, headers):
    if IMG_FETCH_DELAY:
        time.sleep(IMG_FETCH_DELAY)
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.content


def _thumb(data):
    """把原圖縮成寬 IMG_THUMB_WIDTH 的 JPEG bytes；不是圖或縮圖失敗就原樣回傳。"""
    try:
        im = Image.open(io.BytesIO(data))
        if im.mode != "RGB":
            im = im.convert("RGB")
        w, h = im.size
        if w > IMG_THUMB_WIDTH:
            im = im.resize((IMG_THUMB_WIDTH, max(1, round(h * IMG_THUMB_WIDTH / w))),
                           Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82)
        return out.getvalue()
    except Exception:
        return data


def fetch_image(card_number, img=None, cache_dir=IMG_CACHE_DIR, getter=_http_get):
    """帶 Referer 抓官方卡圖 → 縮成 JPEG 縮圖 → 存磁碟快取。
    真圖命中就不再抓；快取的是佔位圖則重試（官方晚上圖的新卡才補得回來）。
    依序試候選 URL，全失敗就快取小灰卡佔位（不丟例外）。"""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{card_number}.jpg"
    if path.exists() and not is_placeholder(path):
        return path
    headers = {"User-Agent": USER_AGENT, "Referer": DECKLOG_IMG_REFERER}
    for url in image_url_candidates(card_number, img):
        try:
            path.write_bytes(_thumb(getter(url, headers)))
            return path
        except Exception:
            continue
    path.write_bytes(_PLACEHOLDER)
    return path
