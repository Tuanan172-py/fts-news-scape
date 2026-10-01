"""Máy chủ HTTP cục bộ của Phòng điều khiển: các đường JSON chỉ đọc và một trang tĩnh."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from src.ops import improve, present
from src.ops import supervision as sv
from src.ops.breakers import Breakers
from src.ops.config import OpsPaths
from src.ops.store import OpsStore

WEB_DIR = Path(__file__).resolve().parent / "web"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class _Server(ThreadingHTTPServer):
    """Máy chủ không cho hai tiến trình dùng chung một cổng.

    Trên Windows `SO_REUSEADDR` cho phép bind trùng cổng đang nghe, khác với Linux; tắt nó
    thì tiến trình thứ hai nhận lỗi và Phòng điều khiển bỏ qua thay vì tranh cổng.
    """

    allow_reuse_address = False
    daemon_threads = True


class ControlRoom:
    """Phục vụ Phòng điều khiển trên `127.0.0.1`, đọc từ `ops.db`.

    Chỉ nhận yêu cầu có header Host là địa chỉ cục bộ (chống DNS rebinding). Thao tác
    ghi duy nhất là quyết định đề xuất cải tiến, và cần mã thông hành do trang tự nhúng.

    Attributes:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.
        port: Cổng đang nghe sau khi `start`.
        token: Mã thông hành của lần chạy này.
    """

    def __init__(self, store: OpsStore, cfg: dict, paths: OpsPaths, breakers: Breakers, *,
                 port: int | None = None, harness: Callable | None = None) -> None:
        """Dựng máy chủ, chưa lắng nghe.

        Args:
            store: Store vận hành.
            cfg: Cấu hình đầy đủ.
            paths: Đường dẫn vận hành.
            breakers: Breaker theo provider.
            port: Cổng; None lấy từ cấu hình, 0 để hệ điều hành chọn (kiểm thử).
            harness: Hàm gọi harness CLI, thay được trong kiểm thử.
        """
        self.store, self.cfg, self.paths, self.breakers = store, cfg, paths, breakers
        self.port = cfg["control_room"]["port"] if port is None else port
        self.token = secrets.token_urlsafe(24)
        self._harness = harness or improve._harness
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ── điều khiển vòng đời ──────────────────────────────────────────────────
    def start(self) -> bool:
        """Mở cổng và chạy máy chủ ở luồng nền.

        Returns:
            False khi cổng đã bị chiếm; daemon vẫn chạy bình thường.
        """
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a) -> None:  # không ghi log từng yêu cầu
                return

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
                return host in LOCAL_HOSTS

            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj) -> None:
                self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                           "application/json; charset=utf-8")

            def do_GET(self) -> None:  # noqa: N802
                if not self._host_ok():
                    return self._json(403, {"error": "host không hợp lệ"})
                try:
                    code, payload, ctype = app.route_get(urlparse(self.path))
                except Exception as exc:  # noqa: BLE001 — lỗi một đường không làm sập máy chủ
                    return self._json(500, {"error": str(exc)[:200]})
                if ctype == "json":
                    return self._json(code, payload)
                self._send(code, payload, ctype)

            def do_POST(self) -> None:  # noqa: N802
                if not self._host_ok():
                    return self._json(403, {"error": "host không hợp lệ"})
                if self.headers.get("X-CR-Token") != app.token:
                    return self._json(403, {"error": "thiếu mã thông hành"})
                try:
                    code, payload = app.route_post(urlparse(self.path))
                except Exception as exc:  # noqa: BLE001
                    return self._json(500, {"error": str(exc)[:200]})
                self._json(code, payload)

        try:
            self._server = _Server(("127.0.0.1", int(self.port)), Handler)
        except OSError as exc:
            self.store.emit("control_room.bind_failed", f"cổng {self.port}: {exc}", level="warn")
            return False
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name="control-room",
                                        daemon=True)
        self._thread.start()
        self.store.emit("control_room.started", f"Phòng điều khiển tại http://127.0.0.1:{self.port}")
        return True

    def stop(self) -> None:
        """Dừng máy chủ."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # ── định tuyến ───────────────────────────────────────────────────────────
    def route_get(self, url) -> tuple[int, object, str]:
        """Xử lý một yêu cầu GET.

        Args:
            url: Kết quả `urlparse` của đường dẫn.

        Returns:
            Bộ ba (mã HTTP, nội dung, kiểu); kiểu `json` nghĩa là nội dung là đối tượng.
        """
        path, q = url.path.rstrip("/") or "/", parse_qs(url.query)
        if path == "/":
            html = (WEB_DIR / "control_room.html").read_text(encoding="utf-8")
            return 200, html.replace("__CR_TOKEN__", self.token).encode("utf-8"), \
                "text/html; charset=utf-8"
        s, c, p, b = self.store, self.cfg, self.paths, self.breakers
        if path == "/api/labels":
            return 200, present.LABELS, "json"
        if path == "/api/attention":
            return 200, sv.state(s, c, p, b)["attention"], "json"
        if path == "/api/state":
            return 200, sv.state(s, c, p, b), "json"
        if path == "/api/map":
            return 200, sv.build_map(s, c, p, b), "json"
        if path == "/api/waves":
            return 200, sv.waves(s, int(q.get("limit", ["20"])[0])), "json"
        if path.startswith("/api/trace/"):
            return 200, sv.trace_of(s, path.rsplit("/", 1)[1]), "json"
        if path == "/api/agents":
            reg = sv.registry()
            return 200, [{"id": a, "class": v.get("class"), "status": v.get("status"),
                          "skill": sv.Path(str(v.get("skill") or "")).parent.name or None,
                          "model": v.get("model")} for a, v in reg.items()], "json"
        if path.startswith("/api/agent/"):
            card = sv.agent_card(s, path.rsplit("/", 1)[1])
            return (200, card, "json") if card else (404, {"error": "không có tác nhân"}, "json")
        if path == "/api/incidents":
            return 200, sv.incidents(s, b), "json"
        if path == "/api/kpi":
            return 200, {"series": sv.kpi_series(s, 14), "anomalies": sv.anomalies(s)}, "json"
        if path == "/api/improvements":
            return 200, sv.proposals(s), "json"
        return 404, {"error": "không có đường dẫn này"}, "json"

    def route_post(self, url) -> tuple[int, object]:
        """Xử lý một yêu cầu POST (chỉ quyết định đề xuất cải tiến).

        Args:
            url: Kết quả `urlparse` của đường dẫn.

        Returns:
            Cặp (mã HTTP, nội dung).
        """
        parts = url.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "improvements"] and parts[2].isdigit():
            res = improve.decide(self.store, int(parts[2]), parts[3], actor="web",
                                 harness=self._harness)
            return (200 if res["ok"] else 409), res
        return 404, {"error": "không có đường dẫn này"}
