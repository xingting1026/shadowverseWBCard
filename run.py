"""本機預覽：先產站（不抓卡圖，快），再用內建 http.server 開在 http://localhost:5000。"""
import functools
import http.server
from sve_meta import db, sitebuild
from sve_meta.config import DB_PATH, IMG_CACHE_DIR, ROOT

if __name__ == "__main__":
    conn = db.get_conn(DB_PATH)
    db.init_db(conn)
    site = ROOT / "site"
    sitebuild.export_site(conn, site, IMG_CACHE_DIR, fetch_images=False)
    conn.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(site))
    print("預覽：http://localhost:5000 （Ctrl+C 結束）")
    http.server.ThreadingHTTPServer(("127.0.0.1", 5000), handler).serve_forever()
