"""Ghi vết span của một đợt vào `ops_spans`; không làm gì khi thiếu biến môi trường."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

ENV_DB = "OPS_TRACE_DB"
ENV_WAVE = "OPS_TRACE_WAVE"
ENV_PARENT = "OPS_TRACE_PARENT"

VN_TZ = timezone(timedelta(hours=7))
REGISTRY_PATH = Path(__file__).resolve().parents[3] / ".agents" / "registry.yaml"

SPAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS ops_spans (
  span_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  parent_id TEXT,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  actor_id TEXT,
  skill TEXT,
  entrypoint TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  attrs_json TEXT,
  input_ref TEXT,
  output_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_spans_trace ON ops_spans(trace_id, started_at);
CREATE INDEX IF NOT EXISTS idx_ops_spans_actor ON ops_spans(actor_id, started_at);
CREATE INDEX IF NOT EXISTS idx_ops_spans_parent ON ops_spans(parent_id);
"""

# Script chạy bên trong `article_run.py` và tác nhân tương ứng trong registry.
SCRIPT_ACTORS = {
    "article_pack.py": "article-packer",
    "article_expand.py": "article-expander",
    "l1_ingest.py": "l1-ingest-gate",
    "agent_ingest.py": "gold-ingest-gate",
    "token_ledger.py": "token-ledger",
    "handoff.py": "token-ledger",
    "ctx_probe.py": "token-ledger",
}


def _now() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="milliseconds")


@lru_cache(maxsize=1)
def _registry() -> dict[str, dict]:
    """Đọc `registry.yaml` một lần và trả về từ điển theo id tác nhân."""
    try:
        import yaml

        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        return {a["id"]: a for a in data.get("agents", []) if isinstance(a, dict) and "id" in a}
    except Exception:  # noqa: BLE001 — thiếu registry không được làm hỏng đợt
        return {}


def registry_info(actor_id: str | None) -> tuple[str | None, str | None]:
    """Tra skill và entrypoint của một tác nhân.

    Args:
        actor_id: Mã tác nhân trong registry.

    Returns:
        Cặp (skill, entrypoint), None khi không có.
    """
    if not actor_id:
        return None, None
    a = _registry().get(actor_id) or {}
    skill = a.get("skill")
    if skill:
        skill = Path(str(skill)).parent.name or str(skill)
    entry = a.get("entrypoint") or a.get("cli")
    return skill, (str(entry)[:120] if entry else None)


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


class Tracer:
    """Ghi span vào `ops.db`; mọi lỗi ghi bị nuốt để không ảnh hưởng đợt.

    Attributes:
        db_path: Đường dẫn `ops.db`.
        trace_id: Mã đợt.
        parent_id: Span cha mặc định của span mới.
    """

    def __init__(self, db_path: str | Path, trace_id: str, parent_id: str | None = None) -> None:
        """Gắn tracer vào một đợt.

        Args:
            db_path: Đường dẫn `ops.db`.
            trace_id: Mã đợt.
            parent_id: Span cha mặc định.
        """
        self.db_path = str(db_path)
        self.trace_id = trace_id
        self.parent_id = parent_id
        self._ready = False

    def _ensure(self, conn: sqlite3.Connection) -> None:
        if not self._ready:
            conn.executescript(SPAN_SCHEMA)
            self._ready = True

    def begin(self, name: str, kind: str, actor_id: str | None = None, *,
              span_id: str | None = None, parent_id: str | None = ..., **attrs: Any) -> str | None:
        """Mở một span ở trạng thái `running`; mở lại cùng `span_id` thì ghi đè.

        Args:
            name: Tên span.
            kind: workflow, step, script, agent, tool, gate hoặc human.
            actor_id: Mã tác nhân trong registry.
            span_id: Mã span cố định (để chạy lại sau crash không nhân bản).
            parent_id: Span cha; bỏ trống dùng cha mặc định, None cho span gốc.
            **attrs: Thuộc tính ban đầu.

        Returns:
            Mã span, hoặc None khi ghi lỗi.
        """
        try:
            sid = span_id or f"{self.trace_id}.{kind}.{int(time.time() * 1000)}"
            pid = self.parent_id if parent_id is ... else parent_id
            skill, entry = registry_info(actor_id)
            entry = attrs.pop("entrypoint", None) or entry
            with _connect(self.db_path) as conn:
                self._ensure(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO ops_spans(span_id, trace_id, parent_id, kind, name, "
                    "actor_id, skill, entrypoint, started_at, status, attrs_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, self.trace_id, pid, kind, name, actor_id, skill, entry, _now(),
                     "running", json.dumps(attrs, ensure_ascii=False, default=str) if attrs else None))
            return sid
        except Exception:  # noqa: BLE001
            return None

    def finish(self, span_id: str | None, status: str = "ok", **attrs: Any) -> None:
        """Đóng span, gộp thuộc tính mới vào thuộc tính cũ.

        Args:
            span_id: Mã span từ `begin`.
            status: ok, fail, timeout, skipped, parked, cancelled hoặc interrupted.
            **attrs: Thuộc tính bổ sung.
        """
        if not span_id:
            return
        input_ref = attrs.pop("input_ref", None)
        output_ref = attrs.pop("output_ref", None)
        try:
            with _connect(self.db_path) as conn:
                row = conn.execute("SELECT attrs_json FROM ops_spans WHERE span_id = ?",
                                   (span_id,)).fetchone()
                merged = json.loads(row[0]) if row and row[0] else {}
                merged.update(attrs)
                conn.execute(
                    "UPDATE ops_spans SET ended_at = ?, status = ?, attrs_json = ?, "
                    "input_ref = COALESCE(?, input_ref), output_ref = COALESCE(?, output_ref) "
                    "WHERE span_id = ?",
                    (_now(), status, json.dumps(merged, ensure_ascii=False, default=str),
                     input_ref, output_ref, span_id))
        except Exception:  # noqa: BLE001
            return

    def close_running(self, status: str = "interrupted") -> int:
        """Đóng mọi span còn `running` của đợt (tiến trình chết, đợt đã chốt).

        Args:
            status: Trạng thái gán cho span bị bỏ dở.

        Returns:
            Số span đã đóng.
        """
        try:
            with _connect(self.db_path) as conn:
                self._ensure(conn)
                cur = conn.execute(
                    "UPDATE ops_spans SET ended_at = ?, status = ? "
                    "WHERE trace_id = ? AND status = 'running' AND kind != 'workflow'",
                    (_now(), status, self.trace_id))
                return cur.rowcount
        except Exception:  # noqa: BLE001
            return 0

    def child_env(self, parent_id: str | None) -> dict[str, str]:
        """Dựng biến môi trường để tiến trình con ghi span dưới `parent_id`.

        Args:
            parent_id: Span cha của các span tiến trình con sẽ tạo.

        Returns:
            Từ điển biến môi trường.
        """
        env = {ENV_DB: self.db_path, ENV_WAVE: self.trace_id}
        if parent_id:
            env[ENV_PARENT] = parent_id
        return env


class SpanHandle:
    """Tay cầm của một span đang mở, dùng trong khối `with`.

    Attributes:
        id: Mã span, None khi không ghi vết.
    """

    def __init__(self, tracer: Tracer | None, span_id: str | None) -> None:
        """Gắn tay cầm vào span đã mở.

        Args:
            tracer: Tracer sở hữu span.
            span_id: Mã span.
        """
        self._tracer = tracer
        self.id = span_id
        self._attrs: dict[str, Any] = {}
        self.status = "ok"

    def set(self, **attrs: Any) -> None:
        """Ghi thuộc tính sẽ gộp vào span lúc đóng.

        Args:
            **attrs: Thuộc tính.
        """
        if "status" in attrs:  # `status` là tham số của finish(); giữ giá trị dưới tên khác
            attrs["result_status"] = attrs.pop("status")
        self._attrs.update(attrs)

    def fail(self, status: str = "fail", **attrs: Any) -> None:
        """Đánh dấu span kết thúc không thành công.

        Args:
            status: Trạng thái cuối.
            **attrs: Thuộc tính bổ sung.
        """
        self.status = status
        self._attrs.update(attrs)

    def env(self) -> dict[str, str]:
        """Biến môi trường cho tiến trình con của span này."""
        return self._tracer.child_env(self.id) if self._tracer and self.id else {}


def from_env() -> Tracer | None:
    """Dựng tracer từ biến môi trường do daemon đặt; None khi chạy tay.

    Returns:
        Tracer với cha mặc định là `OPS_TRACE_PARENT`, hoặc None.
    """
    db, wave = os.environ.get(ENV_DB), os.environ.get(ENV_WAVE)
    if not db or not wave:
        return None
    return Tracer(db, wave, os.environ.get(ENV_PARENT) or None)


@contextmanager
def span(name: str, kind: str, actor_id: str | None = None, *, tracer: Tracer | None = None,
         span_id: str | None = None, **attrs: Any) -> Iterator[SpanHandle]:
    """Mở một span cho khối lệnh; ngoại lệ đánh dấu `fail` rồi ném lại.

    Không làm gì (tay cầm rỗng) khi không có tracer và không có biến môi trường.

    Args:
        name: Tên span.
        kind: Loại span.
        actor_id: Mã tác nhân trong registry.
        tracer: Tracer chỉ định; bỏ trống thì dựng từ môi trường.
        span_id: Mã span cố định.
        **attrs: Thuộc tính ban đầu.

    Yields:
        SpanHandle.
    """
    tr = tracer or from_env()
    sid = tr.begin(name, kind, actor_id, span_id=span_id, **attrs) if tr else None
    handle = SpanHandle(tr, sid)
    try:
        yield handle
    except BaseException:
        handle.status = "fail" if handle.status == "ok" else handle.status
        raise
    finally:
        if tr and sid:
            tr.finish(sid, handle.status, **handle._attrs)
