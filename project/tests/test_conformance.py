"""Kiểm thử công cụ chấm độ phù hợp provider (ADR 0017 D7)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))

import provider_conformance  # noqa: E402
from src.agent.conformance import check_against_baseline, score_outputs  # noqa: E402

PARA = "Đoạn văn đủ dài để làm chứng cứ trích dẫn trong bài."
IM = "Hàm ý thị trường đủ dài để vượt qua ngưỡng bốn mươi ký tự."


def rec(i, sn="pos", ts="today", tic=("HPG",)):
    return {"i": i, "e": [[t, "TIC"] for t in tic], "s": "Tóm tắt.", "k": ["một ý", "hai ý"],
            "im": IM, "sn": sn, "ts": ts, "c": [0, 1]}


def setup(tmp_path, records):
    packet = {"d": "x", "n": 2, "a": [{"i": i, "t": f"Bài {i}", "p": [PARA, PARA + " 2"]}
                                      for i in range(2)]}
    (tmp_path / "b1.task.json").write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "b1.map.json").write_text(json.dumps({"index": {"0": "A", "1": "B"}}), encoding="utf-8")
    (tmp_path / "b1.output.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    gold = {"A": {"sn": "pos", "ts": "today", "tic": ["HPG"]},
            "B": {"sn": "neg", "ts": "week", "tic": ["VND"]}}
    return gold


def test_cham_khop_hoan_toan(tmp_path):
    gold = setup(tmp_path, [rec(0), rec(1, "neg", "week", ("VND",))])
    s = score_outputs(tmp_path, tmp_path, gold, ["b1"])
    assert s["reject_rate"] == 0 and s["missing_ids"] == 0
    assert s["agree_sn"] == s["agree_ts"] == s["tic_f1"] == 1.0


def test_thieu_id_va_ban_ghi_sai_duoc_dem(tmp_path):
    gold = setup(tmp_path, [rec(0, sn="positive")])
    s = score_outputs(tmp_path, tmp_path, gold, ["b1"])
    assert s["records_rejected"] == 1 and s["missing_ids"] == 2
    assert s["agree_sn"] == 0.0


def test_so_voi_muc_agy(tmp_path):
    base = {"records_rejected": 0, "missing_ids": 0, "agree_sn": 0.8, "agree_ts": 0.7, "tic_f1": 0.9}
    ok = {**base, "agree_sn": 0.76}
    low = {**base, "agree_ts": 0.6, "missing_ids": 1}
    assert check_against_baseline(ok, base) == []
    reasons = check_against_baseline(low, base)
    assert any("thiếu" in r for r in reasons) and any("agree_ts" in r for r in reasons)


def test_cli_baseline_roi_check(tmp_path):
    gold = setup(tmp_path, [rec(0), rec(1, "neg", "week", ("VND",))])
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps({"articles": [{"article_id": k, **v} for k, v in gold.items()]}),
                         encoding="utf-8")
    common = ["--gold", str(gold_path), "--batches", "b1", "--output-dir", str(tmp_path),
              "--task-dir", str(tmp_path), "--baseline", str(tmp_path / "base.json")]
    assert provider_conformance.main(["check", *common]) == 2
    assert provider_conformance.main(["baseline", *common]) == 0
    assert provider_conformance.main(["check", *common]) == 0
