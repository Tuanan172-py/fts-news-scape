"""Kiểm thử đơn vị cho module agy_runner điều phối Antigravity CLI."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.agent.agy_runner import (
    AgyRunner,
    build_sandbox_profile,
    has_vietnamese_diacritics,
)


@dataclass
class MockProcessResult:
    stdout: str
    stderr: str
    returncode: int


def test_has_vietnamese_diacritics():
    """Kiểm tra nhận diện chuỗi có dấu tiếng Việt."""
    assert has_vietnamese_diacritics("Ngân hàng Nhà nước") is True
    assert has_vietnamese_diacritics("Thị trường chứng khoán") is True
    assert has_vietnamese_diacritics("Ngan hang Nha nuoc") is False
    assert has_vietnamese_diacritics("ABC XYZ 123") is False


def test_build_sandbox_profile(tmp_path):
    """Kiểm tra khởi tạo Sandboxed Worker Profile cô lập."""
    profile_dir = tmp_path / "sandbox_worker"
    core_text = "# TEST CORE TEXT"

    paths = build_sandbox_profile(profile_dir, core_text)

    agent_file = paths["agent"]
    settings_file = paths["settings"]
    hooks_file = paths["hooks"]

    assert agent_file.exists()
    assert settings_file.exists()
    assert hooks_file.exists()

    agent_content = agent_file.read_text(encoding="utf-8")
    assert "name: article-processor" in agent_content
    assert "tools: []" in agent_content
    assert "excludeDefaultComponents: true" in agent_content
    assert core_text in agent_content

    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert settings["permissions"]["allow"] == []
    assert settings["trustedWorkspaces"] == []

    hooks = json.loads(hooks_file.read_text(encoding="utf-8"))
    assert len(hooks["hooks"]) == 1
    assert hooks["hooks"][0]["decision"] == "deny"


def test_agy_runner_run_batch_ok(tmp_path):
    """Kiểm tra run_batch thành công với mock subprocess."""
    task_dir = tmp_path / "tasks"
    out_dir = tmp_path / "outputs"
    task_dir.mkdir()
    out_dir.mkdir()

    batch_id = "article_TEST_01"
    task_path = task_dir / f"{batch_id}.task.json"
    task_data = {
        "d": "2026-09-25",
        "n": 1,
        "a": [
            {
                "i": 0,
                "t": "Thị trường chứng khoán tăng mạnh",
                "p": ["VN-Index tăng hơn 15 điểm trong phiên.", "Dòng tiền lan tỏa sang nhóm bluechip."],
            }
        ],
    }
    task_path.write_text(json.dumps(task_data), encoding="utf-8")

    # Giả lập phản hồi NDJSON chuẩn của agy
    mock_events = [
        {"type": "init", "data": {"model": "gemini-3.8-flash-low", "tools": []}},
        {
            "type": "result",
            "data": {
                "response": json.dumps(
                    [
                        {
                            "i": 0,
                            "e": [["VN-Index", "IDX"]],
                            "s": "Chỉ số VN-Index tăng mạnh hơn 15 điểm.",
                            "k": ["Chỉ số tăng điểm rõ rệt", "Dòng tiền lan rộng"],
                            "im": "Dòng tiền lan tỏa báo hiệu xu hướng tích cực cho thị trường.",
                            "sn": "pos", "ts": "today", "c": [0, 1],
                        }
                    ]
                ),
                "usage": {"input_tokens": 1500, "output_tokens": 200, "total_tokens": 1700},
            },
        },
    ]
    stdout_text = "\n".join(json.dumps(e) for e in mock_events) + "\n"

    def mock_sp(cmd, stdin_data, env, cwd):
        assert "article-processor" in cmd
        assert "--disable-slash-commands" in cmd
        return MockProcessResult(stdout=stdout_text, stderr="", returncode=0)

    runner = AgyRunner(profile_root=tmp_path / "profiles", work_root=tmp_path / "work")
    res = runner.run_batch(batch_id, task_path, out_dir, core_text="CORE", mock_subprocess=mock_sp)

    assert res.ok is True
    assert res.status == "OK"
    assert len(res.records) == 1
    assert (out_dir / f"{batch_id}.output.json").exists()
    assert (out_dir / f"{batch_id}.meta.json").exists()

    meta = json.loads((out_dir / f"{batch_id}.meta.json").read_text(encoding="utf-8"))
    assert meta["agent_provider"] == "agy"
    assert meta["items_valid"] == 1
    assert meta["contract_version"] == "article-compact-v2"
    assert meta["domain_errors"] == []


def test_agy_runner_ban_ghi_sai_hop_dong_thanh_partial(tmp_path):
    """Bản ghi sai enum bị từ chối, lô thành PARTIAL và lỗi nằm trong meta."""
    task_dir, out_dir = tmp_path / "tasks", tmp_path / "outputs"
    task_dir.mkdir()
    out_dir.mkdir()
    batch_id = "article_TEST_03"
    task_path = task_dir / f"{batch_id}.task.json"
    task_path.write_text(json.dumps({"a": [{
        "i": 0, "t": "Thị trường chứng khoán tăng mạnh",
        "p": ["VN-Index tăng hơn 15 điểm trong phiên.", "Dòng tiền lan tỏa sang nhóm bluechip."]}]}),
        encoding="utf-8")
    bad = [{"i": 0, "e": [], "s": "Tóm tắt có dấu.", "k": ["một", "hai"],
            "im": "Dòng tiền lan tỏa báo hiệu xu hướng tích cực cho thị trường.",
            "sn": "positive", "ts": "today", "c": [0, 1]}]
    events = [{"type": "init", "data": {"model": "gemini-3.8-flash-low", "tools": []}},
              {"type": "result", "data": {"response": json.dumps(bad), "usage": {}}}]
    out = "\n".join(json.dumps(e) for e in events) + "\n"

    def mock_sp(cmd, stdin_data, env, cwd):
        return MockProcessResult(stdout=out, stderr="", returncode=0)

    runner = AgyRunner(profile_root=tmp_path / "profiles", work_root=tmp_path / "work")
    res = runner.run_batch(batch_id, task_path, out_dir, core_text="CORE", mock_subprocess=mock_sp)
    assert res.status == "PARTIAL" and res.records == []
    meta = json.loads((out_dir / f"{batch_id}.meta.json").read_text(encoding="utf-8"))
    assert meta["domain_errors"][0].startswith("i=0: enum:sn")


def test_agy_runner_run_batch_quota_429(tmp_path):
    """Kiểm tra phân loại lỗi QUOTA khi gặp mã lỗi 429."""
    task_dir = tmp_path / "tasks"
    out_dir = tmp_path / "outputs"
    task_dir.mkdir()
    out_dir.mkdir()

    batch_id = "article_TEST_02"
    task_path = task_dir / f"{batch_id}.task.json"
    task_path.write_text(json.dumps({"a": [{"i": 0, "t": "Test", "p": ["p0"]}]}), encoding="utf-8")

    def mock_sp(cmd, stdin_data, env, cwd):
        return MockProcessResult(
            stdout="",
            stderr="AGY_ERROR: 429 Resource Exhausted. Quota limit reached.",
            returncode=3,
        )

    runner = AgyRunner(profile_root=tmp_path / "profiles", work_root=tmp_path / "work")
    res = runner.run_batch(batch_id, task_path, out_dir, core_text="CORE", mock_subprocess=mock_sp)

    assert res.ok is False
    assert res.status == "QUOTA"
    assert "Resource Exhausted" in res.error_message


def test_agy_runner_run_batch_violation_tool(tmp_path):
    """Kiểm tra phân loại lỗi VIOLATION khi mô hình cố tình gọi tool."""
    task_dir = tmp_path / "tasks"
    out_dir = tmp_path / "outputs"
    task_dir.mkdir()
    out_dir.mkdir()

    batch_id = "article_TEST_03"
    task_path = task_dir / f"{batch_id}.task.json"
    task_path.write_text(json.dumps({"a": [{"i": 0, "t": "Test", "p": ["p0"]}]}), encoding="utf-8")

    mock_events = [
        {"type": "init", "data": {"model": "gemini-3.8-flash-low"}},
        {"type": "step_update", "step": {"type": "tool", "tool_name": "run_command"}},
        {"type": "result", "data": {"response": "[]", "usage": {}}},
    ]
    stdout_text = "\n".join(json.dumps(e) for e in mock_events) + "\n"

    def mock_sp(cmd, stdin_data, env, cwd):
        return MockProcessResult(stdout=stdout_text, stderr="", returncode=0)

    runner = AgyRunner(profile_root=tmp_path / "profiles", work_root=tmp_path / "work")
    res = runner.run_batch(batch_id, task_path, out_dir, core_text="CORE", mock_subprocess=mock_sp)

    assert res.ok is False
    assert res.status == "VIOLATION"
    assert "Zero-Tool" in res.error_message


def test_agy_runner_soft_fail_luu_phan_hoi_tho(tmp_path, monkeypatch):
    """Lô không bóc được bản ghi nào để lại tệp phản hồi thô đã che bí mật và ghi đường dẫn."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("OPS_TRACE_WAVE", raising=False)
    task_dir, out_dir = tmp_path / "tasks", tmp_path / "outputs"
    task_dir.mkdir()
    out_dir.mkdir()
    batch_id = "article_W99990000_01"
    task_path = task_dir / f"{batch_id}.task.json"
    task_path.write_text(json.dumps({"a": [{"i": 0, "t": "Tiêu đề", "p": ["Đoạn văn một."]}]}),
                         encoding="utf-8")
    events = [{"type": "init", "data": {"model": "gemini-3.8-flash-low", "tools": []}},
              {"type": "result", "data": {"response": "Xin lỗi, tôi sk-abcdefghijklmnop1234 không làm được.",
                                          "usage": {}}}]
    out = "\n".join(json.dumps(e) for e in events) + "\n"

    def mock_sp(cmd, stdin_data, env, cwd):
        return MockProcessResult(stdout=out, stderr="cảnh báo", returncode=0)

    runner = AgyRunner(profile_root=tmp_path / "profiles", work_root=tmp_path / "work")
    res = runner.run_batch(batch_id, task_path, out_dir, core_text="CORE", mock_subprocess=mock_sp)
    assert res.status == "SOFT_FAIL" and res.raw_ref
    text = Path(res.raw_ref).read_text(encoding="utf-8")
    assert "Xin lỗi" in text and "sk-abcdefghijklmnop1234" not in text and "cảnh báo" in text
    assert Path(res.raw_ref).parent.name == "raw" and "W99990000" in res.raw_ref
