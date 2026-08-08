"""合併/驗證 AI 翻譯批次 → translations/effects.zh.json（可重跑、可增量）。

用法：
  python merge_zh.py <批次資料夾>     # 讀 zh_*.json，驗證後合併進 translations/effects.zh.json

驗證（不合格的條目列出並跳過→保留日文 fallback，不會整批失敗）：
1. key 必須存在於日文母本（site/data/effects.ja.json），結構 B/E 對得上。
2. 圖示 token（半形 [——]）數量需與日文一致；但「關鍵字圖示」
   （[ファンファーレ]／[ラストワード]／[起動]）允許被轉成全形中文關鍵字。
3. 中文長度需 ≥ 日文的 45%（攔截「基於截斷日文」翻出來的殘篇）。

正規化（套用在通過驗證的條目上，保證全站術語一致）：
- 殘留的 [ファンファーレ] 等關鍵字圖示 → 【入場曲】等全形中文。
- 各批次不一致的機制詞統一（吸血/光環/堆疊/連擊/死靈充能/法術連鎖…）。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "translations" / "effects.zh.json"
JA = ROOT / "site" / "data" / "effects.ja.json"

TOKEN = re.compile(r"\[[^\[\]]+\]")
# 關鍵字圖示：翻譯時可（也應該）轉成全形中文關鍵字
KEYWORD_ZH = {"ファンファーレ": "【入場曲】", "ラストワード": "【謝幕曲】", "起動": "【起動】"}
KEYWORD_TOKENS = {f"[{k}]" for k in KEYWORD_ZH}
MIN_LEN_RATIO = 0.45

# 【】內機制詞的統一譯法（variant → canonical；含日文殘留與各批次歧異）
TERM_CANON = {
    "ドレイン": "吸血", "汲取": "吸血",
    "オーラ": "光環", "光暈": "光環", "靈氣": "光環",
    "スタック": "堆疊", "疊層": "堆疊", "疊加": "堆疊",
    "コンボ": "連擊",
    "ネクロチャージ": "死靈充能",
    "レッスン": "課程",
    "スペルチェイン": "法術連鎖", "法術鏈": "法術連鎖",
    "ツインドライブ": "雙重驅動", "雙重攻擊": "雙重驅動",
    "シングルドライブ": "單次驅動", "ドライブ獲得時": "驅動獲得時",
    "土の秘術": "土之秘術", "大地秘術": "土之秘術",
    "土の印": "大地印記", "土之印": "大地印記",
    "覚醒": "覺醒",
    "潜伏": "潛伏", "威圧": "威壓",
    "指定攻撃": "指定攻擊", "攻撃時": "攻擊時", "防御時": "防禦時",
}
_TERM_RE = re.compile(
    "【(" + "|".join(map(re.escape, sorted(TERM_CANON, key=len, reverse=True))) + ")((?:_[^】]*)?)】")
_KW_RE = re.compile(r"\[(" + "|".join(map(re.escape, KEYWORD_ZH)) + r")\]")


def normalize(text):
    text = _KW_RE.sub(lambda m: KEYWORD_ZH[m.group(1)], text)
    return _TERM_RE.sub(lambda m: f"【{TERM_CANON[m.group(1)]}{m.group(2)}】", text)


def _tokens(text):
    return sorted(t for t in TOKEN.findall(text) if t not in KEYWORD_TOKENS)


def main(batch_dir):
    ja = json.loads(JA.read_text(encoding="utf-8"))
    merged = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    ok = skipped = 0
    problems = []
    for f in sorted(Path(batch_dir).glob("zh_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            problems.append(f"{f.name}: JSON 解析失敗 {e}")
            continue
        for name, forms in data.items():
            if name not in ja:
                problems.append(f"{f.name}: 未知卡名 {name}")
                skipped += 1
                continue
            for sub, pair in (forms or {}).items():
                if sub not in ja[name] or not isinstance(pair, list) or not pair or not pair[0]:
                    problems.append(f"{f.name}: {name}/{sub} 結構不對")
                    skipped += 1
                    continue
                ja_text = ja[name][sub][0]
                if _tokens(pair[0]) != _tokens(ja_text):
                    problems.append(f"{f.name}: {name}/{sub} 圖示token不一致")
                    skipped += 1
                    continue
                if len(pair[0]) < MIN_LEN_RATIO * len(ja_text):
                    problems.append(f"{f.name}: {name}/{sub} 太短(疑似翻自截斷文)")
                    skipped += 1
                    continue
                merged.setdefault(name, {})[sub] = [
                    normalize(pair[0]),
                    normalize(pair[1]) if len(pair) > 1 and pair[1] else ""]
                ok += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=0), encoding="utf-8")
    ja_forms = sum(len(v) for v in ja.values())
    got = sum(1 for nm, v in merged.items() for s in v if nm in ja and s in ja[nm])
    print(f"合併 {ok} 條、跳過 {skipped} 條 → 共 {got}/{ja_forms} 條有中文（{len(merged)} 個卡名）")
    # 全部【】詞頻，供人工檢查術語還有沒有分歧
    freq = {}
    for v in merged.values():
        for pair in v.values():
            for t in re.findall(r"【([^】_]+)(?:_[^】]*)?】", pair[0]):
                freq[t] = freq.get(t, 0) + 1
    print("【】詞頻：", dict(sorted(freq.items(), key=lambda kv: -kv[1])))
    for p in problems[:30]:
        print(" !", p)
    if len(problems) > 30:
        print(f" ... 另 {len(problems) - 30} 條")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "translation_batches")
