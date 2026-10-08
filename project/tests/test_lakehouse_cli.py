"""Bộ kiểm thử cho giao diện dòng lệnh scripts/lakehouse_cli.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "scripts" / "lakehouse_cli.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Hàm bổ trợ thực thi lakehouse_cli qua tiến trình con."""
    cmd = [sys.executable, str(CLI_PATH), *args]
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_cli_help() -> None:
    """Kiểm tra câu lệnh --help hiển thị đầy đủ thông tin các lệnh con."""
    proc = run_cli("--help")
    assert proc.returncode == 0
    stdout = proc.stdout or ""
    assert "ingest" in stdout
    assert "consolidate" in stdout
    assert "verify" in stdout


def test_cli_e2e_pipeline() -> None:
    """Kiểm tra toàn bộ chuỗi lệnh CLI: ingest -> consolidate -> verify."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        storage_root = base / "news-data"
        input_json = base / "articles.json"

        date_str = "2026-10-08"

        # 1. Tạo dữ liệu đầu vào JSON
        articles_data = [
            {
                "article_id": "CLI_001",
                "title": "Bản tin kiểm thử CLI về FPT",
                "symbols": "FPT",
                "summary": "FPT đạt doanh thu cao",
                "key_points": ["Doanh thu phần mềm tăng 30%"],
                "implication": "Cổ phiếu FPT triển vọng tốt",
                "citations": ["Trích dẫn doanh thu phần mềm quý 3"],
                "published_at": "2026-10-08T10:00:00Z",
            }
        ]
        with open(input_json, "w", encoding="utf-8") as f:
            json.dump(articles_data, f)

        # 2. Chạy lệnh ingest
        proc_ingest = run_cli(
            "--root", str(storage_root),
            "ingest",
            "--input", str(input_json),
            "--date", date_str,
            "--dev-id", "dev_cli",
            "--batch-id", "b_cli",
        )
        assert proc_ingest.returncode == 0
        assert "Đã xuất bản" in proc_ingest.stdout

        # 3. Chạy lệnh consolidate
        proc_cons = run_cli(
            "--root", str(storage_root),
            "consolidate",
            "--date", date_str,
        )
        assert proc_cons.returncode == 0
        assert "Hoàn tất hợp nhất dữ liệu" in proc_cons.stdout
        assert "Số bài viết duy nhất: 1" in proc_cons.stdout

        # 4. Chạy lệnh verify
        proc_ver = run_cli(
            "--root", str(storage_root),
            "verify",
            "--manifest", "_manifest/latest.json",
        )
        assert proc_ver.returncode == 0
        assert "Kiểm chứng thành công" in proc_ver.stdout
