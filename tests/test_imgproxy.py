from sve_meta import imgproxy


def test_candidates_try_hyphen_then_underscore():
    cands = imgproxy.image_url_candidates("BP01-001")
    assert cands[0].endswith("/BP01/bp01-001.png")        # 新 set 連字號先試
    assert cands[1].endswith("/BP01/bp01_001.png")        # 舊 set 底線備援

def test_candidates_use_stored_img_when_given():
    cands = imgproxy.image_url_candidates("BP01-001", img="BP01/bp01_001.png")
    assert cands == [imgproxy.DECKLOG_IMG_BASE + "BP01/bp01_001.png"]

def test_fetch_image_sends_referer_and_caches(tmp_path):
    calls = []
    def fake_getter(url, headers):
        calls.append(headers.get("Referer"))
        return b"PNGDATA"
    p1 = imgproxy.fetch_image("BP07-007", cache_dir=tmp_path, getter=fake_getter)
    p2 = imgproxy.fetch_image("BP07-007", cache_dir=tmp_path, getter=fake_getter)
    assert p1.read_bytes() == b"PNGDATA"
    assert p2 == p1
    assert len(calls) == 1                                 # 第二次走磁碟快取
    assert calls[0] == "https://decklog.bushiroad.com/"

def test_fetch_image_falls_back_to_underscore(tmp_path):
    def fake_getter(url, headers):
        if url.endswith("bp01-001.png"):                   # 連字號版 404
            raise Exception("404")
        return b"USCORE"                                   # 底線版成功
    p = imgproxy.fetch_image("BP01-001", cache_dir=tmp_path, getter=fake_getter)
    assert p.read_bytes() == b"USCORE"

def test_fetch_image_caches_placeholder_on_total_failure(tmp_path):
    def fail_getter(url, headers):
        raise Exception("404")
    p = imgproxy.fetch_image("ZZ99-999", cache_dir=tmp_path, getter=fail_getter)
    assert p.exists()                                      # 快取佔位圖，不丟例外
    assert p.read_bytes() == imgproxy._PLACEHOLDER
