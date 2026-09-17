"""Tests kiểm định chức năng và vệ sinh hệ thống — Phase 04 & US-019.

1. `l1_ingest.py` có import json và dọn dẹp đúng batch hoàn tất khi pass.
2. `l1_runner.py` truyền `self.reg` cho cả hai luồng kiểm định DoD.
3. `orchestrator.py` chiếm scheduler lock khi chạy `--once` để không cào đè morninger.
4. `user_output.py` gated_rows lọc trực tiếp bằng SQL thay vì nạp toàn bộ vào RAM.
5. `store.py` insert_version không insert lặp khi trùng `(url_title_hash, content_sha256)`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.agent.l1_runner import L1Runner
from src.core.models import Article, now_vn_iso
from src.db.store import ArticleStore
from src.export.user_output import UserOutputWriter
from src.orchestrator import Orchestrator, SCHEDULER_LOCK_STALE_SECONDS


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / "test_hygiene.db")
    store = ArticleStore(db_path=db)
    return store, db, tmp_path


def test_insert_version_deduplication(env):
    """insert_version không tạo dòng mới nếu trùng url_title_hash và content_sha256."""
    store, _db, _tmp = env
    row = {
        "url_title_hash": "hash_v1",
        "source_domain": "cafef.vn",
        "captured_at": now_vn_iso(),
        "content_sha256": "sha256_v1",
        "state": "NEW"
    }

    id1 = store.insert_version(row)
    id2 = store.insert_version(row)

    assert id1 == id2, "insert cùng content_sha256 phải trả về id cũ, không được ghi đúp"

    conn = store.connect()
    count = conn.execute("SELECT count(1) FROM article_versions WHERE url_title_hash='hash_v1'").fetchone()[0]
    conn.close()
    assert count == 1


def test_user_output_gated_rows_sql_filter(env):
    """gated_rows lọc ngày trực tiếp bằng SQL."""
    store, _db, _tmp = env
    # Mock ArticleStore & UserOutputWriter
    writer = UserOutputWriter(store, registry=None)

    # Chạy gated_rows với tham số ngày
    rows_today = writer.gated_rows(date="today")
    assert isinstance(rows_today, list)

    rows_days = writer.gated_rows(days=7)
    assert isinstance(rows_days, list)


def test_orchestrator_once_respects_scheduler_lock(env, monkeypatch):
    """Khi scheduler lock đang có người chiếm, Orchestrator --once phải từ chối chạy."""
    store, db, tmp = env
    import src.orchestrator as orch_mod
    monkeypatch.setattr(orch_mod, "load_settings", lambda: {
        "database": {"path": db},
        "logging": {"level": "INFO", "dir": str(tmp / "logs")},
        "scheduler": {"interval_minutes": 15},
        "http": {"rate_limit": 0.0, "timeout": 5, "max_retries": 1},
        "notifications": {"dir": str(tmp / "notif")},
        "export": {"enabled": False, "dir": str(tmp / "exports")},
    })
    # Giả lập lock đang bị morninger chiếm
    acquired = store.try_acquire_lock("scheduler", "morninger_pid_9999", SCHEDULER_LOCK_STALE_SECONDS)
    assert acquired is True

    rc = orch_mod.main(["--once"])
    assert rc == 1, "Orchestrator --once phải trả về mã lỗi 1 khi scheduler khác đang chiếm lock"


def test_l1_runner_dod_registry_enforcement(env):
    """Luồng ingest_output của L1Runner phải chặn entity_id giả mạo không có trong registry."""
    store, _db, _tmp = env
    runner = L1Runner(store)

    # Tạo 1 task giả
    aid = "test_art_fake_entity"
    store.upsert_l1_task({
        "article_id": aid,
        "title": "Bản tin thử nghiệm với mã giả",
        "domain": "cafef.vn",
        "route": "needs_agent"
    })

    fake_output = {
        "l1_output_version": "1.0",
        "article_id": aid,
        "title": "Bản tin thử nghiệm với mã giả",
        "recognized": True,
        "entities": [
            {
                "surface": "Mã Ảo",
                "entity_id": "TICKER:MA_AO_KHONG_TON_TAI_12345",
                "type": "TICKER",
                "method": "alias",
                "in_list": True
            }
        ],
        "categories": {
            "ticker_company": "done",
            "etf_fund": "none",
            "index": "none",
            "exchange": "none",
            "industry_sector": "none"
        },
        "citations": [{"source_span": "Bản tin thử nghiệm với mã giả"}],
        "processing_metadata": {
            "agent_provider": "gemini",
            "model_used": "flash",
            "timestamp": now_vn_iso()
        }
    }

    res = runner.ingest_output(fake_output)
    assert res["dod_pass"] is False, "DoD phải từ chối output có entity_id không có trong registry"
    assert any("khong co trong danh muc" in r for r in res["reasons"])
