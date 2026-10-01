"""Gửi cảnh báo qua Telegram từ outbox và ping dead-man healthchecks."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import requests

from src.ops.present import LEVEL_LABEL
from src.ops.redact import redact
from src.ops.store import OpsStore, iso, now_vn

SILENT_SEVERITIES = {"warn", "info", "digest"}
TELEGRAM_LIMIT = 4000


class TelegramClient:
    """Client tối giản cho Telegram Bot API dùng long polling.

    Attributes:
        token: Token của bot.
        base: URL gốc của API.
    """

    def __init__(self, token: str, *, session: requests.Session | None = None) -> None:
        """Tạo client.

        Args:
            token: Token của bot.
            session: Phiên HTTP dùng lại, tiện cho kiểm thử.
        """
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.session = session or requests.Session()

    def _call(self, method: str, payload: dict[str, Any], timeout: float = 20) -> Any:
        try:
            resp = self.session.post(f"{self.base}/{method}", json=payload, timeout=timeout)
        except requests.RequestException as exc:
            # Thông điệp lỗi của requests chứa URL, tức chứa token bot.
            raise RuntimeError(f"Telegram {method}: {type(exc).__name__}: "
                               f"{redact(str(exc))}") from None
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data.get('description', resp.status_code)}")
        return data.get("result")

    def send(self, chat_id: str, text: str, *,
             buttons: list[list[tuple[str, str]]] | None = None,
             silent: bool = False) -> int:
        """Gửi tin nhắn văn bản thuần, kèm nút bấm nếu có.

        Args:
            chat_id: Mã cuộc trò chuyện.
            text: Nội dung, cắt ở 4000 ký tự.
            buttons: Hàng nút [[(nhãn, lệnh), ...]]; lệnh đi vào callback_data.
            silent: Gửi không âm thanh.

        Returns:
            Mã tin nhắn.
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:TELEGRAM_LIMIT],
                                   "disable_notification": silent,
                                   "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": [
                [{"text": label, "callback_data": data[:64]} for label, data in row]
                for row in buttons]}
        return int(self._call("sendMessage", payload)["message_id"])

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        """Lấy cập nhật mới bằng long polling.

        Args:
            offset: Mã cập nhật kế tiếp cần lấy.
            timeout: Số giây giữ kết nối.

        Returns:
            Danh sách cập nhật.
        """
        return self._call("getUpdates", {"offset": offset, "timeout": timeout,
                                         "allowed_updates": ["message", "callback_query"]},
                          timeout=timeout + 10) or []

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        """Xác nhận đã nhận một lượt bấm nút.

        Args:
            callback_id: Mã callback_query.
            text: Thông báo ngắn hiện trên máy người bấm.
        """
        self._call("answerCallbackQuery", {"callback_query_id": callback_id,
                                           "text": text[:200]})


def format_alert(row: Any) -> str:
    """Dựng nội dung tin nhắn cho một cảnh báo.

    Args:
        row: Hàng `ops_alerts`.

    Returns:
        Văn bản tin nhắn.
    """
    sev = row["severity"]
    text = row["text"]
    if sev != "digest" and not text.startswith("["):
        text = f"[{LEVEL_LABEL.get(sev, sev.upper())}] {text}"
    if row["repeats"] and row["repeats"] > 1:
        text += f"\nĐã lặp {row['repeats']} lần trong cửa sổ gộp."
    return text


def drain_alerts(store: OpsStore, client: TelegramClient | None, chat_ids: list[str],
                 *, limit: int = 20, max_age_hours: float = 6) -> tuple[int, int]:
    """Gửi các cảnh báo chưa gửi; lỗi thì giữ lại để lần sau gửi tiếp.

    Cảnh báo cũ hơn `max_age_hours` được đánh dấu hết hạn thay vì gửi, để lần đầu nối
    Telegram hoặc sau một đợt mất mạng dài không xả cả loạt tin đã lỗi thời.

    Args:
        store: Store vận hành.
        client: Client Telegram, None khi chưa cấu hình.
        chat_ids: Danh sách mã cuộc trò chuyện nhận cảnh báo.
        limit: Số cảnh báo tối đa mỗi lượt.
        max_age_hours: Tuổi tối đa của cảnh báo còn được gửi.

    Returns:
        Cặp (số đã gửi, số lỗi).
    """
    if client is None or not chat_ids:
        return 0, 0
    cutoff = iso(now_vn() - timedelta(hours=max_age_hours))
    with store.conn() as c:
        c.execute("UPDATE ops_alerts SET sent_at = ?, last_error = 'expired' "
                  "WHERE sent_at IS NULL AND created_at < ?", (iso(), cutoff))
    sent = failed = 0
    for row in store.unsent_alerts(limit):
        buttons = None
        if row["buttons_json"]:
            buttons = [[tuple(b) for b in r] for r in json.loads(row["buttons_json"])]
        try:
            for chat in chat_ids:
                client.send(chat, format_alert(row), buttons=buttons,
                            silent=row["severity"] in SILENT_SEVERITIES)
        except Exception as exc:  # noqa: BLE001 — mạng chập chờn, giữ trong outbox
            store.mark_alert(row["id"], sent=False, error=str(exc)[:300])
            failed += 1
            break
        store.mark_alert(row["id"], sent=True)
        sent += 1
    return sent, failed


def ping_healthcheck(url: str | None, suffix: str = "", body: str = "",
                     *, session: requests.Session | None = None) -> bool:
    """Ping dead-man ngoài máy; lỗi mạng không làm hỏng daemon.

    Args:
        url: URL ping của healthchecks.io (hoặc Uptime Kuma push).
        suffix: `""`, `/start` hoặc `/fail`.
        body: Nội dung đính kèm, cắt ở 10 KB.
        session: Phiên HTTP dùng lại.

    Returns:
        True khi ping thành công.
    """
    if not url:
        return False
    try:
        resp = (session or requests).post(url.rstrip("/") + suffix,
                                          data=body.encode("utf-8")[:10_000], timeout=10)
        return resp.status_code < 400
    except requests.RequestException:
        return False
