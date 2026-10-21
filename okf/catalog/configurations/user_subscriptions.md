---
type: Configuration
title: User Subscriptions
description: Người dùng khai danh mục theo dõi (CSV/Excel) → compile thành config yaml máy đọc; manifest bật/tắt từng người.
resource: project/config/entities/users/
tags: [config, per-user, subscription, compile]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: compile
    resource: project/src/users/compile.py
    title: read_user_file / compile_all / load_manifest / enabled_users
  - id: manifest
    resource: project/src/core/user_manifest.py
    title: Manifest bật/tắt người dùng (SSOT)
  - id: anpt-yaml
    resource: project/config/entities/users/AnPT.yaml
    title: Ví dụ config AUTO-GENERATED
  - id: user-workflow-design
    resource: project/docs/design/13-per-user-output-workflow.md
    title: Per-user output workflow
sources_last_checked: 2026-09-07
---

Đầu vào cấp cao nhất của hệ thống là **danh mục theo dõi do người dùng khai**. Người dùng chỉ
chạm 1 file; phần còn lại do `compile` sinh tự động.[^compile]

# Luồng 2 bước

```
users/subscriptions/<name>.xlsx|.csv        (NGƯỜI DÙNG nhập)
        │  scripts/compile_users.py --all
        ▼
project/config/entities/users/<name>.yaml   (AUTO-GENERATED — đừng sửa tay)
        │   + users/subscriptions/_unknown/<name>_unknown.txt nếu có giá trị không map được
        │     (bố cục thư mục con cũ: <name>/_unknown.txt)
        ▼
EntityRegistry.subscriptions[<name>] → subscribers_for() → định tuyến tin
```

# Vị trí file đăng ký

`compile_all()` dò theo thứ tự:[^compile]

1. `users/subscriptions/` (mặc định hiện hành) — nếu tồn tại;
2. `users/input/` (bố cục cũ) — fallback.

Trong thư mục đó chấp nhận:
- **File phẳng**: `<name>.xlsx` / `<name>.csv` / `<name>_news.csv` — ưu tiên `.xlsx` khi trùng
  tên. Tên file quyết định tên người dùng (`AnPT_news.csv` → `AnPT`).
- **Thư mục con** (tương thích ngược): `<name>/entities.csv|entities.xlsx|<name>_news.csv`.
- Tên bắt đầu bằng `_` luôn bị bỏ qua.

## Trạng thái thực tế (2026-09-07)

```
users/subscriptions/
├── AnPT_news.xlsx        → user AnPT
├── PhoHG_news.xlsx       → user PhoHG
├── ThanhTD_news.xlsx     → user ThanhTD
├── _template_news.xlsx   (bắt đầu bằng '_' → bỏ qua)
├── _unknown/             (bắt đầu bằng '_' → bỏ qua)
└── manifest.yaml
```

Đây là thư mục đăng ký **đang có hiệu lực** — phải giữ nguyên. Bản `.csv` cũ
(`AnPT_news.csv`, `_template_news.csv`) đã được thay bằng `.xlsx`; `compile_all()` ưu tiên
`.xlsx` nên dù còn cả hai cũng chỉ 1 bản được dùng cho mỗi người dùng.

# Định dạng người dùng nhập

Hai kiểu, tự nhận diện:[^compile]
- **Ma trận ngang** — mỗi cột = 1 nhóm, mỗi dòng = 1 giá trị.
- **Tidy dọc** — cột `category`/`type` + `code`/`value` (+ `note` tuỳ chọn).

Nhóm hợp lệ: `tickers`, `etfs`, `indices`, `exchanges`, `industries`, `nations`, `themes`,
`macro`, `assets`, `institutions`, `entities`.

- Mọi nhóm trừ `entities` dùng **CODE**, tự viết hoa khi compile (`hpg` → `HPG`).
- `industries` khớp theo **CODE ngành GICS**, không theo tên.
- `entities` là cửa thoát: nhập thẳng `entity_id` (vd `TICKER:HPG`).
- Giá trị không map được ⇒ ghi `_unknown/<name>_unknown.txt`, không làm hỏng compile; sửa
  xong compile lại thì file cảnh báo tự bị xoá.

Template: `python scripts/make_user_template.py` (thêm `--seed <name>` để đổ sẵn từ yaml có).

# Một manifest duy nhất (ADR-0026.D5)

`<gốc dữ liệu>/subscriptions/manifest.yaml` (bản mẫu `users/subscriptions/manifest.yaml`) là nguồn chân lý
duy nhất bật/tắt người dùng. `project/config/entities/manifest.yaml` đã khai tử. Cả `compile.py`
(`load_manifest`/`enabled_users`) và `entities.py` (`_load_manifest`) đọc qua `src/core/user_manifest.py`.

```yaml
enabled: true      # false = tắt TOÀN BỘ lớp đăng ký
default: true      # user chưa liệt kê → BẬT
users:
  AnPT: true
  PhoHG: true
```

Muốn thêm chuyên viên: đặt `<tên>_news.xlsx` vào thư mục đăng ký, chạy `scripts/compile_users.py --all`,
thêm tên vào `users:` nếu cần liệt kê rõ. `config/entities/users/*.yaml` là **AUTO-GENERATED**, không tạo tay.
Tra trạng thái bằng `python scripts/pipeline_radar.py users`.

# Kết quả compile

`config/entities/users/<name>.yaml` có header `AUTO-GENERATED`, liệt kê entity_id theo nhóm.
Cuối `compile_all()` gọi `load_registry.cache_clear()` để subscription mới có hiệu lực ngay.

# Liên quan

- [Entity Registry](entity_registry.md) · [User Output Workflow](../pipelines/user_output.md)
- [User Deliverables](../datasets/user_deliverables.md) · [Daily Agent Run](../playbooks/daily_agent_run.md)

[^compile]: [compile.py](project/src/users/compile.py)
[^manifest]: [user_manifest.py](project/src/core/user_manifest.py)
[^anpt-yaml]: [AnPT.yaml](project/config/entities/users/AnPT.yaml)
[^user-workflow-design]: [Per-user output workflow](project/docs/design/13-per-user-output-workflow.md)
