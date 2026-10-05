"""Tests chặn tự động hoá phá hoại — ADR 0008.

Hai bất biến:
1. **Không thể xoá nhầm packet chưa xử lý** — dọn dẹp phải dựa vào bằng chứng hoàn tất
   trong DB, không xoá trắng theo tên tệp.
2. **Không tiêu thụ token khi chưa ai cấp quyền**, và thất bại phải ồn ào thay vì in
   "hoàn tất 100%" giả.
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.agent.batch_handoff import split_tasks_into_batches
from src.core.models import Article
from src.db.store import ArticleStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "clean_completed_packets",
    PROJECT_ROOT / "scripts" / "maintenance" / "clean_completed_packets.py")
cleaner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cleaner)

_SPEC_AP = importlib.util.spec_from_file_location(
    "auto_pilot", PROJECT_ROOT / "scripts" / "auto_pilot.py")
auto_pilot = importlib.util.module_from_spec(_SPEC_AP)
_SPEC_AP.loader.exec_module(auto_pilot)


def _write_packet(task_dir: Path, name: str, article_ids: list[str]) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    p = task_dir / f"{name}.task.json"
    p.write_text(json.dumps({"batch_id": name,
                             "tasks": [{"article_id": a} for a in article_ids]},
                            ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / "t.db")
    store = ArticleStore(db_path=db)
    art = Article(url="https://a.vn/x.htm", title="Bài A", source_domain="a.vn",
                  summary="tóm tắt", content_text="nội dung")
    store.insert(art)
    return store, db, tmp_path, art.url_title_hash


def _mark_l1_done(store, article_id: str) -> None:
    conn = store.connect()
    conn.execute(
        "INSERT OR REPLACE INTO l1_outputs (article_id, output_json, dod_pass, created_at) "
        "VALUES (?, ?, 1, '2026-09-17T10:00:00+07:00')", (article_id, "{}"))
    conn.commit()
    conn.close()


def test_unfinished_packet_is_never_deleted(env):
    """Bất biến số 1: packet chưa có bằng chứng hoàn tất KHÔNG được xoá."""
    _store, db, tmp, _aid = env
    packet = _write_packet(tmp / "data" / "agent_tasks" / "l1", "l1_batch_01",
                           ["chua_xong_1", "chua_xong_2"])

    cleaner.main(["--db-path", db, "--task-dir", "data/agent_tasks", "--apply"])

    assert packet.exists(), "packet chưa xử lý đã bị xoá — đúng lỗi đang vá"


def test_completed_packet_is_deleted(env):
    """Chiều ngược lại: packet đã hoàn tất PHẢI được dọn, nếu không sẽ phình đĩa."""
    store, db, tmp, aid = env
    _mark_l1_done(store, aid)
    packet = _write_packet(tmp / "data" / "agent_tasks" / "l1", "l1_batch_01", [aid])

    cleaner.main(["--db-path", db, "--task-dir", "data/agent_tasks", "--apply"])

    assert not packet.exists()


def test_partially_completed_batch_is_kept(env):
    """Lô gom: chỉ cần MỘT bài chưa xong thì giữ cả lô."""
    store, db, tmp, aid = env
    _mark_l1_done(store, aid)
    packet = _write_packet(tmp / "data" / "agent_tasks" / "l1", "l1_batch_01",
                           [aid, "con_thieu"])

    cleaner.main(["--db-path", db, "--task-dir", "data/agent_tasks", "--apply"])

    assert packet.exists()


def test_unreadable_packet_is_kept(env):
    """Packet hỏng không đọc được thì giữ lại — im lặng xoá là mất dữ liệu."""
    _store, db, tmp, _aid = env
    d = tmp / "data" / "agent_tasks" / "l1"
    d.mkdir(parents=True, exist_ok=True)
    bad = d / "hong.task.json"
    bad.write_text("{ khong phai json", encoding="utf-8")

    cleaner.main(["--db-path", db, "--task-dir", "data/agent_tasks", "--apply"])

    assert bad.exists()


def test_dry_run_deletes_nothing(env):
    """Mặc định (không --apply) tuyệt đối không xoá."""
    store, db, tmp, aid = env
    _mark_l1_done(store, aid)
    packet = _write_packet(tmp / "data" / "agent_tasks" / "l1", "l1_batch_01", [aid])

    cleaner.main(["--db-path", db, "--task-dir", "data/agent_tasks"])

    assert packet.exists()


def test_batch_ids_unique_across_runs(tmp_path, monkeypatch):
    """Hai lần gom lô liên tiếp phải sinh mã lô khác nhau.

    Trước đây mã luôn đếm lại từ `batch_01` nên lô mới trùng tên lô cũ; AutoPilot thấy
    output cùng tên liền bỏ qua lô MỚI rồi nạp lại dữ liệu CŨ và báo thành công.
    """
    monkeypatch.chdir(tmp_path)
    tasks = [{"article_id": "a1", "input": {"title": "t"}}]
    first = split_tasks_into_batches(tasks, batch_size=1, base_dir="out")
    second = split_tasks_into_batches(tasks, batch_size=1, base_dir="out")

    assert Path(first[0]).name != Path(second[0]).name, \
        "mã lô trùng nhau giữa hai lần chạy — tái lập lỗi va chạm batch"


def test_run_cmd_raises_on_failure(tmp_path):
    """Lệnh con lỗi phải ném ngoại lệ, không được chỉ in rồi đi tiếp."""
    with pytest.raises(auto_pilot.CommandFailed):
        auto_pilot.run_cmd([sys.executable, "-c", "import sys; sys.exit(3)"])


def test_confirm_refuses_without_tty_and_without_yes(tmp_path, monkeypatch, capsys):
    """Không có terminal tương tác và không có --yes ⇒ từ chối tiêu thụ token."""
    packet = _write_packet(tmp_path, "batch_01", ["a1"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    allowed = auto_pilot._confirm_activation([str(packet)], "low", False, assume_yes=False)

    assert allowed is False
    assert "Từ chối tiêu thụ token" in capsys.readouterr().out


def test_confirm_allows_with_explicit_yes(tmp_path):
    """Có cờ --yes do người vận hành tự khai thì được phép chạy."""
    packet = _write_packet(tmp_path, "batch_01", ["a1"])
    assert auto_pilot._confirm_activation([str(packet)], "low", False, assume_yes=True)


def test_missing_agy_reports_and_stops(tmp_path, monkeypatch, capsys):
    """Thiếu `agy` phải báo rõ và dừng, không nuốt FileNotFoundError."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(auto_pilot, "run_cmd", lambda *a, **k: None)
    monkeypatch.setattr(auto_pilot, "PROJECT_ROOT", tmp_path)
    _write_packet(tmp_path / "data" / "agent_tasks", "batch_01", ["a1"])
    monkeypatch.setattr(auto_pilot.shutil, "which", lambda _n: None)

    rc = auto_pilot.run_gold_pipeline(date="today", assume_yes=True)

    assert rc == 1
    assert "Không tìm thấy `agy`" in capsys.readouterr().out
