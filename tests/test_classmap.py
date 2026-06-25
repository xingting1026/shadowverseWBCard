from sve_meta import classmap

def test_base_class_passthrough():
    assert classmap.normalize_class("ロイヤル") == "ロイヤル"
    assert classmap.normalize_class("ウィッチ") == "ウィッチ"

def test_known_leader_maps_to_base_class():
    assert classmap.normalize_class("シンデレラガールズ") == "ニュートラル"

def test_unknown_returns_input():
    assert classmap.normalize_class("謎のリーダー") == "謎のリーダー"

def test_blank_returns_unknown_label():
    assert classmap.normalize_class("") == "不明"

def test_none_returns_unknown_label():
    assert classmap.normalize_class(None) == "不明"
