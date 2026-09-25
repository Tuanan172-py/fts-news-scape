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
    salvage_json_records,
    validate_records,
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


def test_salvage_json_records():
    """Kiểm tra bóc tách và khôi phục mảng bản ghi JSON từ chuỗi mô hình."""
    # 1. Mảng JSON chuẩn
    raw_1 = '[{"i": 0, "s": "Tóm tắt bài 0"}]'
    assert salvage_json_records(raw_1) == [{"i": 0, "s": "Tóm tắt bài 0"}]

    # 2. Bọc trong khối markdown ```json ... ```
    raw_2 = '```json\n[{"i": 1, "s": "Tóm tắt bài 1"}]\n```'
    assert salvage_json_records(raw_2) == [{"i": 1, "s": "Tóm tắt bài 1"}]

    # 3. Đối tượng có trường 'r'
    raw_3 = '{"r": [{"i": 2, "s": "Tóm tắt bài 2"}]}'
    assert salvage_json_records(raw_3) == [{"i": 2, "s": "Tóm tắt bài 2"}]

    # 4. Kèm lời dẫn bên ngoài mảng
    raw_4 = 'Dưới đây là kết quả:\n[{"i": 3, "s": "Tóm tắt bài 3"}]\nHy vọng giúp ích!'
    assert salvage_json_records(raw_4) == [{"i": 3, "s": "Tóm tắt bài 3"}]

    # 5. Lỗi không bóc được
    with pytest.raises(ValueError):
        salvage_json_records("Không có json nào ở đây.")


def test_validate_records():
    """Kiểm tra logic thẩm định miền nghiệp vụ."""
    packet_items = [
        {
            "i": 0,
            "t": "Ngân hàng Nhà nước hạ lãi suất",
            "p": ["Đoạn mở đầu có dấu.", "Đoạn 1 số liệu định lượng.", "Đoạn 2 kết luận."],
        }
    ]

    # Ca đạt chuẩn
    valid_recs = [
        {
            "i": 0,
            "e": [["Ngân hàng Nhà nước", "INS"]],
            "c": [0, 1],
            "s": "Tóm tắt tiếng Việt có dấu đầy đủ.",
            "im": "Hàm ý dòng tiền tích cực cho thị trường.",
        }
    ]
    recs, errs = validate_records(valid_recs, packet_items)
    assert len(recs) == 1
    assert len(errs) == 0

    # Ca lỗi mã nhóm thực thể không thuộc 11 nhóm
    bad_group = [
        {
            "i": 0,
            "e": [["Ngân hàng Nhà nước", "UNKNOWN_GROUP"]],
            "c": [0],
            "s": "Có dấu",
            "im": "Có dấu",
        }
    ]
    recs, errs = validate_records(bad_group, packet_items)
    assert len(recs) == 0
    assert any("không thuộc 11 nhóm chuẩn" in e for e in errs)

    # Ca lỗi chỉ số trích dẫn vượt dải
    bad_citation = [
        {
            "i": 0,
            "e": [["Ngân hàng Nhà nước", "INS"]],
            "c": [5],  # Chỉ có 3 đoạn 0..2
            "s": "Có dấu",
            "im": "Có dấu",
        }
    ]
    recs, errs = validate_records(bad_citation, packet_items)
    assert len(recs) == 0
    assert any("vượt dải đoạn" in e for e in errs)

    # Ca lỗi mất dấu tiếng Việt
    bad_diacritics = [
        {
            "i": 0,
            "e": [["Ngân hàng Nhà nước", "INS"]],
            "c": [0],
            "s": "Tom tat khong co dau",
            "im": "Ham y khong co dau",
        }
    ]
    recs, errs = validate_records(bad_diacritics, packet_items)
    assert len(recs) == 0
    assert any("mất hoàn toàn dấu" in e for e in errs)


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
                "p": ["VN-Index tăng hơn 15 điểm.", "Dòng tiền lan tỏa."],
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
                            "c": [0, 1],
                            "s": "Chỉ số VN-Index tăng mạnh hơn 15 điểm.",
                            "im": "Dòng tiền lan tỏa báo hiệu xu hướng tích cực.",
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
