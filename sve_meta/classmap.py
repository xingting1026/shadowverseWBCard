# Shadowverse Evolve 的七職 + 中立（ナイトメア 為 SVE 實際職業；
# 影/血在 SVE 合併為 ナイトメア，故無 ネクロマンサー／ヴァンパイア）
BASE_CLASSES = {
    "エルフ", "ロイヤル", "ウィッチ", "ドラゴン",
    "ナイトメア", "ビショップ", "ネメシス", "ニュートラル",
}

# 聯動/別名 leader → 基礎職業（seed，依實際 deck_param1 持續擴充）
LEADER_TO_CLASS = {
    "シンデレラガールズ": "ニュートラル",
    "ウマ娘": "ニュートラル",
    "プリコネ": "ニュートラル",
}


def normalize_class(deck_param1):
    s = (deck_param1 or "").strip()
    if not s:
        return "不明"
    if s in BASE_CLASSES:
        return s
    if s in LEADER_TO_CLASS:
        return LEADER_TO_CLASS[s]
    return s  # 未知：原樣回傳，方便日後補進對照表
