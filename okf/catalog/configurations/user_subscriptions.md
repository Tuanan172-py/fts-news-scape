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
sources_last_checked: 2026-10-22
---

Đầu vào cấp cao nhất của hệ thống là **danh mục theo dõi do người dùng khai**. Người dùng chỉ
chạm 1 file; phần còn lại do `compile` sinh tự động.[^compile]

# Luồng 2 bước

```
<DATA_ROOT>/subscriptions/<name>.xlsx|.csv  (NGƯỜI DÙNG nhập)
        │  scripts/compile_users.py --all
        ▼
project/config/entities/users/<name>.yaml   (AUTO-GENERATED — đừng sửa tay)
        │   + <thư mục đăng ký>/_unknown/<name>_unknown.txt nếu có giá trị không map được
        ▼
EntityRegistry.subscriptions[<name>] → subscribers_for() → định tuyến tin
```

# Vị trí file đăng ký

`compile_all()` dò theo thứ tự:[^compile]

1. `paths.subscriptions_dir()` = `NEWS_SCAPE_SUBSCRIPTIONS_DIR` nếu đặt, mặc định
   `<DATA_ROOT>/subscriptions/` — nếu tồn tại;
2. `<DATA_ROOT>/inputs/users` (bố cục `users/input` cũ đã chép sang khi chuyển dữ liệu) — fallback.

Trong thư mục đó chấp nhận:
- **File phẳng**: `<name>.xlsx` / `<name>.csv` / `<name>_news.csv` — ưu tiên `.xlsx` khi trùng
  tên. Tên file quyết định tên người dùng (`AnPT_news.csv` → `AnPT`).
- **Thư mục con** (tương thích ngược): `<name>/entities.csv|entities.xlsx|<name>_news.csv`.
- Tên bắt đầu bằng `_` luôn bị bỏ qua.

Danh sách người dùng hiện có: `python scripts/pipeline_radar.py users` (chỉ đọc).

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
- [User Deliverables](../datasets/user_deliverables.md) · [Runbook](../playbooks/runbook.md)

[^compile]: [compile.py](project/src/users/compile.py)
[^manifest]: [user_manifest.py](project/src/core/user_manifest.py)
[^anpt-yaml]: [AnPT.yaml](project/config/entities/users/AnPT.yaml)
