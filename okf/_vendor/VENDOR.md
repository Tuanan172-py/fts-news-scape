# Vendored upstream — pin record

OKF format spec + một số file tham chiếu (reference-only) được vendor từ upstream. Nested `.git` đã bị xóa để loại drift 2 chiều; đây là bản ghi để tái lập.

## Upstream pin
- **Repo:** https://github.com/GoogleCloudPlatform/knowledge-catalog.git
- **Branch:** main
- **Commit (pinned):** `3fcbb9f828c2f23d109c855ee403c3a4c81f3a96`
- **Commit date:** 2026-07-24 09:45:43 -0700
- **Subject:** Update SPEC.md
- **License:** Apache-2.0 (xem `LICENSE.md`)
- **Vendored at:** 2026-08-18

## Nội dung giữ lại (reference-only, KHÔNG chạy runtime)
- `SPEC.md` — Open Knowledge Format v0.2 spec (chuẩn frontmatter/entity ta bám theo).
- `LICENSE.md` — Apache-2.0 của upstream.
- `reference_bits/document.py` — parser markdown+frontmatter (tham khảo khi xây `okftools`).
- `reference_bits/viewer/` — viz Cytoscape (tham khảo cho graph GĐ3).

## Đã loại bỏ khỏi repo (không dùng)
- Toàn bộ nested `.git`, `okf/okf/` (python lib chạy GCP/Gemini), `okf/toolbox/` (TS mdcode/enrichment),
  `okf/samples/`, và boilerplate Google (`README.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`).

## Cập nhật pin
Muốn nâng version: `git clone` upstream ở thư mục ngoài, diff `SPEC.md`, cập nhật commit hash ở trên,
copy lại các file cần. KHÔNG re-introduce nested `.git`.
