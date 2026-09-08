from __future__ import annotations

import json
from pathlib import Path

from src.agent.archive import archive_completed_tasks, archive_task_packet
from src.agent.manifest import (
    create_batch_manifest, format_short_time, load_batch_manifest,
    print_batch_summary_table,
)


def test_format_short_time():
    assert format_short_time("") == "--/-- --:--"
    assert format_short_time("2026-09-04T13:58:00+07:00") == "04/09 13:58"


def test_create_and_load_batch_manifest(tmp_path):
    tasks = [
        {
            "article_id": "art_001",
            "title": "Bai viet 1",
            "domain": "cafef.vn",
            "enqueued_at": "2026-09-04T13:58:00+07:00",
            "input": {},
        },
        {
            "article_id": "art_002",
            "title": "Bai viet 2",
            "domain": "vietstock.vn",
            "input": {"fetch_ts": "2026-09-04T14:00:00+07:00"},
        },
    ]

    manifest = create_batch_manifest(tasks, tmp_path, batch_type="gold", order="desc")
    assert manifest["batch_size"] == 2
    assert manifest["batch_type"] == "gold"
    assert manifest["order"] == "desc"
    assert manifest["batch_id"].startswith("BATCH_GOLD_")
    assert len(manifest["articles"]) == 2

    loaded = load_batch_manifest(tmp_path)
    assert loaded is not None
    assert loaded["batch_id"] == manifest["batch_id"]

    # Chi kiem tra khong no khi in bang ra terminal
    print_batch_summary_table(manifest)


def test_archive_task_packet(tmp_path):
    task_dir = tmp_path / "tasks"
    task_dir.mkdir()
    (task_dir / "aid_1.task.json").write_text("{}", encoding="utf-8")
    (task_dir / "aid_2.task.json").write_text("{}", encoding="utf-8")

    archived_file = archive_task_packet("aid_1", task_dir, archive_date="20260907")
    assert archived_file is not None
    assert Path(archived_file).is_file()
    assert not (task_dir / "aid_1.task.json").is_file()          # da roi khoi hang doi
    assert (task_dir / "archive" / "20260907" / "aid_1.task.json").is_file()

    # article_id khong ton tai thi bo qua, khong tinh vao so luong
    cnt = archive_completed_tasks(["aid_2", "non_existing"], task_dir, archive_date="20260907")
    assert cnt == 1
    assert (task_dir / "archive" / "20260907" / "aid_2.task.json").is_file()
