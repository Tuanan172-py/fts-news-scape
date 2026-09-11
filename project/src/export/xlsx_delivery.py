"""Xuất tệp báo cáo giao hàng định dạng Excel (.xlsx) đơn sắc chuẩn."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

from src.core.staging import safe_atomic_write

SHEET_NAME = "Watchlist News"

# Hợp đồng GIAO HÀNG: (khoá trong row dict, nhãn hiển thị, độ rộng cột, có wrap text).
# Thứ tự theo khối: định vị → phân loại (ngắn, để quét/filter) → nguồn → văn bản dài → kỹ thuật.
DELIVERY_FIELDS: list[tuple[str, str, int, bool]] = [
    ("date",             "Date",               12, False),
    ("matched_entities", "Matched Entities",   20, False),
    ("title",            "Title",              48, True),
    ("sentiment",        "Sentiment",          12, False),
    ("time_sensitivity", "Time Sensitivity",   16, False),
    ("gold_status",      "Gold Status",        14, False),
    ("source_domain",    "Source",             16, False),
    ("summary",          "Summary",            64, True),
    ("key_points",       "Key Points",         64, True),
    ("implication",      "Market Implication", 46, True),
    ("url",              "URL",                38, False),
    ("article_id",       "Article ID",         20, False),
]

# Enum → English label. Raw / unexpected values are preserved as-is.
SENTIMENT_EN = {"positive": "Positive", "negative": "Negative", "neutral": "Neutral"}
TIME_SENSITIVITY_EN = {
    "urgent": "Urgent", "today": "Today", "this_week": "This Week",
    "this_month": "This Month", "archive": "Archive",
}
GOLD_STATUS_EN = {"GOLD": "Full", "L1_ONLY": "Preliminary"}

_EN_MAPS = {
    "sentiment": SENTIMENT_EN,
    "time_sensitivity": TIME_SENSITIVITY_EN,
    "gold_status": GOLD_STATUS_EN,
}
_VN_MAPS = _EN_MAPS  # Backward compatibility alias

_HEADER_FONT = Font(bold=True)
_HEADER_BORDER = Border(bottom=Side(style="thin"))
_HEADER_ALIGN = Alignment(vertical="center", horizontal="left")
_WRAP_ALIGN = Alignment(vertical="top", wrap_text=True)
_PLAIN_ALIGN = Alignment(vertical="top")


def en_label(field: str, value) -> str:
    """Chuyển đổi giá trị enum kỹ thuật sang nhãn tiếng Anh hiển thị.

    Args:
        field: Tên trường cần chuyển đổi.
        value: Giá trị nội bộ cần tra cứu.

    Returns:
        Chuỗi nhãn hiển thị tương ứng hoặc giá trị gốc dạng chuỗi nếu không có trong ánh xạ.
    """
    m = _EN_MAPS.get(field)
    if not m:
        return "" if value is None else str(value)
    return m.get(value, "" if value in (None, "") else str(value))


vn_label = en_label  # Backward compatibility alias


def _set_text(cell, value: str, *, align) -> None:
    """Gán giá trị văn bản thuần vào ô nhằm ngăn chặn injection công thức."""
    cell.value = value
    cell.data_type = "s"
    cell.alignment = align


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def build_workbook(rows: list[dict]) -> Workbook:
    """Xây dựng bảng tính Excel đơn sắc từ danh sách bài viết đã tổng hợp.

    Args:
        rows: Danh sách từ điển dữ liệu bài viết theo các khóa DELIVERY_FIELDS.

    Returns:
        Đối tượng Workbook của openpyxl đã định dạng đầy đủ.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    for col, (_key, label, width, _wrap) in enumerate(DELIVERY_FIELDS, start=1):
        cell = ws.cell(row=1, column=col)
        _set_text(cell, label, align=_HEADER_ALIGN)
        cell.font = _HEADER_FONT
        cell.border = _HEADER_BORDER
        ws.column_dimensions[cell.column_letter].width = width

    for r_i, row in enumerate(rows, start=2):
        for col, (key, _label, _width, wrap) in enumerate(DELIVERY_FIELDS, start=1):
            cell = ws.cell(row=r_i, column=col)
            align = _WRAP_ALIGN if wrap else _PLAIN_ALIGN
            raw = row.get(key, "")

            if key == "date":
                d = _parse_date(raw)
                if d is not None:
                    cell.value = d
                    cell.number_format = "yyyy-mm-dd"
                    cell.alignment = align
                else:
                    _set_text(cell, str(raw or ""), align=align)
                continue

            if key in _EN_MAPS:
                _set_text(cell, en_label(key, raw), align=align)
                continue

            _set_text(cell, "" if raw is None else str(raw), align=align)
            # Link bấm được nhưng KHÔNG dùng style Hyperlink (giữ đơn sắc).
            if key == "url" and str(raw or "").startswith(("http://", "https://")):
                cell.hyperlink = str(raw)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(DELIVERY_FIELDS)).column_letter}{max(ws.max_row, 1)}"
    return wb


def write_delivery_xlsx(path: str | Path, rows: list[dict]) -> tuple[Path, bool]:
    """Ghi bảng dữ liệu ra tệp Excel (.xlsx) qua cơ chế nguyên tử an toàn.

    Args:
        path: Đường dẫn tệp đích cần ghi.
        rows: Danh sách từ điển dữ liệu bài viết.

    Returns:
        Tuple gồm đường dẫn tệp thực tế đã ghi và cờ báo tệp có bị rơi về snapshot khóa hay không.
    """
    wb = build_workbook(rows)
    return safe_atomic_write(Path(path), wb.save, binary=True, fallback_on_lock=True)
