"""Kiểm đường dẫn DB vận hành không rơi vào OneDrive và chỉ một tiến trình cào tin chạy."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.core import config
from src.core.config import (OPERATIONAL_DB_PATH, UnsafeDatabasePathError, is_synced_location,
                             resolve_db_path)
from src.core.proclock import SingleInstanceLock

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def no_db_env(monkeypatch):
    """Xoá các biến môi trường chỉ định DB để kiểm đường mặc định."""
    for name in ("MONOCLE_DB_PATH", "MONOCLE_DATA_DIR", config.ALLOW_SYNCED_DB_ENV):
        monkeypatch.delenv(name, raising=False)


def test_thieu_bien_moi_truong_van_tro_dung_db_van_hanh(no_db_env):
    """Tiến trình chạy theo lịch không có MONOCLE_DB_PATH vẫn phải ghi vào C:/data."""
    assert Path(config.load_settings()["database"]["path"]) == OPERATIONAL_DB_PATH.resolve()


def test_duong_dan_tuong_doi_khong_phu_thuoc_cwd(no_db_env, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = resolve_db_path({"database": {"path": str(tmp_path / "x.db")}})
    assert p == (tmp_path / "x.db").resolve()


@pytest.mark.parametrize("raw", [
    "data/monocle.db",
    "src/data/monocle.db",
    r"C:\Users\anpt\OneDrive - fpts.com.vn\bat_ky\monocle.db",
])
def test_db_trong_onedrive_hoac_kho_ma_bi_tu_choi(no_db_env, raw):
    with pytest.raises(UnsafeDatabasePathError, match="MONOCLE_DB_PATH"):
        resolve_db_path({"database": {"path": raw}})


def test_bien_moi_truong_tro_vao_onedrive_cung_bi_tu_choi(monkeypatch):
    monkeypatch.delenv(config.ALLOW_SYNCED_DB_ENV, raising=False)
    monkeypatch.setenv("MONOCLE_DB_PATH", str(PROJECT_ROOT / "data" / "monocle.db"))
    with pytest.raises(UnsafeDatabasePathError):
        config.load_settings()


def test_co_y_mo_ban_sao_cu_can_bien_cho_phep(no_db_env, monkeypatch):
    monkeypatch.setenv(config.ALLOW_SYNCED_DB_ENV, "1")
    p = resolve_db_path({"database": {"path": "data/monocle.db"}})
    assert p == (PROJECT_ROOT / "data" / "monocle.db").resolve()


def test_nhan_dien_vung_dong_bo():
    assert is_synced_location(Path(r"C:\Users\x\OneDrive - fpts.com.vn\a.db"))
    assert is_synced_location((PROJECT_ROOT / "data" / "monocle.db").resolve())
    assert not is_synced_location(Path(r"C:\data\news-scape\monocle.db"))


_CHILD = ("import sys; sys.path.insert(0, sys.argv[2]);"
          "from src.core.proclock import SingleInstanceLock as L;"
          "b = L(sys.argv[1]); ok = b.acquire(); print(ok, b.holder());"
          "sys.stdout.flush(); import time; time.sleep(float(sys.argv[3]))")


def _child(lock_path: Path, hold: float) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", _CHILD, str(lock_path), str(PROJECT_ROOT),
                             str(hold)], stdout=subprocess.PIPE, text=True)


def test_khoa_cao_chan_tien_trinh_thu_hai(tmp_path):
    lock_path = tmp_path / "capture.lock"
    first = SingleInstanceLock(lock_path)
    assert first.acquire()
    try:
        child = _child(lock_path, 0)
        out, _ = child.communicate(timeout=60)
        ok, holder = out.split()
        assert ok == "False", "tiến trình thứ hai không được chiếm khoá khi chủ khoá còn sống"
        assert holder.endswith(f":{__import__('os').getpid()}")
    finally:
        first.release()


def test_khoa_tu_nha_khi_chu_khoa_chet(tmp_path):
    lock_path = tmp_path / "capture.lock"
    holder = _child(lock_path, 60)
    try:
        assert holder.stdout.readline().split()[0] == "True"
        assert not SingleInstanceLock(lock_path).acquire()
    finally:
        holder.kill()
        holder.wait(timeout=30)
    # Python trong venv trên Windows là trình khởi chạy: giết nó thì tiến trình thông dịch
    # thật (đang giữ khoá) mới bị hệ điều hành dọn sau đó một nhịp, nên chờ có hạn.
    after = SingleInstanceLock(lock_path)
    deadline = time.monotonic() + 20
    while not after.acquire():
        assert time.monotonic() < deadline, \
            "khoá phải tự nhả khi tiến trình giữ khoá chết, không có trạng thái cũ"
        time.sleep(0.2)
    after.release()


def test_run_once_tu_choi_khi_morninger_giu_khoa(tmp_path, monkeypatch):
    """`orchestrator --once` (đường của run_once/news_cron) không được cào khi khoá đang bị giữ."""
    from src import orchestrator

    lock_path = tmp_path / "capture.lock"
    held = SingleInstanceLock(lock_path)
    assert held.acquire()

    class _Store:
        def try_acquire_lock(self, *a, **k):
            raise AssertionError("không được chạm khoá DB khi khoá tệp đã bị giữ")

    class _Orch:
        def __init__(self):
            self.store = _Store()
            self._lock_owner = "x:1"
            self.cycles = 0

        def shutdown(self):
            pass

        def run_cycle(self, names):
            raise AssertionError("không được chạy chu kỳ cào")

    monkeypatch.setattr(orchestrator, "Orchestrator", _Orch)
    monkeypatch.setattr(orchestrator, "capture_lock", lambda: SingleInstanceLock(lock_path))
    try:
        assert orchestrator.main(["--once"]) == 1
    finally:
        held.release()
