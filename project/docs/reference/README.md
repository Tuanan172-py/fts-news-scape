# docs/reference — Bản annotated (CHÚ THÍCH) cho artifact capture

> ⚠️ Đây là **bản SAO có chú thích để tra cứu**, KHÔNG phải file dữ liệu thật.
> File thật (`data/raw_html/**`) phải giữ bất biến — xem lý do bên dưới.

| File | Chú thích cho | Cú pháp comment |
|------|---------------|-----------------|
| [`meta-schema.annotated.jsonc`](meta-schema.annotated.jsonc) | `<hash>.meta.json` — 14 trường metadata (2 ví dụ: ok + failed) | `//` (JSONC) |
| [`raw-html.annotated.html`](raw-html.annotated.html) | `<hash>.html` — cấu trúc raw + bất biến no-clean | `<!-- -->` (HTML) |

## Vì sao KHÔNG chèn chú thích vào file thật

1. **`.html` raw = byte-exact (WORM).** Chèn ký tự nào cũng làm `sha256(file) ≠ content_sha256`
   đã lưu → mọi kiểm tra toàn vẹn báo raw bị giả mạo; guardrail agent verify hash sẽ **từ chối bài**.
   Ngoài ra HTML không có comment `//` (chỉ `<!-- -->`).
2. **`.meta.json` = JSON chuẩn.** JSON không cho `//`; `json.loads()` trong `process_meta()`
   (`src/pipeline/run.py:41`) sẽ ném `JSONDecodeError` → sập Vòng 2 ngay bài đầu.

→ Muốn "đọc file có chú thích": mở 2 file annotated trong thư mục này. Nguồn sinh trường:
`src/crawler/raw_store.py` (`RawStore.save`, dict `cap`).
