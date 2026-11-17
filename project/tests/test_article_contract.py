"""Kiểm thử hợp đồng đầu ra article-processor và chống lệch giữa prompt, bộ kiểm, bộ bung."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))

from src.agent import article_contract as ac  # noqa: E402
import article_expand  # noqa: E402
import build_article_prefix  # noqa: E402

LONG = "Đoạn văn đủ dài để làm chứng cứ trích dẫn trong bài."
PACKET = {"d": "2026-10-05", "n": 2, "a": [
    {"i": 0, "t": "Tiêu đề 0", "p": [LONG, LONG + " Hai.", LONG + " Ba.", "Ngắn"]},
    {"i": 1, "t": "Tiêu đề 1", "p": [LONG, LONG + " Hai."]},
]}


def rec(**over):
    base = {"i": 0, "e": [["Hòa Phát", "COM"], ["HPG", "TIC"]], "s": "Tóm tắt một câu.",
            "k": ["Luận điểm một", "Luận điểm hai"],
            "im": "Hàm ý thị trường đủ dài để vượt qua ngưỡng bốn mươi ký tự.",
            "sn": "pos", "ts": "today", "c": [0, 1]}
    base.update(over)
    return base


def run(*records):
    return ac.parse_and_validate(json.dumps(list(records), ensure_ascii=False), PACKET)


def test_ban_ghi_hop_le_duoc_nhan_va_chuan_hoa():
    out = run(rec(c=[2, 0], e=[["HPG", "TIC"], ["Hòa Phát", "COM"], ["hpg", "TIC"]]))
    assert out.errors == {}
    r = out.records[0]
    assert r["c"] == [0, 2]
    assert r["e"] == [["HPG", "TIC"], ["Hòa Phát", "COM"]]
    assert out.counters["dedup_entity"] == 1


def test_enum_sai_bi_tu_choi_khong_gan_mac_dinh():
    out = run(rec(sn="positive"), rec(i=1, ts="year", c=[0, 1]))
    assert out.records == {}
    assert out.errors[0][0].startswith("enum:sn")
    assert out.errors[1][0].startswith("enum:ts")


def test_k_phai_tu_hai_den_bon_muc_va_la_mang():
    out = run(rec(k=["một"]), rec(i=1, k=list("abcde"), c=[0, 1]))
    assert out.errors[0] == ["count:k:1"] and out.errors[1] == ["count:k:5"]
    assert run(rec(k="một chuỗi")).errors[0] == ["type:k"]


def test_c_ngoai_pham_vi_hoac_doan_ngan_bi_tu_choi_khong_tu_bu():
    assert run(rec(c=[0, 9])).errors[0] == ["range:c:9"]
    assert run(rec(c=[0, 3])).errors[0] == ["range:c:3"]
    assert run(rec(c=[1])).errors[0] == ["count:c:1"]
    assert run(rec(c=[0, 1, 2, 0, 1][:3] + [1, 2])).records[0]["c"] == [0, 1, 2]


def test_c_toi_da_bon_chi_so_va_phai_la_so_nguyen():
    packet = {"a": [{"i": 0, "t": "t", "p": [LONG + str(n) for n in range(6)]}]}
    # Thừa chỉ số hợp lệ: giữ 4 lựa chọn đầu của mô hình, không từ chối cả bài.
    out = ac.parse_and_validate(json.dumps([rec(c=[4, 0, 1, 2, 3])]), packet)
    assert out.records[0]["c"] == [0, 1, 2, 4]
    assert out.counters["trim_c"] == 1
    out = ac.parse_and_validate(json.dumps([rec(c=[0, 1, 2, 3, 9])]), packet)
    assert out.errors[0] == ["range:c:9"]       # chỉ số sai vẫn bị từ chối
    assert run(rec(c=["0", "1"])).errors[0] == ["type:c"]
    assert run(rec(c=[True, 1])).errors[0] == ["type:c"]


def test_khoa_la_va_khoa_thieu_bi_tu_choi():
    assert run(rec(t="x")).errors[0] == ["unknown_key:t"]
    bad = rec()
    del bad["im"]
    assert run(bad).errors[0] == ["missing:im"]


def test_thuc_the_sai_nhom_hoac_sai_dang_bi_tu_choi():
    assert run(rec(e=[["Quỹ", "ETF"]])).errors[0][0].startswith("enum:e.group")
    assert run(rec(e=[["a", "TIC", "x"]])).errors[0] == ["shape:e"]
    assert run(rec(e=[])).records[0]["e"] == []


def test_im_ngan_bi_tu_choi():
    assert run(rec(im="Ngắn.")).errors[0] == ["short:im"]


def test_id_lap_bi_loai_ca_hai_va_id_la_duoc_dem():
    out = run(rec(), rec(), rec(i=7))
    assert out.errors == {0: ["dup_i"]} and out.records == {}
    assert out.counters["unknown_i"] == 1


def test_bai_chi_co_mot_doan_dai_duoc_ha_so_chi_so_toi_thieu():
    packet = {"a": [{"i": 0, "t": "t", "p": [LONG, "ngắn"]}]}
    out = ac.parse_and_validate(json.dumps([rec(c=[0])]), packet)
    assert out.errors == {} and out.records[0]["c"] == [0]


def test_vo_truyen_tai_duoc_dem():
    body = json.dumps([rec()], ensure_ascii=False)
    out = ac.parse_and_validate("Kết quả:\n```json\n" + body + "\n```", PACKET)
    assert out.records and out.counters["prose_prefix"] == 1
    fenced = ac.parse_and_validate("```json\n" + body + "\n```", PACKET)
    assert fenced.records and fenced.counters["fence"] == 1
    env = json.dumps({"output": [{"type": "text", "text": body}]})
    assert ac.parse_and_validate(env, PACKET).counters["envelope"] == 1


def test_output_cut_cut_van_cuu_duoc_ban_ghi_dau():
    body = json.dumps([rec(), rec(i=1)], ensure_ascii=False)
    out = ac.parse_and_validate(body[: body.rindex("{") + 20], PACKET)
    assert 0 in out.records and 1 not in out.records and out.counters["broken"] == 1


def test_schema_la_nguon_cua_hang_so():
    assert set(ac.REQUIRED_KEYS) == {"i", "e", "s", "k", "im", "sn", "ts", "c"}
    assert set(ac.SENTIMENT_MAP) == set(ac.SENTIMENT_CODES)
    assert set(ac.TIME_MAP) == set(ac.TIME_CODES)
    assert (ac.K_MIN, ac.K_MAX, ac.C_MIN, ac.C_MAX, ac.IM_MIN_CHARS) == (2, 4, 2, 4, 40)


def test_prefix_khop_hop_dong():
    codes = tuple(c for c, _, _ in build_article_prefix.GROUP_CODES)
    assert codes == ac.GROUP_CODES
    text = build_article_prefix.build([])
    for code in ac.SENTIMENT_CODES + ac.TIME_CODES:
        assert code in text
    assert "|".join(ac.SENTIMENT_CODES) in text and "|".join(ac.TIME_CODES) in text
    for code in ac.EVENT_KIND_CODES:
        assert f"`{code}`" in text
    assert article_expand.SENTIMENT_MAP is ac.SENTIMENT_MAP


def test_expander_khong_con_mac_dinh_ngu_nghia():
    out, reason = article_expand.build_gold_output("a", {**rec(), "sn": "x"}, PACKET["a"][0]["p"])
    assert out is None and "sn" in reason


def test_mat_dau_tieng_viet_bi_tu_choi():
    out = run(rec(s="Tom tat khong co dau", im="Ham y thi truong khong co dau nhung du dai de qua nguong"))
    assert out.errors[0] == ["lost_diacritics"]


def test_analyze_tu_choi_runner_khong_ho_tro(tmp_path, monkeypatch):
    import argparse

    import article_run

    monkeypatch.setattr(article_run, "TASK_DIR", tmp_path)
    (tmp_path / "wave_W.json").write_text("{}", encoding="utf-8")
    args = argparse.Namespace(wave="W", runner="dsh", concurrency=0)
    assert article_run.cmd_analyze(args) == 2


def _packet_with_title(title: str) -> dict:
    para = "Đoạn văn đủ dài để làm chứng cứ trích dẫn trong bài viết này."
    return {"d": "2026-10-05", "n": 1, "a": [{"i": 0, "t": title, "p": [para, para + " Hai."]}]}


def test_tom_tat_lech_tieu_de_bi_tu_choi_de_vao_vong_va():
    """Tóm tắt của bài khác ghép nhầm vào tiêu đề: không từ có nghĩa nào trùng thì bị từ chối."""
    packet = _packet_with_title("Đắk Lắk kiểm soát giá vật liệu xây dựng")
    wrong = rec(e=[["Trung Đông", "GEO"]], s="Giá dầu thô Brent tăng do căng thẳng Trung Đông.",
                k=["Dầu Brent vượt 90 USD", "OPEC giữ nguyên sản lượng"],
                im="Giá năng lượng tăng gây áp lực lạm phát toàn cầu trong quý tới.")
    out = ac.parse_and_validate(json.dumps([wrong], ensure_ascii=False), packet)
    assert out.errors[0] == ["summary_title_mismatch"] and 0 not in out.records


def test_tom_tat_khop_tieu_de_duoc_nhan():
    """Chỉ cần một từ có nghĩa của tiêu đề xuất hiện trong chứng cứ là qua cổng."""
    packet = _packet_with_title("Đắk Lắk kiểm soát giá vật liệu xây dựng")
    ok = rec(e=[["Đắk Lắk", "GEO"]], s="Tỉnh yêu cầu kiểm soát giá vật liệu trước mùa xây dựng cao điểm.")
    out = ac.parse_and_validate(json.dumps([ok], ensure_ascii=False), packet)
    assert 0 in out.records and not out.errors


def test_tieu_de_qua_ngan_khong_bi_chan_nham():
    """Tiêu đề dưới ba từ có nghĩa không đủ căn cứ để kết luận lệch."""
    assert ac.title_summary_misaligned("Tin nhanh", ["Nội dung hoàn toàn khác"]) is False


def test_ek_la_khoa_tuy_chon_va_giu_nguyen_khi_hop_le():
    """ADR 0032: thiếu `ek` vẫn hợp lệ, `ek` trong enum được giữ, ngoài enum bị từ chối."""
    assert ac.EVENT_KIND_CODES == (
        "MACRO_POLICY", "EARNINGS_FINANCE", "CORP_ACTION_MA", "LEGAL_RISK",
        "MARKET_MICROSTRUCTURE", "PR_BRANDING")
    assert "ek" not in ac.REQUIRED_KEYS and "ek" in ac.OPTIONAL_KEYS
    ok = run(rec(ek="PR_BRANDING"), rec(i=1))
    assert ok.errors == {}
    assert ok.records[0]["ek"] == "PR_BRANDING" and "ek" not in ok.records[1]
    bad = run(rec(ek="NEWS"))
    assert bad.errors[0] == ["enum:ek:'NEWS'"] and 0 not in bad.records


def test_gold_output_mang_event_kind_chi_khi_hop_le():
    paras = PACKET["a"][0]["p"]
    row, _ = article_expand.build_gold_output("a", {**rec(), "ek": "LEGAL_RISK"}, paras)
    assert row["event_kind"] == "LEGAL_RISK"
    row, _ = article_expand.build_gold_output("a", rec(), paras)
    assert "event_kind" not in row


def test_gate_ghep_event_kind_vao_categories_khong_mat_the_cu():
    from src.research_db.gate import _with_event_kind
    assert _with_event_kind("kinh-doanh,tai-chinh", "MACRO_POLICY") == "kinh-doanh,tai-chinh,ek:MACRO_POLICY"
    assert _with_event_kind("kinh-doanh,ek:PR_BRANDING", "LEGAL_RISK") == "kinh-doanh,ek:LEGAL_RISK"
    assert _with_event_kind("kinh-doanh", None) == "kinh-doanh"
    assert _with_event_kind(None, "NOT_A_KIND") == ""



def test_sync_preset_ghi_persona_khop_prefix_va_giu_cac_row_khac(tmp_path):
    from src.agent.prefix import compare_persona

    preset = tmp_path / "agent.cordis.yml"
    lines = [
        "- id: other", "  config:", "    persona: keep",
        "- id: tool-subagent-article", "  config:", "    toolName: agent_article",
        "    persona: |", "      cũ dòng một", "", "      cũ dòng hai",
        "    agentOptions:", "      model: x", "- id: tail", "",
    ]
    preset.write_text("\n".join(lines), encoding="utf-8")
    content = "# Tiêu đề\n\nDòng một\nDòng hai\n"
    assert build_article_prefix.sync_preset(content, preset)
    assert compare_persona(content, preset)[0]
    text = preset.read_text(encoding="utf-8")
    assert "    persona: keep\n" in text
    assert "    agentOptions:\n      model: x\n- id: tail" in text
