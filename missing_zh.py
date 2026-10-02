"""列出/匯出「還沒有中文翻譯」的牌效（新彈出來後補翻用）。

用法：
  python missing_zh.py                        # 只統計缺多少（母本＝網站用到的卡）
  python missing_zh.py --export dir           # 缺的切成 ja_XX.json 批次檔（交給 AI 翻，翻完 merge_zh.py 合併）
  python missing_zh.py --all --export dir     # 母本改用 DB 全卡池（新彈剛發售、尚未入賞時先翻）
  python missing_zh.py --all --set BP22 --export dir   # 只匯出某個 set 的卡
"""
import argparse
import json
import math
import sqlite3
from pathlib import Path

from merge_zh import ja_master

ROOT = Path(__file__).resolve().parent
ZH = ROOT / "translations" / "effects.zh.json"
CHUNK = 150


def _names_of_set(set_code):
    from sve_meta.config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    return {r[0] for r in conn.execute("SELECT name FROM cards WHERE set_code = ?", (set_code,))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--export", metavar="DIR", help="把缺翻的匯出成批次檔")
    p.add_argument("--all", action="store_true", help="母本改用 DB 全卡池（含未入賞的卡）")
    p.add_argument("--set", metavar="SET", help="只看某個 set（如 BP22；需搭配 --all）")
    p.add_argument("--chunk", type=int, default=CHUNK, help=f"每批幾個卡名（預設 {CHUNK}）")
    a = p.parse_args()
    ja = ja_master(a.all or bool(a.set))
    zh = json.loads(ZH.read_text(encoding="utf-8")) if ZH.exists() else {}
    if a.set:
        keep = _names_of_set(a.set)
        ja = {nm: forms for nm, forms in ja.items() if nm in keep}
    missing = {nm: {sub: pair for sub, pair in forms.items()
                    if sub not in zh.get(nm, {})}
               for nm, forms in ja.items()}
    missing = {nm: forms for nm, forms in missing.items() if forms}
    print(f"缺中文：{len(missing)} 個卡名 / 全部 {len(ja)} 個")
    if a.export and missing:
        out = Path(a.export)
        out.mkdir(parents=True, exist_ok=True)
        names = sorted(missing)
        for i in range(math.ceil(len(names) / a.chunk)):
            chunk = {nm: missing[nm] for nm in names[i * a.chunk:(i + 1) * a.chunk]}
            (out / f"ja_{i:02d}.json").write_text(
                json.dumps(chunk, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"已匯出到 {out}")


if __name__ == "__main__":
    main()
