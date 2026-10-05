"""Mandate vận hành tự gia hạn có điều kiện (D-A): hệ thống khoẻ thì giữ uỷ quyền, có sự cố thì dừng."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.ops import supervision as sv
from src.ops.config import OpsPaths
from src.ops.order import extend, load_order, save_order
from src.ops.present import alert_card
from src.ops.store import OpsStore, iso, now_vn


def health(store: OpsStore, cfg: dict) -> tuple[bool, list[str]]:
    """Đánh giá điều kiện cho phép tự gia hạn mandate.

    Điều kiện (D-A): không có sự kiện mức đỏ trong 24 giờ, chuỗi đợt sạch đủ dài,
    không có chuỗi đợt hỏng, và không có lượt gọi công cụ trái bất biến Zero-Tool
    trong 7 ngày.

    Args:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.

    Returns:
        Cặp (khoẻ, danh sách lý do không khoẻ).
    """
    a = cfg["autonomy"]
    reasons: list[str] = []
    with store.conn() as c:
        crit = c.execute("SELECT COUNT(*) FROM ops_events WHERE level = 'critical' AND ts >= ?",
                         (iso(now_vn() - timedelta(hours=24)),)).fetchone()[0]
    if crit:
        reasons.append(f"{crit} sự kiện mức đỏ trong 24 giờ")
    clean = int(store.get_state("clean_streak", "0") or 0)
    need = int(a["renew_min_clean_streak"])
    if clean < need:
        reasons.append(f"chuỗi đợt sạch {clean} < {need}")
    if int(store.get_state("fail_streak", "0") or 0) > 0:
        reasons.append("đang có chuỗi đợt hỏng")
    since = iso(now_vn() - timedelta(days=7))
    bad = [r for r in sv._rows(store, "SELECT attrs_json FROM ops_spans WHERE kind = 'agent' "
                                      "AND started_at >= ?", (since,))
           if sv._attrs(r).get("tool_invoked") or sv._attrs(r).get("denied_actions")]
    if bad:
        reasons.append(f"{len(bad)} lô agy gọi công cụ trái Zero-Tool trong 7 ngày")
    return (not reasons), reasons


def maybe_renew(store: OpsStore, cfg: dict, paths: OpsPaths) -> dict | None:
    """Gia hạn mandate khi sắp hết hạn và hệ thống khoẻ; ngược lại báo lý do không gia hạn.

    Mandate đã hết hạn hoặc chưa từng cấp thì không bao giờ tự cấp lại: việc cấp ban đầu
    và cấp lại sau khi hết hạn là hành động của người.

    Args:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.
        paths: Đường dẫn vận hành.

    Returns:
        Từ điển mô tả hành động đã làm, hoặc None khi chưa cần.
    """
    order = load_order(paths.standing_order)
    if not order.exists or order.expired() or order.effective_level() == "L0":
        return None
    try:
        left = (datetime.fromisoformat(order.valid_until).date() - now_vn().date()).days
    except ValueError:
        return None
    if left > int(cfg["autonomy"]["renew_when_days_left"]):
        return None
    ok, reasons = health(store, cfg)
    if ok:
        days = int(cfg["autonomy"]["max_order_days"])
        old = order.valid_until
        order = extend(order, days, days)
        order.created_by = "daemon:auto-renew"
        save_order(paths.standing_order, order)
        store.emit("mandate.renewed", f"Mandate {order.level} gia hạn {old} → {order.valid_until}",
                   actor="daemon", data={"from": old, "to": order.valid_until})
        return {"action": "renewed", "from": old, "to": order.valid_until}
    text = (f"Mandate {order.level} còn {left} ngày và KHÔNG tự gia hạn: " + "; ".join(reasons)
            + ". Xử lý nguyên nhân, hoặc gia hạn tay bằng /order extend.")
    store.emit("mandate.renew_blocked", text, level="warn", actor="daemon", data={"reasons": reasons})
    level = "warn" if left > 2 else "error"
    store.alert(level, alert_card(
        level, f"Mandate {order.level} còn {left} ngày và không tự gia hạn: " + "; ".join(reasons),
        "hết hạn thì daemon về L0 và dừng tự mở đợt",
        "xử lý nguyên nhân trên, hoặc gia hạn tay bằng /order extend 30", "/mandate"),
        dedup_key=f"mandate:blocked:{now_vn().date().isoformat()}")
    return {"action": "blocked", "reasons": reasons, "days_left": left}
