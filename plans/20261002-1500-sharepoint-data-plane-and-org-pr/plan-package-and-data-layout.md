# Kế hoạch thực thi: đưa news-scape vào fpa-toolkit dạng gói `packages/news_scape/` và tổ chức lại dữ liệu

- **Ngày lập:** 2026-10-02
- **Trạng thái:** Kế hoạch. Chưa sửa mã.
- **Thay thế:** Phần B của [`plan.md`](plan.md) (chuỗi PR B4). Phần A của `plan.md` (SharePoint A3) để sau, chưa làm ở bước này.
- **Phân loại:** Cấp 3. Đổi đường dẫn dữ liệu, đổi ngôn ngữ toàn bộ mã, xin một ngoại lệ với quy chuẩn của tổ chức.

---

## 1. Quyết định đã chốt (người dùng, 2026-10-02)

| Mã | Quyết định | Hệ quả kỹ thuật |
| --- | --- | --- |
| P1 | Đặt mã ở `packages/news_scape/` (GLB-DEC-068) | Gói tự chứa: `pyproject.toml` riêng, test riêng. Không được import `admin`, `ffa`, `fqs`, `fta`, `shared`. Đường dẫn lấy từ `.env`. |
| P2 | Dịch hết sang tiếng Anh, giữ prompt LLM bằng tiếng Việt | Docstring, comment, log, thông điệp CLI, ngoại lệ và tài liệu dùng tiếng Anh. Có hai ngoại lệ tiếng Việt, cả hai được gom vào thư mục riêng: (a) prompt gửi mô hình, (b) chuỗi giao cho người dùng cuối như tiêu đề cột Excel và template đăng ký. Căn cứ là GLB-DEC-047 (deliverable tiếng Việt). |
| P3 | news-scape là nguồn gốc, đồng bộ định kỳ sang monorepo | Phần dịch phải làm **trong news-scape**, nếu không mỗi lần đồng bộ lại phải dịch lại. Monorepo nhận bản xuất tất định từ một script, không ai sửa tay `packages/news_scape/`. |
| P4 | Chỉ đưa mã sản phẩm | Harness, `.agents/`, `docs/HARNESS*`, `harness_cli`, preset DSH, `plans/` và `docs/stories/` ở lại news-scape. |

**Điểm vướng với quy chuẩn tổ chức:** bất biến số 1 của GLB-DEC-068 coi monorepo là nguồn chân lý. P3 đi ngược điều đó. PR phải kèm một ADR xin mô hình "gói vệ tinh có nguồn ở thượng nguồn", trong đó cam kết ba điều:
- Không sửa tay trong monorepo.
- Mỗi lần đồng bộ là một PR có tag phiên bản.
- Script xuất kiểm tra xem bản trong monorepo có bị sửa ngoài luồng không.

Reviewer có thể không chấp nhận. Khi đó phương án dự phòng là chuyển P3 sang "monorepo là gốc" sau lần đồng bộ đầu tiên. Bước S1–S3 vẫn có giá trị trong cả hai trường hợp.

---

## 2. Số đo khối lượng (2026-10-02)

| Hạng mục | Số đo |
| --- | --- |
| Python `src/` | 121 tệp, 23.859 dòng, 4.060 dòng có tiếng Việt, 307 lệnh `import src.` |
| Python `scripts/` | 65 tệp, 12.317 dòng, 2.393 dòng tiếng Việt, 274 lệnh `import src.`, 64 chỗ chỉnh `sys.path` |
| Python `tests/` | 81 tệp, 13.548 dòng, 1.659 dòng tiếng Việt, 326 lệnh `import src.`, 43 chỗ chỉnh `sys.path` |
| Tài liệu `project/docs/` | 62 tệp, 7.798 dòng, gần như toàn tiếng Việt |
| Tệp mã chứa đường dẫn tuyệt đối hoặc OneDrive | 26 |
| Tệp sản phẩm nhắc tên nhà cung cấp AI (bị hook GLB-DEC-069 để ý) | 3 (`fireant.yaml`, `agent-instructions-v1.md`, `classifier.py`) |
| Test ghi vào DB vận hành thật | Có, ví dụ `tests/test_cli_entrypoints.py:56`. Đã ghi nhận trong kiểm toán 24/09, chưa sửa. |
| Mã chết của lane L1/Gold (ADR 0010) | `l1_route.py`, `agent_export.py`, `process_l1_pipeline.py`, `maintenance/route_today_l1.py` và các tệp khác trong danh mục 3.1 của plan kiểm toán 24/09 |

---

## 3. Tổ chức dữ liệu

### 3.1 Nguyên tắc

1. **Mã không biết dữ liệu nằm ở đâu.** Mọi đường dẫn đi qua một mô-đun `paths.py` duy nhất, đọc từ biến môi trường. Thiếu biến thì dừng ngay và báo rõ, không có giá trị mặc định trỏ vào OneDrive hay vào kho mã.
2. **Git chỉ giữ thứ người viết tay và nhỏ:** cấu hình nguồn, alias thực thể, lược đồ, prompt. Thứ sinh ra từ máy hoặc gắn với người cụ thể không vào Git.
3. **Một nơi ghi cho mỗi loại dữ liệu.** DB đang ghi chỉ nằm trên ổ cục bộ của máy vận hành.
4. **Danh tính người dùng theo tài khoản tổ chức** (`anpt`, `phohg`...) khớp `personnel_roster`, không theo tên hiển thị tự đặt (`AnPT`, `PhoHG`).

### 3.2 Biến môi trường

| Biến | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `NEWS_SCAPE_DATA_DIR` | Gốc dữ liệu vận hành, trên ổ cục bộ, ngoài OneDrive | `C:\data\news-scape` |
| `NEWS_SCAPE_USERS_DIR` | Gốc dữ liệu người dùng (đăng ký vào, tệp giao ra) | thư mục SharePoint có phân quyền, xem D-2 |
| `FRA_DATA_ROOT` | Dữ liệu chung của khối, biến đã có sẵn trong fpa-toolkit | `<OneDrive>\fpa-toolkit-junctions\sharepoint\FRA - Data` |
| `NEWS_SCAPE_SECRETS` | Chỉ là tên mục trong Windows Credential Manager, không phải đường dẫn | Token Telegram, khoá API LLM |

### 3.3 Bảng phân loại toàn bộ dữ liệu

| Lớp | Hiện nằm ở | Nơi mới | Git | Ghi chú |
| --- | --- | --- | --- | --- |
| **Cấu hình nguồn tin** `config/domains/*.yaml`, `settings.yaml`, `ops.yaml`, `token_pricing.yaml` | `project/config/` | `packages/news_scape/src/news_scape/resources/config/` | Có | Bỏ đường dẫn tuyệt đối (`settings.yaml` đang ghi cứng `C:/data/...`). |
| **Lược đồ** `schemas/*.json`, `*.md` | `project/schemas/` | `resources/schemas/` | Có | |
| **Prompt LLM** (nguồn của `ARTICLE_SYSTEM_CORE`) | `project/data/prefix/` | `resources/prompts_vi/` | Có | Ngoại lệ tiếng Việt P2. Bản prefix đã ghép danh mục thực thể là dữ liệu sinh ra, chuyển xuống `$DATA/reference/`. |
| **Alias thực thể viết tay** `config/entities/aliases/*.yaml`, `brand_aliases.yaml`, `_context_guards.yaml` | `project/config/entities/` | `resources/entities/` | Có | Nhỏ, có người duyệt. Nhóm FFA review theo Epic 3. |
| **Nguồn thực thể** (`company_name.xlsx`, `etf_name.xlsx`, `market_caps.parquet`, `os.xlsx`, `indices.parquet`, `industry_classification.xlsx`) | `FRA - Data` (đang dò qua ba đường dẫn ghi cứng) | `$FRA_DATA_ROOT/{company_data,trading_data,industry_classification}` | Không | Giữ nguyên chỗ, chỉ đổi cách tìm sang biến môi trường. |
| **Danh mục thực thể sinh ra** `entities.json` (1 MB), `entities_archive.json`, `entities.csv`, `entities.xlsx`, `taxonomy.json` | `project/data/entities/` (đang được Git theo dõi) | `$DATA/reference/entities/` | Không | `build_entities.py` sinh lại được. 1 MB vượt trần 500 KB của monorepo. Bước sau: phát hành bản Parquet ra `$FRA_DATA_ROOT/news/reference/`. |
| **Từ điển nhỏ** `lexicon/*.tsv` | `project/data/lexicon/` | `resources/lexicon/` | Có | Dưới 5 KB, viết tay. |
| **Bộ nhãn đánh giá** `labeled/sentiment_validation.csv` | `project/data/labeled/` | `$DATA/reference/labeled/` | Không | Hook chặn `.csv`. Test dùng bộ nhãn tổng hợp nhỏ sinh trong `tmp_path`. |
| **DB vận hành** `monocle.db`, `ops.db`, `ops_dbos.db` | `C:\data\news-scape\` | `$DATA/db/` | Không | Thêm `*.db*` vào `.gitignore` của gói, vì gốc monorepo không chặn đuôi `.db`. |
| **DB cũ và bản sao lưu** (7 tệp ở `C:\data`, 5 tệp trong OneDrive, `project/src/data/monocle.db`) | rải rác | `$DATA/legacy/` kèm `MANIFEST.json` (SHA-256, nguồn gốc) | Không | Chỉ chuyển, không xoá. `project/src/data` chứa Bronze duy nhất của 237 bài. |
| **Bronze** `raw_html` + `.meta.json` | `C:\data\news-scape\raw_html`, `project/data/raw_html` (25.481 tệp trong OneDrive), `project/src/data/raw_html` | `$DATA/bronze/` | Không | Gộp ba nơi về một, đối chiếu SHA-256 trước khi gỡ bản trong OneDrive. |
| **Silver, packet, đầu ra agent, work package** | `project/data/{silver,agent_tasks,agent_outputs*,work_packages}` | `$DATA/work/` | Không | Sinh lại được. Gỡ 2.826 tệp đang được Git theo dõi. |
| **Báo cáo hằng ngày** `data/reports/` | `project/data/reports/` | `$DATA/reports/` | Không | |
| **Đăng ký người dùng** `users/subscriptions/*.xlsx`, `manifest.yaml` | `users/` trong kho | `$NEWS_SCAPE_USERS_DIR/<tài khoản>/subscription.xlsx`, `$NEWS_SCAPE_USERS_DIR/_registry.yaml` | Không | Gắn tên người nên không vào Git (ADM-DEC-002). Template trống `_template_news.xlsx` sinh bằng `make_user_template.py`, không commit. |
| **Cấu hình người dùng sinh ra** `config/entities/users/*.yaml` | `project/config/` (Git) | `$DATA/users_compiled/` | Không | Sinh từ đăng ký. |
| **Tệp giao người dùng** `users/output/<user>/<ngày>.xlsx` | `users/output/` | `$NEWS_SCAPE_USERS_DIR/<tài khoản>/output/` | Không | |
| **Bí mật** token Telegram, khoá API, chat ID | `.env`, `openrouter/.env` | Windows Credential Manager. `.env.example` chỉ còn tên biến. | Không | `.env.example` hiện chứa một chat ID thật, phải xoá. |
| **Harness, nhật ký phiên** `harness.db`, `logs/` | gốc kho | Ở lại news-scape | Không | P4. |

### 3.4 Cây thư mục dữ liệu đích

```
$NEWS_SCAPE_DATA_DIR/            (C:\data\news-scape, ổ cục bộ, máy vận hành)
├── db/            monocle.db, ops.db, ops_dbos.db
├── bronze/        raw_html/<nguồn>/<ngày>/..., *.meta.json   (bất biến)
├── work/          silver/, agent_tasks/, agent_outputs/, work_packages/
├── reference/     entities/, labeled/, article_prefix/
├── users_compiled/
├── reports/
└── legacy/        bản DB và sao lưu cũ + MANIFEST.json

$NEWS_SCAPE_USERS_DIR/           (SharePoint, mỗi người chỉ thấy thư mục của mình)
├── _registry.yaml               bật/tắt theo tài khoản (thay manifest.yaml)
└── <tài khoản>/subscription.xlsx, output/<ngày>.xlsx
```

---

## 4. Cơ chế đồng bộ news-scape sang fpa-toolkit

```
news-scape (nguồn, nhánh main, tag vX.Y.Z)
   │  python scripts/monorepo_export.py --target <worktree fpa-toolkit> --version vX.Y.Z
   ▼
1. Chép theo danh sách trắng: project/src, project/scripts (chỉ CLI còn sống), project/config (trừ users),
   project/schemas, resources, project/tests (chỉ test kín).
2. Biến đổi cơ học: src/ thành src/news_scape/, `import src.` thành `import news_scape.`, scripts/ thành news_scape/cli/.
3. Sinh EXPORT_MANIFEST.json gồm SHA-256 từng tệp, commit nguồn và phiên bản.
4. Cổng kiểm tra, đỏ một mục là dừng:
   - không có .db .csv .xlsx .xls .parquet .pkl .ipynb, không tệp nào trên 500 KB
   - không đường dẫn tuyệt đối, không "OneDrive", không bí mật (quét regex)
   - không nhắc tên nhà cung cấp trợ lý AI (GLB-DEC-069)
   - không ký tự tiếng Việt ngoài resources/prompts_vi/ và resources/deliverables_vi/
   - test cô lập AST: không import admin, ffa, fqs, fta, shared
   - pytest của gói chạy trong môi trường sạch Python 3.11, mạng bị chặn bằng conftest
   - bản hiện có trong monorepo khớp EXPORT_MANIFEST lần trước (phát hiện sửa tay)
   ▼
fpa-toolkit worktree ngoài OneDrive (~/fpa-toolkit-worktrees/news-scape), nhánh từ origin/main
   → pre-commit run → commit không dòng ghi danh trợ lý → PR "chore(news-scape): sync to vX.Y.Z"
```

Worktree của fpa-toolkit tạo mới từ `origin/main`. Không dùng bản clone ở `Documents/fpa-toolkit`, vì nhánh `main` ở đó đang lệch 194 commit so với remote.

---

## 5. Các bước thực hiện

| Bước | Ở đâu | Việc | Điều kiện xong |
| --- | --- | --- | --- |
| **S0 Nền an toàn** | news-scape | (a) Commit hoặc tạm gác phần thay đổi chưa commit của nhánh `feature/article-lane-remove-gates` (US-033). (b) Fixture autouse đặt DB vào `tmp_path`, `--dry-run` mở DB chỉ đọc. Lấy từ S0 của plan kiểm toán 24/09. (c) Conftest chặn mạng. | `pytest tests/` 100% PASS, không test nào mở `C:\data\…`, không test nào gọi mạng. |
| **S1 Đường dẫn và dữ liệu** | news-scape | `paths.py` với ba biến môi trường. Thay 26 tệp có đường dẫn ghi cứng và mọi chỗ `PROJECT_ROOT / "data"`. Chép dữ liệu sang cây ở §3.4, đối chiếu số tệp và SHA-256, chưa xoá bản gốc. Đổi định danh người dùng sang tài khoản. Gỡ 2.826 tệp khỏi chỉ mục Git. Chuyển chỉ mục Git của dữ liệu thực thể và người dùng ra ngoài. | Daemon chạy một vòng đầy đủ trên cây mới. `pipeline_radar.py status` xanh. Kho mã không còn tệp dữ liệu nào được theo dõi. |
| **S2 Dọn mã chết** | news-scape | Xoá lane L1/Gold đã ngừng theo danh mục 3.1 của plan kiểm toán 24/09 đã qua phản biện. | Test PASS, radar xanh. |
| **S3 Chuyển tiếng Anh** | news-scape | Dịch theo cụm: core, db, scrapers, pipeline, agent, ops, export, cli, tests, docs. Chuỗi giao người dùng gom vào `deliverables_vi`. Prompt chuyển vào `prompts_vi`. Sửa rule 06 sang docstring tiếng Anh. Mỗi cụm một commit. | `ast.parse` và pytest PASS sau mỗi cụm. Cổng "không tiếng Việt ngoài thư mục ngoại lệ" xanh. |
| **S4 Script xuất và khung gói** | news-scape | `scripts/monorepo_export.py` cùng các cổng ở §4. Mẫu `pyproject.toml`, `README.md`, `AGENTS.md`, `.gitignore`, `.agents/skills.json`, `test_satellite_isolation.py` theo `ge_document_migration`. | Xuất ra thư mục tạm, mọi cổng xanh, pytest của gói PASS trong venv sạch. |
| **S5a PR hạ tầng** | fpa-toolkit | `wrapup_runner` tự tìm `packages/*/tests` thay cho tên `ge_document_migration` ghi cứng. Thêm `*.db`, `*.db-wal`, `*.db-shm` vào `.gitignore` gốc. | PR nhỏ, có test. |
| **S5b PR quyết định** | fpa-toolkit | ADR mới: gói vệ tinh có nguồn thượng nguồn, ranh giới dữ liệu §3, biến môi trường §3.2. Sửa phạm vi Epic 3 (`shared/news/` thành `packages/news_scape/`). Thêm dòng vào `.env.example`. Thêm context "news" vào `CONTEXT-MAP.md`. | `check-frontmatter-quality`, `test_docs_integrity.py` PASS. |
| **S5c PR mã** | fpa-toolkit | Bản xuất v1.0.0, chia commit theo ranh giới: khung gói, core+db, scrapers, pipeline, ops, export, cli, tests. Mô tả PR có bản đồ kiến trúc và EXPORT_MANIFEST. | `pre-commit run --all-files`, pytest gói, `wrapup_runner` exit 0. Reviewer duyệt. |
| **S6 Đồng bộ định kỳ** | cả hai | Mỗi tag phát hành của news-scape sinh một PR đồng bộ. Mục nhật ký Tầng 1 theo GLB-DEC-062. | |

S5a và S5b có thể mở song song với S1–S3, vì không phụ thuộc mã.

---

## 6. Rủi ro

| Rủi ro | Biện pháp |
| --- | --- |
| Reviewer từ chối mô hình "nguồn ở thượng nguồn" | Hỏi ở S5b trước khi làm S5c. Phương án dự phòng: chuyển gốc sang monorepo sau lần đồng bộ đầu. |
| Dịch làm gãy hành vi (chuỗi được so khớp, khoá log, tên cột) | Dịch theo cụm, test sau mỗi cụm. Chuỗi được mã so khớp gom thành hằng số trước khi dịch. |
| Đổi đường dẫn khi daemon đang chạy | Làm S1 trong cửa sổ dừng daemon (`ops_daemon.py` về L0), chép trước rồi mới chuyển biến môi trường. |
| PR mã quá lớn để review | Chia commit theo ranh giới. Bản xuất tất định có manifest để reviewer chỉ cần đọc mã, không phải kiểm tra tệp lạ. |
| Đụng phần thay đổi chưa commit (US-033) | S0(a) là điều kiện tiên quyết. Đợt dịch không bắt đầu khi cây làm việc còn bẩn. |

---

## 7. Quyết định còn treo

| # | Câu hỏi | Đề xuất |
| --- | --- | --- |
| D-1 | Phần thay đổi chưa commit trên nhánh `feature/article-lane-remove-gates` (US-033 cụm hoá trùng lặp, ~30 tệp sửa, ~25 tệp mới): commit hay gác lại? | Commit thành story US-033 sau khi chạy test của phần đó. |
| D-2 | Đặt `NEWS_SCAPE_USERS_DIR` ở thư viện SharePoint nào, ai quản trị quyền theo thư mục người dùng | Một thư viện riêng trên site FRA, mỗi thư mục con cấp quyền cho đúng người đó và người vận hành. |
| D-3 | Phiên bản đầu tiên đồng bộ sang monorepo | `v1.0.0` sau S4 |
