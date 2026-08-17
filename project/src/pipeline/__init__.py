"""
Downstream pipeline (medallion Silver + change-detection) — re-derivable from WORM Bronze.

Tách khỏi hot capture path: các builder ở đây chạy OFFLINE trên Bronze artifact
(`data/raw_html/**`) + DB, KHÔNG chèn vào scraper (giữ bất biến "scraper không ghi DB",
capture nhanh, và re-derive được sau khi sửa parser). Xem docs/design/07,11.
"""
