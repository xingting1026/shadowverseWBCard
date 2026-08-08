"""列出/匯出「還沒有中文翻譯」的牌效（新彈出來後補翻用）。

用法：
  python missing_zh.py                 # 只統計缺多少
  python missing_zh.py --export dir    # 缺的切成 ja_XX.json 批次檔（交給 AI 翻，翻完 merge_zh.py 合併）
"""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JA = ROOT / "site" / "data" / "effects.ja.json"
ZH = ROOT / "translations" / "effects.zh.json"
CHUNK = 150


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--export", metavar="DIR", help="把缺翻的匯出成批次檔")
    a = p.parse_args()
    ja = json.loads(JA.read_text(encoding="utf-8"))
    zh = json.loads(ZH.read_text(encoding="utf-8")) if ZH.exists() else {}
    missing = {nm: {sub: pair for sub, pair in forms.items()
                    if sub not in zh.get(nm, {})}
               for nm, forms in ja.items()}
    missing = {nm: forms for nm, forms in missing.items() if forms}
    print(f"缺中文：{len(missing)} 個卡名 / 全部 {len(ja)} 個")
    if a.export and missing:
        out = Path(a.export)
        out.mkdir(parents=True, exist_ok=True)
        names = sorted(missing)
        for i in range(math.ceil(len(names) / CHUNK)):
            chunk = {nm: missing[nm] for nm in names[i * CHUNK:(i + 1) * CHUNK]}
            (out / f"ja_{i:02d}.json").write_text(
                json.dumps(chunk, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"已匯出到 {out}")


if __name__ == "__main__":
    main()
