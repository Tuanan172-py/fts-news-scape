# okf/tools — OKF tooling (local-first, Python)

Track OKF độc lập. Không GCP, không Node. Chạy bằng project venv (có PyYAML).

## `okf_check.py` — phát hiện KB lạc hậu / lỗi frontmatter

```bash
# Windows / PowerShell (path có dấu cách → luôn quote)
"project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated          # chỉ stale/warn/parse-error
"project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated --all     # in mọi file
"project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated --json    # xuất JSON (CI)
"project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated --no-git  # fs-mtime thay git commit-time
```

### Cơ chế
- Quét `okf/catalog/**/*.md` (bỏ `index.md`).
- Đọc frontmatter: `sources[].resource` (căn cứ code/doc) + `sources_last_checked` (fallback `generated.at`).
- Ngày đổi mỗi nguồn = **git commit-time** (fallback fs-mtime). So với `sources_last_checked`.
- `resource` top-level (tài sản được mô tả, vd `.db`) **KHÔNG** tính vào staleness — nó đổi mỗi crawl.

### Trạng thái
| status | nghĩa |
|---|---|
| `ok` | nguồn không mới hơn last-checked |
| `stale` | ≥1 nguồn đổi SAU `sources_last_checked` → knowledge-manager cần review + bump ngày |
| `parse-error` | frontmatter YAML hỏng (vd value chứa `: ` chưa quote) |
| `no-source` | không có `sources[]` trỏ file tồn tại (vd metric mô tả bảng, không phải file) |

### Exit code
`0` = sạch · `1` = có `stale` hoặc `parse-error` (dùng làm pre-commit/CI gate ở GĐ2) · `2` = lỗi cấu hình.

### Lưu ý
- Sửa `stale` = con người review nội dung rồi cập nhật `sources_last_checked` (KHÔNG tự động sửa nội dung KB).
- Sửa `parse-error` = quote value frontmatter chứa ký tự đặc biệt, vd `resource: "a/b.db (table: x)"`.
