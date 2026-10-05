# Report 08 — Toàn bộ thay đổi của phiên 2026-09-07 → 09-08

Bản ghi đầy đủ **mọi thứ tôi đã thay đổi**, gồm cả các quyết định sai đã phải sửa lại.
Chi tiết kỹ thuật của riêng đợt mở rộng nguồn ở [report 07](07-implementation-changelog.md);
tài liệu này bao trùm cả phần hạ tầng 2 máy và các đính chính.

Mọi commit đều author = committer = `An Pham Thanh <anpt11172@gmail.com>`, không có trailer
`Co-Authored-By` / `Claude-Session`.

---

## 1. Bảng commit

| # | Commit | Thời điểm | Quy mô | Nội dung |
|---|---|---|---|---|
| 1 | `7bb46ba` | 09-07 23:15 | 55 file, **+10468 / −358** | Mở rộng nguồn Bronze-first: 5 nguồn mới + driver NSO |
| 2 | `75b8b6c` | 09-07 23:25 | 16 file, +731 | Khôi phục `domains/` contract + biên bản rà soát kế hoạch |
| 3 | `8bb4f44` | 09-07 23:59 | 2 file, +223 | Report 07 — changelog implement |
| 4 | `e4d281a` | 09-08 02:56 | 45 file, +2123 / −3066 | **Hợp nhất 2 máy** |
| 5 | `4738f66` | 09-08 03:22 | 2 file, +181 | `docs/dev/07-two-machine-workflow.md` |
| 6 | `8cc1890` | 09-08 04:00 | 11 file, +324 / −12 | Đồng bộ kho tri thức OKF |
| 7 | `6893c3f` | 09-08 04:03 | 1 file, +24 | Bảng "lệnh nào cho máy nào" |
| 8 | `396e591` | 09-08 06:50 | 4 file, +157 | **Sửa lỗi:** khôi phục 4 report bị bỏ track nhầm |
| 9 | `69348cd` | 09-08 06:56 | 1 file, +66 / −31 | **Sửa lỗi:** đính chính giả định về SharePoint |

Commit 1–3 nằm trên lineage cũ, đã bị thay thế khi hợp nhất; **nội dung của chúng nằm trọn
trong `e4d281a`**. Lineage cũ giữ ở tag `archive/machineA-20260908` và trong bundle
`C:\dev\backup\newscape-backup-20260908b.bundle` (17,3 MB, đã verify "complete history",
gồm cả `refs/stash`).

`9c06234` và `359ac20` **không phải của tôi** — luồng B, phiên song song trên cùng máy.

---

## 2. Mở rộng nguồn tin (commit 1–3)

Chi tiết đầy đủ ở [report 07](07-implementation-changelog.md). Tóm tắt:

- Nguồn enabled **3 → 8**; `pytest` **273 → 355 passed**.
- 6 file code mới: `rss_capture.py` (97), `baodautu.py` (202), `periodic_reports.py` (359),
  `fetch_periodic_reports.py` (115), `backfill_deferred.py` (362), `run_periodic_reports.ps1` (41).
- 3 API nền tảng mới: `resolve_source_domain()`, `RawStore.save_binary()`, `_html_from_json()`.
- Bảng DB thứ 11 `periodic_reports`; kho Bronze thứ hai `data/raw_reports/`.
- Xoá `enrich_deferred.py` (mù Bronze, vi phạm WORM).
- 4 chỗ kế hoạch sai so với dữ liệu live, mỗi chỗ có test khoá lại.

---

## 3. Hợp nhất 2 máy — `e4d281a`

### Vấn đề

`git` báo `main` **15 ahead / 11 behind**, merge-base lùi về `89c4ddb` (2026-08-12). Nhưng
so tree hash thì `999061e` ≡ `a11fe7a` — **giống hệt nhau**. Lịch sử bị nhân đôi do một máy
rewrite authorship. Phân kỳ thật chỉ là 5 commit (máy A) vs 1 commit (máy B).

Đo bằng `git merge-tree --write-tree --merge-base=` (in-memory, không đụng working tree):

| Cách | Xung đột |
|---|---|
| `git merge` với base sai `89c4ddb` | **74 file** |
| Base đúng `999061e ≡ a11fe7a` | **17 file** |
| Sau khi máy B import lại bản cũ ở `215de5f` | **42 file** |

### Cách giải

Lấy `origin/main` làm nền, đắp lên các file máy A thắng — **không có conflict marker nào**,
chỉ là `git checkout <nhánh> -- <đường dẫn>` theo bảng quyết định:

| Nhóm | Bên thắng | Bằng chứng quyết định |
|---|---|---|
| `src/`, `scripts/`, `config/domains/`, `tests/`, fixtures | **máy A** | Bản origin còn giữ giả định đã bị bác: `baodautu.py` docstring *"item = div.thumbblock"* (khớp 0 node), TBTC yaml *"NSO đang bị chặn network"* (G1 re-run 12/12 PASS) |
| `domains/*/`, `docs/design/16`, `plan.md`, `phase-01..05`, `research/`, `scout/` | **origin** | Bản gốc đầy đủ hơn: `domains/tnck/schema.yaml` **245 vs 78** dòng, zone map đủ 1..45 |
| Luồng B: `src/agent/*`, `l1_backlog`, `SESSION-LATEST`, `TEST_MATRIX`, `SKILL.md` | **máy A** | Diff origin chỉ là style churn (đổi nháy, **thêm trailing whitespace**) và **xoá 48 dòng** mục 5 *Consolidated Batch Mode* |
| `daily_reporter.py`, `monitor_daily.py`, `test_daily_reporter.py`, `reports/01–04` | **origin** | 3 file luồng B từng mất + 4 report gốc — lấy lại được |

### Kết quả

- `pytest` **357 passed, 0 failed** (355 + 2 của `test_daily_reporter`)
- Audit 99 bất biến: **96/99 PASS**, đúng 3 FAIL giả cũ (Bronze domain cũ bị OneDrive dehydrate, `0 sai hash`)
- `plans/20260907-0834-market-sources-expansion/` **đủ bộ**: 5 phase + 3 research + 1 scout + reports 01→08

### Dọn dẹp trong commit này

- Xoá `enrich_deferred.py` (origin đã thêm lại)
- Bỏ track `daily_log.txt` (1795 dòng log runtime)
- ~~Bỏ track `project/data/reports/`~~ ← **SAI, đã hoàn tác ở `396e591`** (xem §7)
- Thêm `.gitattributes`

---

## 4. Tài liệu quy trình 2 máy — `4738f66`, `6893c3f`, `69348cd`

`project/docs/dev/07-two-machine-workflow.md` (~200 dòng), indexed trong `docs/README.md`.

Nội dung: 4 kiểu hỏng đã gặp kèm cơ chế · vai trò 2 máy · bảng "lệnh nào cho máy nào" ·
cái gì ở lại SharePoint / cái gì ra ngoài · ranh giới sở hữu file · nhịp làm việc và 5 điều
cấm · trao đổi dữ liệu · cổng chất lượng · checklist di chuyển · bảng tra 7 sự cố.

Bảng ranh giới sở hữu có số liệu chống lưng: trong 153 file máy A đổi và 56 file máy B đổi,
file **duy nhất** cả hai cùng đụng là `src/db/store.py` — và nó tự merge sạch.

---

## 5. Đồng bộ kho tri thức OKF — `8cc1890`

Trước commit này, grep `okf/` + `.agents/` + `AGENTS.md` + `docs/SESSION-LATEST.md`:

| Khái niệm | File nhắc tới (trước) |
|---|---|
| `rss_capture`, `baodautu`, `vietnambiz`, `tnck`, `fireant`, `thoibaotaichinhvietnam` | 2–8 ✅ |
| `periodic_reports`, `raw_reports`, `save_binary`, `resolve_source_domain`, `backfill_deferred` | **0** |

Toàn bộ nhánh NSO và 3 API nền tảng vô hình với agent. OKF còn nói sai: "7/24 domain đang
bật", "10 bảng", `src/pipeline/` "8 file".

**3 concept mới:** `tables/periodic_reports.md`, `datasets/bronze_periodic_reports.md`,
`pipelines/periodic_reports.md`.
**8 file cập nhật:** `index.md` 7/24→8/24 · `tables/` + `datasets/` index 10→11 bảng ·
`pipelines/index.md` thêm mục "Ngoài chu kỳ" · `domain_sources.md` 7→8 enabled ·
`codebase.md` `src/pipeline/` 8→9 file + bảng 3 API nền tảng · `MAPPING.md` · `log.md`.

Sau commit: `periodic_reports` 9 file · `raw_reports` 5 · `save_binary` 4 ·
`resolve_source_domain` 3 · `backfill_deferred` 2.

---

## 6. Thay đổi NGOÀI repo

| Hạng mục | Vị trí | Lý do |
|---|---|---|
| Skill global | `~/.claude/skills/cloud-sync-git-safety/SKILL.md` (165 dòng) | Nhận diện + sửa hỏng repo do cloud sync; kích hoạt theo chuỗi lỗi nguyên văn và theo đường dẫn repo chứa tên thư mục sync |
| venv máy A | `C:\Users\An Thanh Pham\AppData\Local\venvs\news-scape` | `.venv` cũ trong OneDrive bị máy B đè: `site-packages` còn **2 gói**, `pyvenv.cfg` trỏ `C:\Users\anpt\...anaconda3` |
| Clone máy A | `C:\dev\news-scape` | Máy B chạy `git init --separate-git-dir` = xoá thư mục `.git` trong vùng sync → nguy cơ lan sang máy A |
| Bundle backup | `C:\dev\backup\newscape-backup-20260908b.bundle` | 17,3 MB, "complete history", gồm `refs/stash` + tag `archive/machineA-20260908` |
| Tag | `archive/machineA-20260908` → `359ac20` | Lineage cũ 15 commit, **không push** lên remote để khỏi rác |

---

## 7. Hai chỗ tôi làm sai và đã sửa

### 7.1 Bỏ track `project/data/reports/` — sửa ở `396e591`

**Sai:** trong `e4d281a` tôi xếp `project/data/reports/` là "output chạy máy" và bỏ track.

**Hậu quả thật:** khi máy B `git pull`, git **xoá 4 file khỏi working tree** của B —
`cafef-2026-08-03.md`, `tnck-2026-09-07.md`, `vietnambiz-2026-09-07.md`,
`vietstock-2026-08-03.md`. Thư mục đó đồng bộ lên SharePoint, nên khi bật sync lại thì lệnh
xoá lan sang bản người khác đọc.

**Đã sửa:** khôi phục nguyên trạng 4 file. `project/daily_log.txt` vẫn để bỏ track — chờ
quyết định của chủ dự án.

### 7.2 Giả định "OneDrive chỉ là backup" — sửa ở `69348cd`

**Sai:** tôi suy ra thư mục OneDrive của máy B chỉ phục vụ 2 máy, rồi **viết suy đoán đó
vào tài liệu như một sự kiện** (§1: *"OneDrive chỉ là backup file"*) và thiết kế cả quy
trình quanh việc gỡ bỏ nó — gồm bước xoá `project\data`.

**Thực tế:** thư mục đó đồng bộ lên SharePoint và **người dùng khác review trực tiếp ở đó**.
Xoá local là xoá của họ (vào Recycle Bin ~93 ngày rồi mất hẳn).

**Đã sửa:** viết lại §2 theo hướng phân loại thay vì "đẩy hết ra ngoài":

| Ở LẠI SharePoint | RA NGOÀI |
|---|---|
| working tree, `data/raw_html`, `silver`, `work_packages`, `reports/daily`, `users/**` | `.git`, `.venv`, `monocle.db` |
| vì người khác review | vì sync 2 chiều **phá hỏng** chúng |

Bỏ hoàn toàn bước xoá. Thêm 2 điều cấm mới. Ghi lại vụ 7.1 làm tiền lệ.

**Bài học:** không suy đoán mục đích của một thư mục rồi thiết kế quanh việc loại bỏ nó —
phải hỏi ai đang đọc nó.

### 7.3 Đính chính sự thật kỹ thuật

`MONOCLE_DATA_DIR` / `MONOCLE_DB_PATH` **chỉ đổi đường dẫn database** — `config.py:58-64`
cho thấy cả hai chỉ ghi vào `cfg["database"]["path"]`. Chúng **không** di dời `raw_html/`,
`silver/`, `work_packages/`, `reports/`. Tôi đã nói sai điều này trước đó.

Hệ quả tốt: trạng thái hiện tại của máy B **đã đúng ý** mà không cần làm thêm — DB ra ngoài,
mọi thứ người dùng review vẫn ở SharePoint. `robocopy` cả `project\data` là thừa (chỉ cần
copy file `.db`); `MONOCLE_DATA_DIR` cũng thừa.

---

## 8. Trạng thái cuối

| | |
|---|---|
| `origin/main` | `69348cd` |
| Máy A | `C:\dev\news-scape` — `pytest` **357 passed**, `pull.rebase=true`, upstream đã gắn |
| Máy B | `.git` → `C:\gitdirs\news-scape.git` · `monocle.db` → `C:\data\news-scape` · working tree + `data/` giữ nguyên trên SharePoint |
| Nguồn enabled | **8** — cafef, vietstock, vneconomy, vietnambiz, thoibaotaichinhvietnam, tnck, baodautu, fireant |
| Audit bất biến | **96/99 PASS** (3 FAIL giả — dehydrate, `0 sai hash`) |

### Việc còn mở

| # | Việc | Ai |
|---|---|---|
| 1 | **3.625 file Silver/work_package/agent_task (269 MB toàn văn bài báo) đang công khai trên GitHub public** — commit `4e1d02e`, có trước phiên này. Ba mức xử lý: đổi repo sang private / `git rm --cached` / `filter-repo` | owner |
| 2 | Máy A bỏ chọn thư mục trong OneDrive (GUI) — chặn việc máy B bật sync, vì `.git` của A là **thư mục** còn của B đã thành **file** | owner |
| 3 | Máy B: dựng venv (`py -0p` để chọn interpreter — máy B không có 3.14), `git pull` lấy `396e591`, `git config pull.rebase true` | owner |
| 4 | `project/daily_log.txt` — giữ bỏ track hay khôi phục? | owner |
| 5 | ToS FireAnt — robots chặn ClaudeBot/GPTBot + `ai-train=no` | owner |
| 6 | Gắn lịch `run_periodic_reports.ps1` sau khi `--dry-run` từ máy deploy | owner |
| 7 | `verify_quality` cho `min_body` theo domain (tnck 92.1% do bố cáo ĐHCĐ ~116 ký tự — ngắn **hợp lệ**) | owner |
| 8 | `C:\gitdirs\news-scape.git` không còn được OneDrive che — cân nhắc backup riêng | owner |
