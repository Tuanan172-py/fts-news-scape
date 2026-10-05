"""
Tests change-detection (phase-02): SimHash/hamming, dom_path_sig, classify 5 states.
"""

from src.pipeline.change_detect import (
    classify,
    dom_path_sig,
    fingerprint,
    hamming64,
    simhash64,
)


def _fp(text, structure, sha, status="ok", missing=None):
    return fingerprint(text, structure, content_sha256=sha,
                       capture_status=status, missing=missing or [])


def test_simhash_identical_zero_distance():
    a = simhash64("thị trường chứng khoán tăng điểm mạnh phiên sáng")
    b = simhash64("thị trường chứng khoán tăng điểm mạnh phiên sáng")
    assert a == b and hamming64(a, b) == 0


def test_simhash_similar_small_distance():
    a = simhash64("VN-Index tăng điểm nhờ nhóm ngân hàng và công nghệ dẫn dắt thị trường")
    b = simhash64("VN-Index tăng điểm nhờ nhóm ngân hàng và công nghệ dẫn dắt thị trường hôm nay")
    assert 0 < hamming64(a, b) <= 12  # gần nhau


def test_dom_sig_stable_and_sensitive():
    s1 = {"headings": [{"level": 1, "text": "a"}], "paragraphs": ["x"] * 5, "tables": [], "links": []}
    s2 = {"headings": [{"level": 1, "text": "a"}], "paragraphs": ["x"] * 5, "tables": [], "links": []}
    s3 = {"headings": [{"level": 1}, {"level": 2}], "paragraphs": ["x"] * 50, "tables": [[["c"]]], "links": []}
    assert dom_path_sig(s1) == dom_path_sig(s2)      # ổn định
    assert dom_path_sig(s1) != dom_path_sig(s3)      # nhạy template khác


STRUCT = {"headings": [{"level": 1, "text": "t"}], "paragraphs": ["p"] * 10, "tables": [], "links": []}


def test_classify_new():
    cur = _fp("nội dung", STRUCT, "sha1")
    assert classify(None, cur)[0] == "NEW"


def test_classify_unchanged():
    cur = _fp("nội dung", STRUCT, "shaX")
    prev = {"content_sha256": "shaX", "simhash64": cur["simhash64"],
            "dom_path_sig": cur["dom_path_sig"], "selector_ok": True}
    assert classify(prev, cur)[0] == "UNCHANGED"


def test_classify_content_changed():
    cur = _fp("nội dung bài viết đã được cập nhật thêm một câu", STRUCT, "shaNEW")
    prev = {"content_sha256": "shaOLD",
            "simhash64": format(simhash64("nội dung bài viết đã được cập nhật"), "016x"),
            "dom_path_sig": cur["dom_path_sig"], "selector_ok": True}
    state, rec = classify(prev, cur)
    assert state == "CONTENT_CHANGED" and rec == "re_extract"


def test_classify_template_drift():
    cur = _fp("nội dung", STRUCT, "shaNEW")
    prev = {"content_sha256": "shaOLD", "simhash64": cur["simhash64"],
            "dom_path_sig": "different_sig", "selector_ok": True}
    assert classify(prev, cur)[0] == "TEMPLATE_DRIFT"


def test_classify_selector_broken_precedence():
    cur = _fp("x", STRUCT, "sha", status="partial", missing=["main_content_node"])
    prev = {"content_sha256": "sha", "simhash64": cur["simhash64"],
            "dom_path_sig": cur["dom_path_sig"], "selector_ok": True}
    # dù sha bằng nhau, selector hỏng vẫn ưu tiên
    assert classify(prev, cur)[0] == "SELECTOR_BROKEN"
