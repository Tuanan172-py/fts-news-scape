"""Kiểm thử runner OpenCode theo hợp đồng đầu ra thống nhất v2-lean."""
from __future__ import annotations

import json
from pathlib import Path

from src.agent.runners import opencode_runner as ocr

PARAS = ["VN-Index tăng hơn 15 điểm trong phiên.", "Dòng tiền lan tỏa sang nhóm bluechip."]
GOOD = {
    "i": 0,
    "e": [["VN-Index", "IDX"]],
    "s": "Chỉ số VN-Index tăng điểm mạnh mẽ trong phiên giao dịch.",
    "k": ["Chỉ số tăng hơn 15 điểm", "Dòng tiền lan tỏa sang bluechip"],
    "im": "Dòng tiền lan tỏa sang nhóm vốn hóa lớn củng cố xu hướng tăng điểm của thị trường.",
    "sn": "pos",
    "ts": "today",
    "c": [0, 1],
}


class _MockCompletedProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _make_ndjson(text_payload: str) -> str:
    lines = [
        json.dumps({"type": "step_start", "timestamp": 123}),
        json.dumps({"type": "text", "part": {"text": text_payload}}),
        json.dumps({"type": "step_finish", "part": {"tokens": {"input": 100, "output": 50, "total": 150}}}),
    ]
    return "\n".join(lines)


def _run(tmp_path: Path, monkeypatch, reply_text: str):
    task = tmp_path / "article_W_01.task.json"
    packet_text = json.dumps(
        {"d": "2026-10-21", "n": 1, "a": [{"i": 0, "t": "Thị trường tăng", "p": PARAS}]},
        ensure_ascii=False,
    )
    task.write_text(packet_text, encoding="utf-8")
    called_cmd = []

    def fake_subprocess_run(cmd, **kwargs):
        called_cmd.extend(cmd)
        return _MockCompletedProcess(stdout=_make_ndjson(reply_text))

    monkeypatch.setattr(ocr.subprocess, "run", fake_subprocess_run)
    runner = ocr.OpencodeRunner()
    res = runner.run_batch("article_W_01", task, tmp_path / "out", force=True)
    return res, called_cmd, packet_text


def test_opencode_runner_thanh_cong_ghi_output_va_meta(tmp_path: Path, monkeypatch):
    """Kiểm tra OpencodeRunner thực thi thành công và ghi tệp output/meta hợp lệ."""
    reply_json = json.dumps([GOOD], ensure_ascii=False)
    res, called_cmd, packet_text = _run(tmp_path, monkeypatch, reply_json)

    assert res.ok is True
    assert res.status == "OK"
    assert len(res.records) == 1
    assert "run" in called_cmd
    assert "--format" in called_cmd
    assert "json" in called_cmd

    out_file = tmp_path / "out" / "article_W_01.output.json"
    meta_file = tmp_path / "out" / "article_W_01.meta.json"
    assert out_file.exists()
    assert meta_file.exists()

    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["agent_provider"] == "opencode-native"
    assert meta["contract_version"] == "article-compact-v2"
    assert meta["items_valid"] == 1
    assert meta["usage"]["total_tokens"] == 150


def test_opencode_runner_tu_choi_ban_ghi_loi_hop_dong(tmp_path: Path, monkeypatch):
    """Kiểm tra OpencodeRunner từ chối khi bản ghi vi phạm độ dài trường hàm ý."""
    bad_record = {**GOOD, "im": "Ngắn", "sn": "pos"}
    reply_json = json.dumps([bad_record], ensure_ascii=False)
    res, _, _ = _run(tmp_path, monkeypatch, reply_json)

    assert res.ok is False
    assert res.status == "FATAL"
    assert "short:im" in res.error_message


def test_opencode_runner_tai_su_dung_cache(tmp_path: Path, monkeypatch):
    """Kiểm tra cơ chế tái sử dụng kết quả cached khi force=False."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "article_W_01.output.json"
    out_file.write_text(json.dumps([GOOD]), encoding="utf-8")

    task = tmp_path / "article_W_01.task.json"
    task.write_text(json.dumps({"a": [{"i": 0}]}), encoding="utf-8")

    called = []
    def fake_subprocess_run(cmd, **kwargs):
        called.append(cmd)
        return _MockCompletedProcess(stdout="")

    monkeypatch.setattr(ocr.subprocess, "run", fake_subprocess_run)
    runner = ocr.OpencodeRunner()
    res = runner.run_batch("article_W_01", task, out_dir, force=False)

    assert res.ok is True
    assert len(called) == 0  # Không gọi subprocess vì đã có cache
