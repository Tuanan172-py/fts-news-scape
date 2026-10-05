"""Phân trang theo watermark: đọc tiếp tới khi gặp trang toàn bài đã có trong kho."""

from __future__ import annotations

from typing import Callable

DEFAULT_MAX_PAGES = 8


def paginate_until_known(
    fetch_page: Callable[[int], list[dict] | None],
    key_of: Callable[[dict], str],
    known: Callable[[list[str]], set[str]],
    *,
    min_pages: int = 1,
    max_pages: int = DEFAULT_MAX_PAGES,
    errors: list[str] | None = None,
    label: str = "",
) -> list[dict]:
    """Đọc từng trang listing cho tới khi cả trang đều đã ở trạng thái captured.

    Args:
        fetch_page: Hàm nhận số trang (từ 1), trả danh sách mục, rỗng khi hết trang, None khi lỗi.
        key_of: Hàm trả khoá bài của một mục, dùng để tra sổ phát hiện.
        known: Hàm nhận danh sách khoá và trả tập khoá đã captured.
        min_pages: Số trang tối thiểu luôn đọc, kể cả khi trang đầu toàn bài đã biết.
        max_pages: Trần an toàn số trang mỗi lượt.
        errors: Danh sách lỗi của scraper; hàm ghi thêm khi lỗi trang hoặc chạm trần.
        label: Nhãn nguồn hoặc chuyên mục để ghi vào thông điệp lỗi.

    Returns:
        Các mục đã đọc, theo thứ tự trang.
    """
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        items = fetch_page(page)
        if items is None:
            if errors is not None:
                errors.append(f"{label}: tải trang {page} lỗi, dừng phân trang")
            return out
        if not items:
            return out
        out.extend(items)
        if page >= min_pages:
            keys = [k for k in (key_of(i) for i in items) if k]
            if keys and set(keys) <= known(keys):
                return out
    if errors is not None:
        errors.append(f"{label}: chạm trần {max_pages} trang mà chưa gặp bài đã biết")
    return out
