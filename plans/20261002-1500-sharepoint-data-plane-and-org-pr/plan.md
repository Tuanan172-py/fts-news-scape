# Đề xuất: Kho dữ liệu chung trên SharePoint và tích hợp news-scape vào fpa-toolkit

- **Ngày lập:** 2026-10-02
- **Trạng thái:** Đề xuất, chờ duyệt. Chưa sửa mã.
- **Phân loại:** Cấp 3 (HIGH-RISK). Đề xuất đổi nơi lưu dữ liệu, sinh hợp đồng dữ liệu mới và cần cấp quyền ứng dụng trên tenant. Cần ADR và người duyệt trước khi triển khai.
- **Quan hệ với bản nháp cũ:** bản này rà lại [`../20261001-1630-fpa-toolkit-integration-strategy/plan.md`](../20261001-1630-fpa-toolkit-integration-strategy/plan.md) và đề nghị sửa ba điểm ở Phần B.3.

---

## Phần 0. Hiện trạng đo được (2026-10-02)

| Hạng mục | Số đo | Hệ quả |
| --- | --- | --- |
| Thư mục kho mã trong OneDrive | 7,0 GB | Kho mã đang mang theo dữ liệu nặng qua đồng bộ. |
| `project/data/` trong OneDrive | 5,4 GB. `raw_html` 25.481 tệp (2,5 GB), `silver` 12.131 tệp, `work_packages` 14.416 tệp | Số tệp nhỏ lớn, tăng mỗi ngày. Microsoft khuyến nghị một máy đồng bộ không quá 300.000 tệp. |
| `project/data/monocle.db` trong OneDrive | 187 MB, sửa lần cuối 21/09, còn `-wal`/`-shm` | Bản cũ nằm cạnh 4 bản sao lưu khác. Người mở nhầm sẽ thấy dữ liệu lệch 11 ngày. |
| DB vận hành `C:\data\news-scape\monocle.db` | 675 MB, đang ghi (WAL 4,4 MB) | Đây là nguồn chân lý duy nhất hiện nay. Có thêm `monocle-FPA-AnPT.db`, dấu vết của việc nhiều máy giữ bản riêng. |
| Dấu vết xung đột đồng bộ | `data/archive_conflicts/`, luật `**/*-DESKTOP-*` trong `.gitignore` | Xung đột OneDrive đã xảy ra trước đây. |
| Git: tệp dữ liệu vẫn được theo dõi | 2.826 tệp dưới `project/data/silver` và `project/data/work_packages` | Đã thêm vào `.gitignore` nhưng chưa `git rm --cached`, nên vẫn nằm trong lịch sử. |
| Git remote | `github.com/Tuanan172-py/fts-news-scape` (tài khoản cá nhân) | Quản lý tổ chức không nhìn thấy kho, tài sản mã chưa thuộc tổ chức. |
| Tệp được theo dõi chứa đường dẫn máy (`C:\Users\anpt`, `C:\data\news-scape`) | 64 tệp | Vi phạm `no-workspace-paths` nếu đưa sang fpa-toolkit. |
| Tệp được theo dõi nhắc tên trợ lý AI | 69 tệp (lịch sử commit: 0) | Vi phạm GLB-DEC-069 nếu đưa sang fpa-toolkit. |

---

## Phần A. Kho dữ liệu chung trên SharePoint

### A.1 Yêu cầu nghiệp vụ

| Mã | Yêu cầu | Ai dùng |
| --- | --- | --- |
| R1 | Một kho chung trên SharePoint giữ cả dữ liệu thô (Bronze) và dữ liệu đã qua toàn bộ quy trình. | Toàn khối |
| R2 | Người dùng tự tạo skill hoặc template riêng để lấy tin từ kho đã xử lý, không phải chạy pipeline. | Chuyên viên |
| R3 | Đội dev triển khai mã lên một máy chủ chung, máy này chạy thu thập và vận hành hằng ngày. | Dev |
| R4 | Phần chạy mô hình có thể làm trên nhiều laptop, mỗi máy một nhà cung cấp LLM khác nhau, rồi đẩy kết quả về kho chung. | Dev, người vận hành |
| R5 | An toàn dài hạn: không xung đột ghi, không hỏng dữ liệu, truy vết được ai ghi gì, khôi phục được, phân quyền tối thiểu. | Quản lý |

Ràng buộc kế thừa từ dự án: Bronze bất biến, thu thập trọn vẹn (ADR 0013), cổng DoD khi nạp, sổ cái token, mô hình phân tích chứ không phải script (AGENTS.md §6C).

### A.2 Sự thật kỹ thuật quyết định thiết kế

1. **SQLite không chịu được nhiều máy cùng ghi qua tệp đồng bộ.** SQLite xác nhận khoá tệp trên hệ thống tệp mạng có thể sai và gây hỏng DB, WAL chỉ chạy khi mọi tiến trình trên cùng một máy, và tách tệp DB khỏi tệp `-wal` là một nguyên nhân hỏng được liệt kê. OneDrive đồng bộ `.db` và `-wal` như hai tệp độc lập. Nguồn: sqlite.org/useovernet.html, sqlite.org/howtocorrupt.html.
2. **SharePoint là kho tệp có phiên bản, không phải máy chủ CSDL.** Microsoft liệt kê việc dùng SharePoint làm dịch vụ trung gian giữa M365 và một kho khác là cách dùng không được hỗ trợ. Danh sách có ngưỡng hiển thị 5.000 mục không đổi được.
3. **Graph API đủ để tự động hoá an toàn:**
   - Cấp quyền ứng dụng theo đúng một site (`Sites.Selected`) hoặc đúng một thư viện (`Lists.SelectedOperations.Selected`). Cấp quyền gồm ba bước: admin đồng ý trong Entra ID, gọi `POST /sites/{id}/permissions` với vai trò `read` hoặc `write`, rồi lấy token. Thiếu một bước là không có quyền.
   - Xác thực bằng chứng chỉ. Microsoft khuyến nghị không dùng client secret cho môi trường sản xuất. SharePoint REST app-only bắt buộc chứng chỉ.
   - Tải lên: PUT một lần tới 250 MB. Tệp lớn hơn 10 MB nên dùng upload session, mỗi mảnh là bội số của 320 KiB, khuyến nghị 5 đến 10 MiB.
   - Chống ghi đè: `@microsoft.graph.conflictBehavior=fail` trả 409 khi tên đã tồn tại. `If-Match` theo eTag trả 412 khi tệp đã bị người khác sửa.
   - Theo dõi thay đổi: delta query trên `/drives/{id}/root/delta`. Webhook chỉ đăng ký được ở gốc thư viện, sống tối đa khoảng 29 ngày, trễ trung bình dưới 1 phút nhưng có thể tới 6 giờ.
   - Giới hạn tốc độ (tenant dưới 1.000 giấy phép): 1.250 đơn vị tài nguyên mỗi phút cho mỗi ứng dụng. Tải lên tốn 2 đơn vị, đọc tốn 1. Khi bị chặn, Graph trả 429 kèm `Retry-After`.
   - Thư viện Python: `msgraph-sdk` (chính hãng, async), `Office365-REST-Python-Client` (đồng bộ, hỗ trợ chứng chỉ và upload session).
4. **Chưa xác minh được:** Microsoft không mô tả việc tạo tệp với `conflictBehavior=fail` như một khoá phân tán. Thiết kế dưới đây không dựa vào khoá đó.

### A.3 Các phương án

| Phương án | Mô tả | Đánh giá |
| --- | --- | --- |
| **A1. DB sống trên SharePoint** | Đặt `monocle.db` vào thư mục đồng bộ, mọi máy ghi thẳng. | **Loại.** Hỏng DB theo đúng cơ chế SQLite cảnh báo. Dự án đã có dấu vết xung đột. |
| **A2. Máy chủ CSDL (PostgreSQL) + SharePoint chỉ để phát hành** | DB trên máy chủ chung, laptop ghi qua mạng nội bộ hoặc VPN. | Mạnh về đồng thời. Cần IT cấp máy chủ, cổng mạng, chuyển đổi lược đồ khỏi SQLite. Hợp làm đích dài hạn, quá lớn cho bước đầu. |
| **A3. Một máy ghi, SharePoint là kho phát hành và hộp trao đổi** (đề xuất) | Máy chủ giữ DB trên ổ cục bộ và là nơi ghi duy nhất. SharePoint nhận ảnh chụp bất biến (Parquet, Bronze theo ngày, bản DB chỉ đọc). Laptop không ghi DB, chỉ nộp tệp kết quả có tên duy nhất vào hộp thư đến. Máy chủ nạp qua cổng DoD hiện có. | Không đổi lược đồ DB, dùng lại vòng đời packet và `--finish` đang chạy. Không có hai bên cùng ghi một tệp nên không có xung đột theo cấu trúc. |
| **A4. Azure Blob/ADLS hoặc Fabric OneLake** | Kho phân tích chuyên dụng, OneLake tạo được lối tắt tới thư mục SharePoint. | Cần giấy phép và IT. Giữ làm đường mở rộng, hợp đồng dữ liệu của A3 dùng lại được. |

**Đề xuất: A3 ngay, giữ đường lên A2 hoặc A4.** Mọi truy cập DB đã đi qua `src/db/store.py`, nên đổi sang PostgreSQL sau này chỉ chạm tầng đó.

### A.4 Kiến trúc A3

```
   Máy chủ chung (vai trò server)                SharePoint site FRA - Data
   ┌───────────────────────────────┐            ┌────────────────────────────────────┐
   │ ops_daemon, capture, --finish │  publish   │ News-Curated (đọc: chuyên viên)     │
   │ monocle.db trên ổ cục bộ      │──Graph────▶│   parquet/articles/year=/month=/    │
   │ (nơi ghi DB duy nhất)         │            │   parquet/mentions/  okf/  _manifest│
   │                               │──Graph────▶│ News-Bronze (đọc: dev, kiểm toán)   │
   │                               │            │   raw/YYYY/MM/DD/<nguồn>.tar.zst    │
   │                               │  packets   │ News-Exchange (dev + máy xử lý)     │
   │                               │──Graph────▶│   outbox/<máy>/<đợt>/...            │
   │  ingest qua cổng DoD          │◀──delta────│   inbox/<đợt>/<máy>__<lô>__<uuid>   │
   └───────────────────────────────┘            └────────────────────────────────────┘
                                                      ▲                 │
   Laptop (vai trò processor, mỗi máy một provider)    │ nộp kết quả     │ đọc packet
   ──────────────────────────────────────────────────── ┘                 ▼
   Chuyên viên (vai trò reader): đọc News-Curated qua lối tắt OneDrive `sharepoint/FRA - Data/news/`
   hoặc `UniversalHub.news` trong fpa-toolkit.
```

**Ba vai trò, một biến cấu hình** (`NS_ROLE=server|processor|reader`). Mã kiểm tra vai trò trước mọi lệnh ghi:

| Vai trò | Được làm | Không được làm |
| --- | --- | --- |
| server | capture, đóng gói đợt, `--finish`, ghi DB, phát hành | |
| processor | kéo packet được giao, chạy mô hình, nộp kết quả vào `inbox/` | ghi DB, capture, phát hành, sửa tệp người khác |
| reader | đọc News-Curated | mọi thao tác ghi |

### A.5 Bất biến chống xung đột

1. **Một nơi ghi cho mỗi loại dữ liệu.** Chỉ máy chủ ghi DB, News-Curated và News-Bronze.
2. **Tệp bất biến, tên duy nhất.** Không sửa tại chỗ. Phát hành bản mới bằng tệp mới, sau đó đổi con trỏ `_manifest/latest.json` bằng `If-Match` theo eTag. Người đọc luôn đi từ manifest, nên không bao giờ đọc nửa chừng.
3. **Giao việc thay cho tranh khoá.** Máy chủ chia lô cho từng máy ngay khi đóng gói (`outbox/<máy>/`). Hai laptop không bao giờ tranh một lô, nên không cần khoá phân tán. Lô quá hạn được máy chủ thu hồi và giao lại.
4. **Nạp lũy đẳng.** Khoá nạp là `(mã đợt, article_id, phiên bản lược đồ)`. Tệp nộp trùng không sinh bản ghi trùng. Tệp hỏng chuyển vào `rejected/` kèm lý do, không bị xoá.
5. **Kiểm tổng SHA-256** cho mọi tệp phát hành, ghi trong manifest. Người đọc kiểm trước khi dùng.
6. **Hợp đồng dữ liệu có phiên bản** (`news-articles-v1`). Thay đổi phá vỡ tương thích đi vào đường dẫn `v2` song song, giữ `v1` tới khi mọi người đọc chuyển xong.
7. **Không bao giờ đặt DB đang ghi vào thư mục đồng bộ.** Bản DB chỉ đọc cho người cần SQL được tạo bằng `VACUUM INTO`, rồi mới tải lên.
8. **Bronze đóng gói theo ngày.** Không tải từng tệp HTML lên (25 nghìn tệp và đang tăng). Mỗi ngày mỗi nguồn một gói, kèm danh sách SHA-256 từng bài để kiểm toán.
9. **Bí mật không lên SharePoint.** Chứng chỉ Graph nằm trong kho chứng chỉ Windows của máy chủ. Khoá API LLM của laptop nằm trong Windows Credential Manager của máy đó.

### A.6 Phân quyền

Ranh giới quyền đặt ở **cấp thư viện**, không ở thư mục, để không phá kế thừa quyền và không chạm giới hạn 50.000 quyền riêng mỗi danh sách.

| Danh tính | News-Curated | News-Bronze | News-Exchange |
| --- | --- | --- | --- |
| Ứng dụng `news-scape-publisher` (Entra ID, chứng chỉ, `Lists.SelectedOperations.Selected`) | write | write | write |
| Nhóm `ns-dev-owners` | owner | owner | owner |
| Nhóm `ns-processors` (người chạy laptop) | read | không | contribute |
| Nhóm chuyên viên FRA | read | không | không |

Người dùng không có quyền ghi vào News-Curated, nên template hay skill riêng của họ không thể làm hỏng dữ liệu chung.

### A.7 Skill và template tuỳ biến của người dùng (R2)

Không đặt template người dùng trên SharePoint. fpa-toolkit đã có cơ chế cho việc này:
- Skill chung `news-query` trong `.agents/skills/` của fpa-toolkit, gọi `UniversalHub.news` để lọc theo mã, ngành, ngày, cảm xúc.
- Người dùng mở rộng skill trong workspace cá nhân (Zone 2, GLB-DEC-042 về mirror và mở rộng skill). Workspace đã đồng bộ qua OneDrive cá nhân và nằm ngoài Git.

Cách này giữ một nguồn dữ liệu chung, chỉ đọc, còn phần tuỳ biến nằm ở người dùng.

### A.8 Lộ trình triển khai

| Bước | Việc | Cần ai | Rủi ro |
| --- | --- | --- | --- |
| P0 (vệ sinh, 1 ngày) | `git rm -r --cached project/data/silver project/data/work_packages`. Chuyển `project/data/*.db*` và các bản sao lưu ra `C:\data\news-scape\legacy\` sau khi kiểm SHA-256. Chuyển `raw_html`, `silver`, `work_packages` ra khỏi OneDrive, đối chiếu số tệp và SHA-256 trước khi gỡ bản gốc. Không đụng `project/src/data/` cho tới khi có bản sao kiểm chứng, vì đó là Bronze duy nhất của giai đoạn đầu. | Dev | Thấp. Chỉ di chuyển, không xoá. |
| P1 (phát hành một chiều) | Viết bộ xuất Parquet và manifest theo hợp đồng `news-articles-v1`. Máy chủ ghi vào `FRA - Data/news/` qua lối tắt OneDrive (một nơi ghi, tệp bất biến nên đồng bộ đủ an toàn). | Dev | Thấp. Chưa cần IT. |
| P2 (hộp trao đổi) | `outbox/inbox` cho laptop, nạp lũy đẳng, thu hồi lô quá hạn. Biến `NS_ROLE`. | Dev | Trung bình. Thay đổi vòng đời đợt. |
| P3 (Graph API) | Đăng ký ứng dụng Entra ID, chứng chỉ, cấp `Lists.SelectedOperations.Selected` trên ba thư viện. Máy chủ chuyển từ đồng bộ sang Graph, dùng delta query cho `inbox/`. | **IT tenant admin** | Trung bình. Phụ thuộc người ngoài đội. |
| P4 (khi cần) | PostgreSQL hoặc Fabric nếu số máy xử lý tăng hoặc chuyên viên cần truy vấn SQL trực tiếp. | IT | Đánh giá lại sau 3 tháng vận hành. |

---

## Phần B. Pull request vào `Research-FPA/fpa-toolkit`

### B.1 Quy chuẩn của fpa-toolkit ràng buộc PR

| Quy chuẩn | Nội dung | Ảnh hưởng tới news-scape |
| --- | --- | --- |
| `no-data-files` | Hook chặn `.xlsx .xls .csv .parquet .pkl`. `.gitignore` chặn mọi `**/data/`. | Test không được kèm tệp Parquet cố định. Phải sinh dữ liệu trong `tmp_path`. |
| `check-added-large-files` | Tệp trên 500 KB bị chặn. | Không mang fixture HTML lớn. |
| `no-workspace-paths`, GLB-DEC-062, GLB-DEC-066 | Tài liệu chung không được trỏ vào workspace cá nhân. Nhật ký phát triển chia 3 tầng. | 64 tệp có đường dẫn máy phải sửa nếu mang sang. |
| GLB-DEC-069 | Không nhắc tên trợ lý AI trong commit, PR, mã, tài liệu. Hook `commit-msg` chặn. | 69 tệp nhắc tên. Commit và PR trong fpa-toolkit không được có dòng ghi danh trợ lý. Luật này có hiệu lực cao hơn mẫu ghi danh mặc định của công cụ. |
| Universal English Core (FFA-DEC-006) | Mã và tài liệu bằng tiếng Anh. | Toàn bộ tài liệu news-scape đang bằng tiếng Việt. |
| GLB-DEC-068 (gói vệ tinh) | Gói trong `packages/` không được import `shared`, `ffa`, `fqs`, `fta`, `admin`. | Nếu đặt news-scape vào `packages/`, nó không gọi được `UniversalHub.get_all_tickers()`. |
| GitHub Free, không Actions | Mọi kiểm tra chạy ở máy dev bằng pre-commit và `wrapup_runner`. | PR phải tự chứng minh bằng đầu ra lệnh. |

### B.2 Các phương án

| Phương án | Mô tả | Đánh giá |
| --- | --- | --- |
| **B1. Viết lại mỏng trong `shared/news/`** (bản nháp 01/10) | Viết mới scraper, tagger regex, digest, writer khoảng 600 dòng. | PR gọn, nhưng tạo bản thứ hai yếu hơn của hệ thống đang chạy, hai mã nguồn trôi dần. Quản lý chỉ thấy 600 dòng, không thấy năng lực thật của dự án. Phần tagger regex và digest bằng code vi phạm nguyên tắc LLM-first của chính dự án. |
| **B2. Chuyển nguyên khối** | Đưa `project/` vào monorepo. | **Loại.** Vi phạm hook dữ liệu, ngôn ngữ, đường dẫn. Test phụ thuộc mạng làm đỏ toàn monorepo. |
| **B3. Gói vệ tinh `packages/news_scape/`** | Theo GLB-DEC-068. | Mô hình này đặt monorepo làm nguồn chân lý và cấm import `shared`. news-scape đang phát triển nhanh ở kho riêng, nên đồng bộ hai chiều sẽ thành gánh nặng. Hợp khi phần sản xuất đã ổn định. |
| **B4. Kho sản xuất về tổ chức + hợp đồng và lớp tiêu thụ trong monorepo** (đề xuất) | Chuyển kho news-scape về tổ chức. Monorepo nhận hồ sơ dự án, hợp đồng dữ liệu, bộ nạp `UniversalHub.news`, template OKF và skill tra cứu. | Quản lý thấy toàn bộ dự án ở kho tổ chức. Monorepo chỉ nhận phần ổn định, nhỏ, kiểm thử offline. Không trùng mã. |

### B.3 Ba điểm cần sửa trong bản nháp 01/10

1. **Bỏ `extract_tickers` bằng regex `[A-Z0-9]+` và `generate_digest` bằng code.** Nhận diện thực thể và tóm tắt là việc của mô hình (AGENTS.md §6C). Monorepo chỉ nên nhận kết quả đã phân tích qua hợp đồng dữ liệu. Đối chiếu với `get_all_tickers()` vẫn có ích, nhưng ở vai trò kiểm tra, không phải bộ sinh.
2. **Không sinh ghi chú OKF hằng ngày vào `shared/okf_base/news/` trong Git.** Epic 3 ghi thư mục này chứa "generated OKF news notes". Mỗi ngày hàng trăm ghi chú sẽ làm phình lịch sử Git. Đề nghị với reviewer: Git giữ template và lược đồ, ghi chú sinh ra nằm ở `FRA - Data/news/okf/`.
3. **Không viết lại scraper trong monorepo.** Phần thu thập đã có quy chuẩn thu thập trọn vẹn, sổ phát hiện, phân trang theo watermark. Bản viết lại 1 trang RSS sẽ không đạt các bất biến đó.

### B.4 Chuyển kho news-scape về tổ chức

Kho hiện ở tài khoản cá nhân `Tuanan172-py/fts-news-scape`. Đề nghị dùng chức năng **Transfer repository** của GitHub sang `Research-FPA/news-scape` (riêng tư). Chuyển giữ nguyên lịch sử commit, nhánh, issue, và GitHub tự chuyển hướng URL cũ.

Trước khi chuyển:
- Gỡ 2.826 tệp dữ liệu khỏi theo dõi (P0). Lịch sử cũ vẫn chứa chúng. Nếu tổ chức yêu cầu sạch hoàn toàn, chạy `git filter-repo --path project/data --invert-paths` trên một bản clone và đẩy lại, việc này đổi mã commit nên cần thống nhất trước.
- Rà 64 tệp có đường dẫn máy, thay bằng biến môi trường.
- Hỏi reviewer GLB-DEC-069 có áp dụng cho kho vệ tinh không. Nếu có, xử lý 69 tệp nhắc tên trợ lý (phần lớn là tài liệu hướng dẫn agent).

Sau khi chuyển, quản lý theo dõi tiến độ tại một chỗ:
- **Checkpoint = tag phát hành** (`v0.9.0`, `v1.0.0`) kèm `CHANGELOG.md` sinh từ commit chuẩn conventional.
- **GitHub Milestones và Projects** (miễn phí) cho lộ trình. Mỗi user story `US-0xx` là một issue.
- **ADR** của dự án giữ trong `docs/decisions/`, đã có 16 bản.

### B.5 Chuỗi PR vào fpa-toolkit

Chia nhỏ, mỗi PR một mục đích, mỗi PR tự qua `pre-commit run --all-files` và `wrapup_runner`. Nhánh tách từ `origin/main`, commit không có dòng ghi danh trợ lý.

| PR | Nội dung | Thư mục | Bằng chứng |
| --- | --- | --- | --- |
| PR-1 (tài liệu) | Hồ sơ dự án tiếng Anh: tổng quan kiến trúc, ranh giới sản xuất và tiêu thụ, hợp đồng `news-articles-v1` (cột, kiểu, phân vùng, manifest), bảng checkpoint trỏ về tag của kho tổ chức. ADR mới `GLB-DEC-0xx` cho kho dữ liệu tin tức trên SharePoint (Phần A). Cập nhật trạng thái trong Epic 3. | `shared/docs/news/`, `docs/adr/`, `docs/GE_rollout/epics/EPIC-03-*` | `check-frontmatter-quality`, `no-workspace-paths`, `test_docs_integrity.py` |
| PR-2 (bộ nạp) | `shared/news/contract.py` (hằng lược đồ, hàm kiểm tra, thuần), `shared/data_ingestion/news_loader.py` (Polars lazy scan, lọc theo mã, ngày, ngành), gắn `UniversalHub.news`. Test sinh Parquet tổng hợp trong `tmp_path` (GLB-DEC-053). | `shared/news/`, `shared/data_ingestion/`, `tests/shared/unit/test_news*.py` | pytest offline, dưới 3 giây |
| PR-3 (OKF) | Template ghi chú tin tức, `writer.py` sinh ghi chú từ một dòng hợp đồng, mẫu cho VCB và HPG. Báo cáo chạy thí điểm 30 bài ngân hàng và thép (Slice 4 của Epic) bằng số đếm, không kèm dữ liệu. | `shared/okf_base/news/templates/`, `shared/news/writer.py` | `okf_manager validate` |
| PR-4 (skill) | Skill `news-query` cho chuyên viên, có công thức mẫu và hướng dẫn mở rộng trong workspace. | `.agents/skills/news-query/` | `check-frontmatter-quality` |

PR-2 tới PR-4 không cần dữ liệu thật trên SharePoint để merge. Chúng chỉ phụ thuộc hợp đồng ở PR-1.

### B.6 Danh sách loại trừ khi đưa sang fpa-toolkit

**Không bao giờ đưa:**
- Dữ liệu: `*.db*`, `raw_html/`, `silver/`, `work_packages/`, `agent_tasks/`, `agent_outputs*/`, `exports/`, `*.parquet`, `*.xlsx`, `*.csv`.
- Nội dung bài báo thật làm fixture. Đó là nội dung có bản quyền của các báo. Dùng văn bản tổng hợp.
- `users/` (danh sách đăng ký và watchlist gắn tên người, là dữ liệu nhân sự).
- `harness.db`, `logs/`, `docs/SESSION-LATEST.md`, `docs/stories/`, `plans/` (nhật ký nội bộ, tiếng Việt, đã nằm ở kho tổ chức).
- `.agents/dsh/` preset có đường dẫn máy, `.kilo/`, `.opencode/`, `.code-review-graph/`, `openrouter/` (benchmark, packet, output chứa nội dung bài), `other/`, `project/thamkhao/`.
- Mọi `.env`, khoá API, token Telegram, URL healthcheck.
- Mọi đường dẫn tuyệt đối và mọi nhắc tên trợ lý AI.

**Đưa:** chỉ những gì ở bảng B.5, viết mới bằng tiếng Anh theo chuẩn của monorepo, không chép tệp từ news-scape.

### B.7 Ghi nhận tiến độ trong monorepo

Theo GLB-DEC-062:
- Mỗi PR merge sinh một mục Tầng 1 trong `docs/governance/development_log.md`, 3 đến 6 gạch đầu dòng, mỗi gạch trích ADR, module công khai và lệnh chứng minh.
- Bảng trạng thái trong Epic 3 cập nhật theo slice.
- Chi tiết vận hành hằng ngày giữ ở kho `Research-FPA/news-scape`, không đưa vào nhật ký monorepo.

---

## Phần C. Quyết định cần người duyệt

| # | Câu hỏi | Người quyết | Đề xuất |
| --- | --- | --- | --- |
| D1 | Chọn A3 (một máy ghi, SharePoint phát hành) làm kiến trúc dữ liệu giai đoạn 1 | Trưởng dự án, Head of Research | Đồng ý |
| D2 | Tạo ba thư viện News-Curated, News-Bronze, News-Exchange trên site FRA - Data hay site riêng | Quản trị SharePoint | Site FRA - Data, khớp Zone 3 của GLB-DEC-040 |
| D3 | Đăng ký ứng dụng Entra ID với `Lists.SelectedOperations.Selected` và chứng chỉ | IT tenant admin | Cần cho P3, P1 và P2 chạy được khi chưa có |
| D4 | Chuyển kho về `Research-FPA/news-scape` và có lọc lịch sử hay không | Head of Research | Chuyển. Lọc lịch sử chỉ khi tổ chức yêu cầu. |
| D5 | Ghi chú OKF hằng ngày nằm ở Git hay ở SharePoint | Head of Research (chủ Epic 5) | SharePoint |
| D6 | GLB-DEC-069 có áp dụng cho kho vệ tinh news-scape không | Head of Research | Hỏi trước khi chuyển kho |
| D7 | Máy chủ chung là máy nào, ai quản trị, chạy Windows hay Linux | Trưởng dự án, IT | Cần trước P1 |

Sau khi D1 được duyệt: viết ADR 0017 trong `docs/decisions/` cho news-scape, mở story cho P0 và P1.
