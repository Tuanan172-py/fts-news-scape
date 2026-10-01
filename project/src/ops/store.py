"""Lưu sự kiện, cảnh báo, breaker, trạng thái, đợt và lệnh vận hành trong `ops.db`."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from src.ops.redact import redact, redact_data
from src.ops.trace import SPAN_SCHEMA

VN_TZ = timezone(timedelta(hours=7))

LEVELS = ("debug", "info", "warn", "error", "critical")
ACTIVE_WAVE_STATUSES = ("SENSED", "PREFLIGHT", "PREPARED", "ANALYZING", "REPAIRING",
                        "ANALYZED", "FINISHING")
# Đợt ở các trạng thái này đã xong vòng đời; bài của chúng không còn bị giữ chỗ.
RELEASED_WAVE_STATUSES = ("DONE", "CANCELLED")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ops_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT NOT NULL,
  actor TEXT NOT NULL,
  wave_id TEXT,
  step TEXT,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  data_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_events_ts ON ops_events(ts);
CREATE INDEX IF NOT EXISTS idx_ops_events_wave ON ops_events(wave_id, ts);
CREATE TABLE IF NOT EXISTS ops_alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  severity TEXT NOT NULL,
  dedup_key TEXT,
  text TEXT NOT NULL,
  buttons_json TEXT,
  repeats INTEGER NOT NULL DEFAULT 1,
  sent_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_alerts_unsent ON ops_alerts(sent_at, id);
CREATE INDEX IF NOT EXISTS idx_ops_alerts_dedup ON ops_alerts(dedup_key, created_at);
CREATE TABLE IF NOT EXISTS provider_breakers (
  provider TEXT PRIMARY KEY,
  state TEXT NOT NULL DEFAULT 'CLOSED',
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_class TEXT,
  opened_at TEXT,
  reopen_at TEXT,
  reason TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ops_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ops_waves (
  wave_id TEXT PRIMARY KEY,
  workflow_id TEXT,
  status TEXT NOT NULL,
  step TEXT,
  trigger TEXT,
  target_date TEXT,
  n_articles INTEGER,
  level TEXT,
  provider TEXT,
  attempt INTEGER NOT NULL DEFAULT 0,
  opened_at TEXT NOT NULL,
  updated_at TEXT,
  progress_at TEXT,
  finished_at TEXT,
  reason TEXT,
  resume_on_breaker INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ops_waves_status ON ops_waves(status, opened_at);
CREATE TABLE IF NOT EXISTS ops_wave_articles (
  wave_id TEXT NOT NULL,
  article_id TEXT NOT NULL,
  PRIMARY KEY (wave_id, article_id)
);
CREATE INDEX IF NOT EXISTS idx_ops_wave_articles_article ON ops_wave_articles(article_id);
CREATE TABLE IF NOT EXISTS ops_article_attempts (
  article_id TEXT PRIMARY KEY,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_wave TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ops_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  evidence_json TEXT,
  impact REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  decided_at TEXT,
  story_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_proposals_status ON ops_proposals(status, impact);
CREATE TABLE IF NOT EXISTS ops_commands (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  result TEXT,
  processed_at TEXT
);
"""


def now_vn() -> datetime:
    """Trả về thời điểm hiện tại theo giờ Việt Nam.

    Returns:
        Đối tượng datetime có múi giờ +07:00.
    """
    return datetime.now(VN_TZ)


def iso(dt: datetime | None = None) -> str:
    """Định dạng thời điểm thành chuỗi ISO tới giây.

    Args:
        dt: Thời điểm cần định dạng. Mặc định là hiện tại.

    Returns:
        Chuỗi ISO 8601 có múi giờ.
    """
    return (dt or now_vn()).isoformat(timespec="seconds")


def parse_iso(text: str | None) -> datetime | None:
    """Đọc chuỗi ISO, gán giờ Việt Nam khi chuỗi không có múi giờ.

    Args:
        text: Chuỗi ISO hoặc None.

    Returns:
        Đối tượng datetime có múi giờ, hoặc None khi không đọc được.
    """
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=VN_TZ)


class OpsStore:
    """Truy cập `ops.db` an toàn giữa nhiều luồng của daemon.

    Mỗi thao tác mở một kết nối ngắn với `busy_timeout`, nên luồng Telegram, luồng
    workflow và vòng chính ghi đồng thời mà không chia sẻ đối tượng kết nối.

    Attributes:
        path: Đường dẫn tệp `ops.db`.
        log_dir: Thư mục ghi bản sao JSONL của sự kiện, hoặc None để tắt.
        dedup_minutes: Cửa sổ gộp cảnh báo cùng khoá.
    """

    def __init__(self, path: Path, *, log_dir: Path | None = None,
                 dedup_minutes: int = 30) -> None:
        """Tạo store và bảo đảm lược đồ tồn tại.

        Args:
            path: Đường dẫn tệp `ops.db`.
            log_dir: Thư mục nhật ký JSONL.
            dedup_minutes: Cửa sổ gộp cảnh báo.
        """
        self.path = Path(path)
        self.log_dir = Path(log_dir) if log_dir else None
        self.dedup_minutes = dedup_minutes
        self._jsonl_lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            c.executescript(SPAN_SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        """Mở kết nối ngắn, commit khi thoát êm, rollback khi lỗi.

        Yields:
            Kết nối SQLite với `row_factory` dạng Row.
        """
        c = sqlite3.connect(str(self.path), timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=10000")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ── sự kiện ──────────────────────────────────────────────────────────────
    def emit(self, kind: str, message: str, *, level: str = "info", actor: str = "daemon",
             wave_id: str | None = None, step: str | None = None,
             data: dict[str, Any] | None = None) -> int:
        """Ghi một sự kiện vào `ops_events` và bản sao JSONL theo ngày.

        Args:
            kind: Loại sự kiện, ví dụ `wave.opened`.
            message: Mô tả ngắn bằng tiếng Việt.
            level: Mức độ trong LEVELS.
            actor: Thành phần phát sinh sự kiện.
            wave_id: Mã đợt liên quan.
            step: Bước của đợt.
            data: Dữ liệu kèm theo.

        Returns:
            Mã sự kiện vừa ghi.
        """
        ts = iso()
        message = redact(message) or ""
        data = redact_data(data) if data else None
        payload = json.dumps(data, ensure_ascii=False, default=str) if data else None
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO ops_events(ts, level, actor, wave_id, step, kind, message, data_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ts, level, actor, wave_id, step, kind, message, payload))
            event_id = int(cur.lastrowid)
        if self.log_dir is not None:
            row = {"id": event_id, "ts": ts, "level": level, "actor": actor,
                   "wave_id": wave_id, "step": step, "kind": kind, "message": message,
                   "data": data}
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                with self._jsonl_lock, open(self.log_dir / f"{ts[:10]}.jsonl", "a",
                                            encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            except OSError:
                pass
        return event_id

    def events(self, *, limit: int = 30, wave_id: str | None = None,
               min_level: str | None = None, after_id: int = 0) -> list[sqlite3.Row]:
        """Đọc sự kiện mới nhất, sắp theo thời gian tăng dần.

        Args:
            limit: Số sự kiện tối đa.
            wave_id: Lọc theo đợt.
            min_level: Lọc từ mức độ này trở lên.
            after_id: Chỉ lấy sự kiện có mã lớn hơn.

        Returns:
            Danh sách hàng sự kiện.
        """
        where, params = ["id > ?"], [after_id]
        if wave_id:
            where.append("wave_id = ?")
            params.append(wave_id)
        if min_level in LEVELS:
            where.append("level IN (%s)" % ",".join("?" * len(LEVELS[LEVELS.index(min_level):])))
            params.extend(LEVELS[LEVELS.index(min_level):])
        sql = (f"SELECT * FROM ops_events WHERE {' AND '.join(where)} "
               f"ORDER BY id DESC LIMIT ?")
        with self.conn() as c:
            rows = c.execute(sql, [*params, limit]).fetchall()
        return list(reversed(rows))

    # ── cảnh báo (outbox) ────────────────────────────────────────────────────
    def alert(self, severity: str, text: str, *, dedup_key: str | None = None,
              buttons: list[list[tuple[str, str]]] | None = None) -> int | None:
        """Đưa một cảnh báo vào outbox, gộp với cảnh báo cùng khoá trong cửa sổ.

        Args:
            severity: Một trong `critical`, `error`, `warn`, `info`, `digest`.
            text: Nội dung tin nhắn.
            dedup_key: Khoá gộp. Cùng khoá trong `dedup_minutes` chỉ tăng bộ đếm.
            buttons: Hàng nút dạng [[(nhãn, lệnh), ...], ...].

        Returns:
            Mã cảnh báo mới, hoặc None khi đã gộp vào cảnh báo cũ.
        """
        now = now_vn()
        text = redact(text) or ""
        with self.conn() as c:
            if dedup_key:
                since = iso(now - timedelta(minutes=self.dedup_minutes))
                row = c.execute(
                    "SELECT id FROM ops_alerts WHERE dedup_key = ? AND created_at >= ? "
                    "ORDER BY id DESC LIMIT 1", (dedup_key, since)).fetchone()
                if row:
                    c.execute("UPDATE ops_alerts SET repeats = repeats + 1 WHERE id = ?",
                              (row["id"],))
                    return None
            cur = c.execute(
                "INSERT INTO ops_alerts(created_at, severity, dedup_key, text, buttons_json) "
                "VALUES (?,?,?,?,?)",
                (iso(now), severity, dedup_key, text,
                 json.dumps(buttons, ensure_ascii=False) if buttons else None))
            return int(cur.lastrowid)

    def unsent_alerts(self, limit: int = 20) -> list[sqlite3.Row]:
        """Lấy các cảnh báo chưa gửi, cũ trước.

        Args:
            limit: Số cảnh báo tối đa.

        Returns:
            Danh sách hàng cảnh báo.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_alerts WHERE sent_at IS NULL "
                             "ORDER BY id LIMIT ?", (limit,)).fetchall()

    def mark_alert(self, alert_id: int, *, sent: bool, error: str | None = None) -> None:
        """Ghi kết quả gửi một cảnh báo.

        Args:
            alert_id: Mã cảnh báo.
            sent: True khi đã gửi thành công.
            error: Lỗi gửi, nếu có.
        """
        with self.conn() as c:
            if sent:
                c.execute("UPDATE ops_alerts SET sent_at = ?, attempts = attempts + 1, "
                          "last_error = NULL WHERE id = ?", (iso(), alert_id))
            else:
                c.execute("UPDATE ops_alerts SET attempts = attempts + 1, last_error = ? "
                          "WHERE id = ?", (redact(error), alert_id))

    # ── trạng thái khoá/giá trị ──────────────────────────────────────────────
    def get_state(self, key: str, default: str | None = None) -> str | None:
        """Đọc một giá trị trạng thái.

        Args:
            key: Khoá.
            default: Giá trị trả về khi chưa có.

        Returns:
            Chuỗi giá trị hoặc `default`.
        """
        with self.conn() as c:
            row = c.execute("SELECT value FROM ops_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_state(self, key: str, value: str | None) -> None:
        """Ghi một giá trị trạng thái; None thì xoá khoá.

        Args:
            key: Khoá.
            value: Giá trị chuỗi hoặc None.
        """
        with self.conn() as c:
            if value is None:
                c.execute("DELETE FROM ops_state WHERE key = ?", (key,))
            else:
                c.execute("INSERT INTO ops_state(key, value, updated_at) VALUES (?,?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                          "updated_at = excluded.updated_at", (key, value, iso()))

    # ── đợt ──────────────────────────────────────────────────────────────────
    def upsert_wave(self, wave_id: str, **fields: Any) -> None:
        """Tạo hoặc cập nhật hàng của một đợt.

        Args:
            wave_id: Mã đợt.
            **fields: Các cột cần ghi.
        """
        fields["updated_at"] = iso()
        with self.conn() as c:
            exists = c.execute("SELECT 1 FROM ops_waves WHERE wave_id = ?",
                               (wave_id,)).fetchone()
            if exists:
                sets = ", ".join(f"{k} = ?" for k in fields)
                c.execute(f"UPDATE ops_waves SET {sets} WHERE wave_id = ?",
                          [*fields.values(), wave_id])
            else:
                fields.setdefault("status", "SENSED")
                fields.setdefault("opened_at", iso())
                cols = ", ".join(["wave_id", *fields])
                marks = ", ".join("?" * (len(fields) + 1))
                c.execute(f"INSERT INTO ops_waves({cols}) VALUES ({marks})",
                          [wave_id, *fields.values()])

    def wave(self, wave_id: str) -> sqlite3.Row | None:
        """Đọc hàng của một đợt.

        Args:
            wave_id: Mã đợt.

        Returns:
            Hàng đợt hoặc None.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_waves WHERE wave_id = ?",
                             (wave_id,)).fetchone()

    def waves(self, limit: int = 10) -> list[sqlite3.Row]:
        """Đọc các đợt mới nhất.

        Args:
            limit: Số đợt tối đa.

        Returns:
            Danh sách hàng đợt, mới trước.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_waves ORDER BY opened_at DESC LIMIT ?",
                             (limit,)).fetchall()

    def active_wave(self) -> sqlite3.Row | None:
        """Trả về đợt đang chạy, nếu có.

        Returns:
            Hàng đợt đang ở trạng thái hoạt động, hoặc None.
        """
        marks = ",".join("?" * len(ACTIVE_WAVE_STATUSES))
        with self.conn() as c:
            return c.execute(f"SELECT * FROM ops_waves WHERE status IN ({marks}) "
                             "ORDER BY opened_at DESC LIMIT 1",
                             ACTIVE_WAVE_STATUSES).fetchone()

    def parked_for_breaker(self) -> list[sqlite3.Row]:
        """Liệt kê đợt PARKED đang chờ provider hồi phục.

        Returns:
            Danh sách hàng đợt, cũ trước.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_waves WHERE status = 'PARKED' "
                             "AND resume_on_breaker = 1 ORDER BY opened_at").fetchall()

    # ── giữ chỗ bài theo đợt ─────────────────────────────────────────────────
    def record_wave_articles(self, wave_id: str, article_ids: list[str]) -> int:
        """Ghi tập bài của một đợt và tăng số lần thử của từng bài đúng một lần.

        Gọi lại cho cùng đợt (chạy lại sau crash) không tăng số lần thử lần nữa.

        Args:
            wave_id: Mã đợt.
            article_ids: Định danh bài trong đợt.

        Returns:
            Số bài mới được ghi cho đợt.
        """
        added = 0
        now = iso()
        with self.conn() as c:
            for aid in article_ids:
                cur = c.execute("INSERT OR IGNORE INTO ops_wave_articles(wave_id, article_id) "
                                "VALUES (?,?)", (wave_id, aid))
                if cur.rowcount:
                    added += 1
                    c.execute("INSERT INTO ops_article_attempts(article_id, attempts, "
                              "last_wave, updated_at) VALUES (?,1,?,?) "
                              "ON CONFLICT(article_id) DO UPDATE SET "
                              "attempts = attempts + 1, last_wave = excluded.last_wave, "
                              "updated_at = excluded.updated_at", (aid, wave_id, now))
        return added

    def reserved_article_ids(self) -> set[str]:
        """Liệt kê bài đang thuộc một đợt chưa xong vòng đời (đang chạy, PARKED, FAILED).

        Returns:
            Tập định danh bài không được đóng gói vào đợt khác.
        """
        marks = ",".join("?" * len(RELEASED_WAVE_STATUSES))
        with self.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT a.article_id FROM ops_wave_articles a "
                "JOIN ops_waves w ON w.wave_id = a.wave_id "
                f"WHERE w.status NOT IN ({marks})", RELEASED_WAVE_STATUSES).fetchall()
        return {r[0] for r in rows}

    def exhausted_article_ids(self, max_attempts: int) -> set[str]:
        """Liệt kê bài đã được đóng gói đủ số lần thử tối đa.

        Args:
            max_attempts: Số lần thử tối đa của một bài.

        Returns:
            Tập định danh bài không được tự động thử lại nữa.
        """
        with self.conn() as c:
            rows = c.execute("SELECT article_id FROM ops_article_attempts WHERE attempts >= ?",
                             (int(max_attempts),)).fetchall()
        return {r[0] for r in rows}

    def excluded_article_ids(self, max_attempts: int) -> set[str]:
        """Gộp bài đang giữ chỗ và bài đã hết lượt thử.

        Args:
            max_attempts: Số lần thử tối đa của một bài.

        Returns:
            Tập định danh bài mà sensor và bộ đóng gói phải bỏ qua.
        """
        return self.reserved_article_ids() | self.exhausted_article_ids(max_attempts)

    # ── lệnh từ console ──────────────────────────────────────────────────────
    def enqueue_command(self, text: str, actor: str = "console") -> int:
        """Đưa một lệnh vào hộp thư để daemon xử lý.

        Args:
            text: Lệnh dạng `/pause`.
            actor: Nguồn lệnh.

        Returns:
            Mã lệnh.
        """
        with self.conn() as c:
            cur = c.execute("INSERT INTO ops_commands(created_at, actor, text) VALUES (?,?,?)",
                            (iso(), actor, text))
            return int(cur.lastrowid)

    def pending_commands(self) -> list[sqlite3.Row]:
        """Lấy các lệnh chưa xử lý, cũ trước.

        Returns:
            Danh sách hàng lệnh.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_commands WHERE status = 'pending' "
                             "ORDER BY id").fetchall()

    def finish_command(self, command_id: int, result: str, status: str = "done") -> None:
        """Ghi kết quả xử lý một lệnh.

        Args:
            command_id: Mã lệnh.
            result: Văn bản kết quả.
            status: Trạng thái cuối.
        """
        with self.conn() as c:
            c.execute("UPDATE ops_commands SET status = ?, result = ?, processed_at = ? "
                      "WHERE id = ?", (status, result, iso(), command_id))

    def command(self, command_id: int) -> sqlite3.Row | None:
        """Đọc một lệnh theo mã.

        Args:
            command_id: Mã lệnh.

        Returns:
            Hàng lệnh hoặc None.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_commands WHERE id = ?",
                             (command_id,)).fetchone()
