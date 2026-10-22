# 07 — Quy trình 2 máy: máy dev qua GitHub + máy vận hành trên OneDrive

Chốt 2026-09-08, sau khi hợp nhất `e4d281a`. Thay thế mọi thoả thuận miệng trước đó.

## 0. Vì sao có tài liệu này

Trong 2 ngày, repo hỏng **4 kiểu khác nhau**, cùng **một** nguyên nhân: hai máy dùng
chung một thư mục OneDrive đồng bộ hai chiều, trong đó có cả `.git`.

| # | Triệu chứng | Cơ chế |
|---|---|---|
| 1 | File mới biến mất, `ImportError: cannot import name 'baodautu'` | OneDrive xoá file **mới chưa commit** khi hoà giải với snapshot máy kia. File **đã sửa** thì giữ |
| 2 | `main` 15 ahead / 11 behind, merge-base lùi 1 tháng | Một máy rewrite authorship → 2 lineage cùng tree, hash khác |
| 3 | `.venv/site-packages` còn 2 gói; `pyvenv.cfg` trỏ sang `C:\Users\anpt\...anaconda3` | venv của máy kia ghi đè qua sync |
| 4 | `fatal: bad object refs/stash`; `There is no tracking information` | `.git/refs/stash` và `.git/config` của máy A sync sang B, nhưng object thì không |

Điểm chung: **OneDrive không sai — sai là để `.git` trong vùng đồng bộ hai chiều.**
Nó đồng bộ theo file, không hiểu ràng buộc toàn vẹn của git.

## 1. Vai trò hai máy (bất đối xứng — cố ý)

| | **Máy A — dev** | **Máy B (FPA-AnPT) — vận hành** |
|---|---|---|
| Vị trí repo | `C:\dev\news-scape` — **ngoài** OneDrive | working tree **trong** OneDrive |
| Kênh trao đổi | **chỉ GitHub** | GitHub cho mã nguồn; **SharePoint là mặt bằng review** cho người dùng khác |
| Việc chính | phát triển scraper, test, contract, docs | chạy pipeline thật, Bronze, DB, báo cáo ngày |
| Cần `data/` ? | **không** — test dùng fixture, zero-network | **có** — là nguồn sự thật duy nhất |

Phân vai này khớp thực tế đang chạy và **loại bỏ nhu cầu đồng bộ `data/`** giữa hai máy:
A phát triển bằng fixture trong git, B giữ dữ liệu sản xuất.

> ⚠️ **Thư mục OneDrive của máy B KHÔNG phải chỉ là backup.** Nó đồng bộ lên SharePoint và
> **người dùng khác đọc trực tiếp ở đó** — báo cáo ngày, file đăng ký danh mục, kết quả đầu
> ra. Hệ quả bắt buộc nhớ:
>
> - **Không xoá bất cứ thứ gì** trong thư mục đó để "dọn dẹp". Xoá local ⇒ xoá trên
>   SharePoint (vào Recycle Bin ~93 ngày rồi mất hẳn).
> - Mỗi lần **bỏ track** một file trong `project/data/`: `git pull` ở máy B sẽ xoá nó khỏi
>   working tree, và lệnh xoá đó lan lên SharePoint. Đã xảy ra một lần — `e4d281a` bỏ track
>   4 file `data/reports/daily/*.md`, khôi phục ở `396e591`.

## 1b. Lệnh nào chạy trên máy nào

Bảng này tồn tại vì đã có lần hỏi nhầm — mục §2 dưới đây tuy tiêu đề là "máy B" nhưng có
một lệnh dùng cho cả hai.

| Lệnh | Máy A (dev) | Máy B (vận hành) |
|---|---|---|
| `git clone … C:\dev\news-scape` | ✅ | ❌ |
| `git init --separate-git-dir C:\gitdirs\news-scape.git` | ❌ — đã ngoài OneDrive rồi | ✅ |
| `setx MONOCLE_DB_PATH` (chỉ đổi đường dẫn DB) | ❌ | ✅ bắt buộc |
| `python -m venv …` + `pip install -r requirements.txt` | ✅ | ✅ — **mỗi máy một venv riêng, dùng interpreter có sẵn của máy đó** |
| OneDrive → Choose folders → bỏ chọn repo | ✅ | ❌ — B phải giữ để người khác review |
| `attrib -U +P` (Always keep on this device) | ❌ | ✅ |
| Xoá bớt file trong thư mục OneDrive | ❌ | ❌ — **không bao giờ** |

**Thứ tự giữa hai máy:**

1. A: clone ra `C:\dev\news-scape`, `pytest` xanh.
2. A: bỏ chọn thư mục repo trong OneDrive (**không** xoá/đổi tên) — bắt buộc trước bước 4,
   vì `.git` của A là **thư mục** còn của B đã thành **file**, sync hai thứ trùng tên nhưng
   khác loại là ca không có cách hoà giải đúng.
3. B: chạy §2.
4. B: bật lại sync.

Không có bước xoá. Thư mục OneDrive của B giữ nguyên toàn bộ nội dung.

## 2. Máy B: cái gì ở lại SharePoint, cái gì ra ngoài

Nguyên tắc phân loại — **không** phải "đẩy hết ra ngoài cho an toàn":

| | Ở LẠI thư mục OneDrive | RA NGOÀI |
|---|---|---|
| Vì sao | người khác review qua SharePoint | sync 2 chiều **phá hỏng** chúng |
| Gồm | working tree, `project/data/raw_html`, `silver`, `work_packages`, `reports/daily`, `users/**` | `.git`, `.venv`, `monocle.db` |

Chỉ **ba** thứ ra ngoài, và mỗi thứ vì một lý do đã chứng kiến tận mắt:

```cmd
:: 1) .git — sync file-by-file lam hong rang buoc ref<->object
::    (da gap: "bad object refs/stash", ".git/config" mat tracking)
cd "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape"
git init --separate-git-dir C:\gitdirs\news-scape.git
::    -> .git tro thanh 1 FILE chua "gitdir: C:\gitdirs\news-scape.git"

:: 2) monocle.db — SQLite WAL = 3 file (.db/.db-wal/.db-shm) phai nhat quan,
::    sync doc lap tung file trong luc dang ghi => hong DB / conflict copy
mkdir C:\data\news-scape
copy "project\data\monocle.db" "C:\data\news-scape\"
setx MONOCLE_DB_PATH "C:\data\news-scape\monocle.db"

:: 3) venv — chua duong dan tuyet doi, khong the dung chung 2 may
::    (da gap: site-packages con 2 goi, pyvenv.cfg tro sang may kia)
::    Dung interpreter co san tren may nay — xem "py -0p"
"C:\Users\anpt\AppData\Local\anaconda3\python.exe" -m venv C:\venvs\news-scape
C:\venvs\news-scape\Scripts\python -m pip install -r project\requirements.txt pytest
```

> ⚠️ **`MONOCLE_DATA_DIR` / `MONOCLE_DB_PATH` chỉ đổi đường dẫn DATABASE**, không di dời
> `raw_html/`, `silver/`, `work_packages/`, `reports/`. Xem `src/core/config.py:58-64` —
> cả hai biến chỉ ghi vào `cfg["database"]["path"]`. Vậy **đặt `MONOCLE_DB_PATH` là đủ**;
> `MONOCLE_DATA_DIR` thừa, và `robocopy` cả `project\data` cũng thừa (chỉ cần copy file
> `.db`). Bronze/Silver vẫn ở nguyên trong OneDrive để người dùng review — đúng như mong
> muốn.

Thêm: chuột phải thư mục repo → **"Always keep on this device"** (hoặc
`attrib -U +P /s /d "<repo>\*"`). Files On-Demand dehydrate file thành placeholder là
nguyên nhân 3 mục "FAIL" giả trong `reports/06` và lỗi
`git add: read error while indexing ...: Invalid argument`.

Kiểm chứng sau khi set (phải mở **cửa sổ cmd mới** — `setx` không ăn vào cửa sổ cũ):

```cmd
python -c "from src.core.config import load_settings; print(load_settings()['database']['path'])"
```

Kỳ vọng: in ra `C:\data\news-scape\monocle.db`.

## 3. Máy A: rời OneDrive — một cái bẫy chết người

```cmd
git clone https://github.com/Tuanan172-py/fts-news-scape.git C:\dev\news-scape
```

> ⛔ **TUYỆT ĐỐI KHÔNG xoá hoặc đổi tên thư mục OneDrive từ máy A.**
> Thao tác đó sẽ đồng bộ sang máy B và **xoá/đổi tên repo đang chạy của B**.

Cách đúng để máy A thôi giữ bản OneDrive: **OneDrive Settings → Account → Choose folders
→ bỏ chọn** thư mục `FRA_DataIngestion - news-scape`. Bản local trên A biến mất, bản
trên cloud và trên B **nguyên vẹn**.

Sau khi bỏ chọn, máy A không còn bất kỳ đường nào chạm vào file của B ngoài GitHub —
đó là mục tiêu.

## 4. Ranh giới sở hữu file

Đo thật ở lần hợp nhất `e4d281a`: trong 153 file máy A đổi và 56 file máy B đổi, file
**duy nhất** cả hai cùng đụng là `src/db/store.py` — và nó **tự merge sạch**. Giữ ranh
giới dưới đây thì xung đột gần bằng 0.

| Khu vực | Chủ |
|---|---|
| `src/scrapers/`, `src/pipeline/`, `src/crawler/`, `config/domains/`, `domains/`, `tests/` + `tests/fixtures/`, `docs/domains/`, `docs/design/` | **máy A** |
| `src/agent/`, `src/export/`, `src/handoff/`, `src/monitor/`, `src/users/`, `scripts/l1_*`, `scripts/agent_*`, `okf/`, `.agents/`, `docs/stories/`, `users/` | **máy B** |
| `src/db/store.py`, `src/core/config.py`, `src/orchestrator.py`, `src/morninger.py`, `README.md`, `docs/runbook.md` | **chung** — sửa nhỏ, commit riêng, push ngay |

Cần sửa file của bên kia: **đừng sửa thẳng**. Ghi yêu cầu vào `docs/SESSION-LATEST.md`
hoặc mở issue GitHub. Chi phí một dòng ghi chú rẻ hơn một lần giải 42 xung đột.

## 5. Nhịp làm việc

Cấu hình một lần, cả hai máy:

```cmd
git config pull.rebase true          :: khong tao merge commit rac
git config core.autocrlf true        :: kho luu tru la LF (xem .gitattributes)
git config push.default simple
```

Mỗi phiên:

1. **Mở phiên:** `git pull` (đã rebase sẵn nhờ config).
2. **Làm việc trên nhánh ngắn:** `git switch -c feat/<scope>-<mo-ta>`.
3. **Kết phiên:** `pytest -q` xanh → commit → push. **Không để việc chưa commit qua đêm** —
   đó chính xác là thứ đã mất trong sự cố #1.
4. **Gộp vào `main`:** chỉ fast-forward. `main` luôn phải xanh.

Ba điều cấm:

- ⛔ **Không rewrite lịch sử đã push** (rebase/amend/filter-branch trên commit đã lên remote).
  Đó là nguyên nhân sự cố #2.
- ⛔ **Không khôi phục file bằng cách copy giữa hai máy.** Chỉ khôi phục bằng git.
  Copy thủ công đã sinh ra 42 xung đột add/add ở `215de5f`.
- ⛔ **Không xoá, không bỏ track file trong thư mục OneDrive của máy B** mà chưa hỏi — nó
  là mặt bằng review trên SharePoint, xoá local là xoá của người khác.
- ⛔ **Không commit `data/`, `.venv`, `daily_log.txt`, `data/reports/`** — đã có rule
  trong `.gitignore`, đừng `git add -f`.

## 6. Trao đổi dữ liệu (không đi qua git)

- **Máy B là nguồn sự thật** cho `data/raw_html/`, `data/raw_reports/`, `data/silver/`,
  `monocle.db`.
- Bronze/Silver **ở lại thư mục OneDrive của máy B** và đồng bộ lên SharePoint — đó là nơi
  người dùng khác review. Đây là quyết định của chủ dự án, ghi lại 2026-09-08.
- Đánh đổi đã biết và đã chấp nhận: Bronze là HTML bên thứ ba có bản quyền; đưa lên
  SharePoint doanh nghiệp là mở rộng phạm vi lưu trữ so với "chỉ nội bộ máy chạy". Quyền
  truy cập thư mục SharePoint chính là ranh giới phát tán — rà soát quyền chia sẻ định kỳ.
- Máy A cần dữ liệu để audit → xin snapshot **một chiều** (zip hoặc robocopy), không bao
  giờ sync hai chiều.
- Fixture trong `tests/fixtures/` là **hợp đồng dữ liệu** giữa hai máy. Đã chứng minh:
  sau sự cố #1, 4 fixture trang detail được tái tạo **byte-exact từ Bronze**. Mất code
  không mất dữ liệu — miễn là Bronze còn.

## 7. Cổng chất lượng

| Kiểm tra | Chạy ở đâu | Mốc |
|---|---|---|
| `pytest -q` | cả hai — bắt buộc trước push | **357 passed, 0 failed** |
| `python scripts/domain_check.py --report <domain>` | chỉ B (cần data) | — |
| `python scripts/verify_quality.py <host>` | chỉ B | vietnambiz 100% · baodautu 99.1% · TBTC 95.8% · tnck 92.1% |
| `python -m src.morninger --once derive` | chỉ B | Bronze ≡ Silver |

Test suite **zero-network** (dùng `FakeHTTP`) và tự cô lập `raw_dir` qua `monkeypatch.chdir`,
nên chạy được trên máy không có `data/` — kể cả runner CI. Nếu muốn khoá "main luôn xanh"
mà không phụ thuộc trí nhớ, thêm GitHub Actions chạy `pytest` trên mỗi push (chưa bật).

## 8. Checklist di chuyển (làm một lần)

- [ ] Cả hai máy cùng ở `e4d281a`, `git status` sạch ✅ (đã đạt 2026-09-08)
- [ ] B: `git init --separate-git-dir C:\gitdirs\news-scape.git`
- [ ] B: set `MONOCLE_DATA_DIR` + `MONOCLE_DB_PATH`, robocopy `data/`
- [ ] B: venv mới ở `C:\venvs\news-scape`
- [ ] B: "Always keep on this device" cho thư mục repo
- [ ] B: `pytest -q` → 357
- [ ] A: `git clone` về `C:\dev\news-scape`, venv ở `C:\venvs\news-scape`
- [ ] A: `pytest -q` → 357
- [ ] A: OneDrive → Choose folders → **bỏ chọn** thư mục repo (KHÔNG xoá/đổi tên)
- [ ] Cả hai: `git config pull.rebase true`

## 9. Bảng tra sự cố

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `fatal: bad object refs/stash` | ref của máy kia sync sang, object không có | `git update-ref -d refs/stash` rồi pull lại |
| `There is no tracking information for the current branch` | `.git/config` bị sync đè | `git branch --set-upstream-to=origin/main main` |
| `ImportError` module vừa viết xong | file mới bị OneDrive xoá | `git checkout` nếu đã commit; nếu chưa — đã mất |
| `.venv` rỗng / `pyvenv.cfg` trỏ máy khác | venv trong vùng sync | dựng lại venv **ngoài** OneDrive |
| `OSError: Invalid argument` khi đọc Bronze | Files On-Demand dehydrate | "Always keep on this device", hoặc chuyển `data/` ra ngoài |
| `git add` báo `read error while indexing …: Invalid argument` | cùng nguyên nhân: file là placeholder chưa hydrate | `attrib -U +P "<file>"` rồi `certutil -hashfile <file> SHA256` để ép tải, sau đó `git add` lại |
| merge-base lùi cả tháng, commit trùng tiêu đề | lịch sử đã push bị rewrite | dừng lại, so tree hash trước khi merge (xem `reports/06`) |

## Câu hỏi còn mở

1. Có bật GitHub Actions chạy `pytest` mỗi push không? (test zero-network nên khả thi)
2. Máy A có cần bản `data/` để audit định kỳ, hay giao hẳn việc audit cho máy B?
3. `.git` của máy B đặt ở `C:\gitdirs\` — có cần backup riêng cho thư mục này không
   (nó không còn được OneDrive che nữa)?
