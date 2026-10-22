"""Deliver outbox alerts through Telegram and ping the dead-man healthcheck."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import requests

from src.ops.present import LEVEL_LABEL
from src.core.redact import redact
from src.ops.store import OpsStore, iso, now_vn

SILENT_SEVERITIES = {"warn", "info", "digest"}
TELEGRAM_LIMIT = 4000


class TelegramClient:
    """Minimal client for the Telegram Bot API using long polling.

    Attributes:
        token: Bot token.
        base: Base URL of the API.
        session: HTTP session used for requests.
    """

    def __init__(self, token: str, *, session: requests.Session | None = None) -> None:
        """Create the client.

        Args:
            token: Bot token.
            session: Reusable HTTP session, convenient in tests.
        """
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.session = session or requests.Session()

    def _call(self, method: str, payload: dict[str, Any], timeout: float = 20) -> Any:
        try:
            resp = self.session.post(f"{self.base}/{method}", json=payload, timeout=timeout)
        except requests.RequestException as exc:
            # The requests error message contains the URL, which contains the bot token.
            raise RuntimeError(f"Telegram {method}: {type(exc).__name__}: "
                               f"{redact(str(exc))}") from None
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data.get('description', resp.status_code)}")
        return data.get("result")

    def send(self, chat_id: str, text: str, *,
             buttons: list[list[tuple[str, str]]] | None = None,
             silent: bool = False) -> int:
        """Send a plain-text message, with buttons when given.

        Args:
            chat_id: Chat identifier.
            text: Message body, truncated at 4000 characters.
            buttons: Button rows [[(label, command), ...]]; the command goes into callback_data.
            silent: Send without notification sound.

        Returns:
            Message identifier.
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
        """Fetch new updates by long polling.

        Args:
            offset: Identifier of the next update to fetch.
            timeout: Seconds to hold the connection.

        Returns:
            List of updates.
        """
        return self._call("getUpdates", {"offset": offset, "timeout": timeout,
                                         "allowed_updates": ["message", "callback_query"]},
                          timeout=timeout + 10) or []

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        """Acknowledge receipt of a button press.

        Args:
            callback_id: callback_query identifier.
            text: Short notice shown on the device of the user who pressed.
        """
        self._call("answerCallbackQuery", {"callback_query_id": callback_id,
                                           "text": text[:200]})


def format_alert(row: Any) -> str:
    """Build the message text for one alert.

    Args:
        row: `ops_alerts` row.

    Returns:
        Message text.
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
    """Send unsent alerts; on failure keep them for the next attempt.

    An alert older than `max_age_hours` is marked expired instead of sent, so the first
    Telegram connection or a long network outage does not flush a batch of stale messages.

    Args:
        store: Operations store.
        client: Telegram client, None when not configured.
        chat_ids: Chat identifiers that receive alerts.
        limit: Maximum number of alerts per pass.
        max_age_hours: Maximum age of an alert that may still be sent.

    Returns:
        Pair (number sent, number failed).
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
        except Exception as exc:  # noqa: BLE001 — flaky network: keep the alert in the outbox
            store.mark_alert(row["id"], sent=False, error=str(exc)[:300])
            failed += 1
            break
        store.mark_alert(row["id"], sent=True)
        sent += 1
    return sent, failed


def ping_healthcheck(url: str | None, suffix: str = "", body: str = "",
                     *, session: requests.Session | None = None) -> bool:
    """Ping the off-machine dead-man check; a network error does not break the daemon.

    Args:
        url: Ping URL of healthchecks.io (or an Uptime Kuma push).
        suffix: `""`, `/start` or `/fail`.
        body: Attached body, truncated at 10 KB.
        session: Reusable HTTP session.

    Returns:
        True when the ping succeeded.
    """
    if not url:
        return False
    try:
        resp = (session or requests).post(url.rstrip("/") + suffix,
                                          data=body.encode("utf-8")[:10_000], timeout=10)
        return resp.status_code < 400
    except requests.RequestException:
        return False
