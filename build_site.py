"""把 sve_meta.db 產成純靜態網站到 site/（GitHub Pages 直接部署這個資料夾）。

用法：
  python build_site.py                 # 產站（缺的卡圖會抓，間隔 0.1 秒）
  python build_site.py --no-images     # 只產資料與頁面，不抓卡圖
  python build_site.py --out dist      # 換輸出資料夾
"""
import argparse
from sve_meta import db, sitebuild
from sve_meta.config import DB_PATH, IMG_CACHE_DIR, ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "site"), help="輸出資料夾（預設 site/）")
    p.add_argument("--no-images", action="store_true", help="不抓缺少的卡圖")
    p.add_argument("--image-delay", type=float, default=0.1,
                   help="抓卡圖的間隔秒數（預設 0.1）")
    a = p.parse_args()

    conn = db.get_conn(DB_PATH)
    db.init_db(conn)
    sitebuild.export_site(conn, a.out, IMG_CACHE_DIR,
                          fetch_images=not a.no_images,
                          image_delay=a.image_delay)


if __name__ == "__main__":
    main()
