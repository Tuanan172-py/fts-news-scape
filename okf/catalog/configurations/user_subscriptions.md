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
    resource: project/config/entities/manifest.yaml
    title: Manifest bật/tắt (DEV switch)
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

# Hai manifest — hai tầng gác khác nhau

Đây **không** phải một file bị trùng: hai file, hai module đọc, hai quy ước mặc định.

| File | Ai đọc | Gác cái gì | Mặc định khi vắng tên |
|---|---|---|---|
| `users/subscriptions/manifest.yaml` | `compile.py::load_manifest` / `enabled_users` | người dùng nào **được nhận output** | **BẬT** (`manifest.get(n, True)`) |
| `project/config/entities/manifest.yaml` | `entities.py::_load_manifest` | file `config/entities/users/*.yaml` nào **được nạp vào registry** | theo khoá `default` (đang là **TẮT**) |

```yaml
# users/subscriptions/manifest.yaml — vắng tên = mặc định BẬT
users:
  AnPT: true

# project/config/entities/manifest.yaml — công tắc DEV
enabled: true      # false = tắt TOÀN BỘ lớp đăng ký
default: false     # user chưa liệt kê → TẮT
users:
  AnPT: true
```

⚠️ **Một người dùng phải qua CẢ HAI cửa mới nhận được tin.** Vì manifest DEV để
`default: false`, thêm file đăng ký thôi là **chưa đủ** — bắt buộc liệt kê tên trong khoá
`users:` của `config/entities/manifest.yaml`.

Trạng thái 3 người dùng (2026-09-07):

| User | File đăng ký | Cửa 1 (output) | Cửa 2 (registry) | `config/entities/users/<name>.yaml` |
|---|---|---|---|---|
| AnPT | `AnPT_news.xlsx` | ✅ | ✅ liệt kê | đã có |
| PhoHG | `PhoHG_news.xlsx` | ✅ vắng tên = BẬT | ✅ liệt kê 2026-09-07 | **compile sinh** |
| ThanhTD | `ThanhTD_news.xlsx` | ✅ vắng tên = BẬT | ✅ liệt kê 2026-09-07 | **compile sinh** |

`config/entities/users/*.yaml` là **AUTO-GENERATED** — không tạo tay; lần
`scripts/compile_users.py --all` kế tiếp sẽ sinh `PhoHG.yaml` và `ThanhTD.yaml`, và cả hai được
manifest DEV cho qua ngay.

`A.yaml` / `B.yaml` còn trong `config/entities/users/` nhưng không có file đăng ký tương ứng và
không nằm trong manifest DEV ⇒ bị bỏ qua (tàn dư, xoá được).

# Kết quả compile

`config/entities/users/<name>.yaml` có header `AUTO-GENERATED`, liệt kê entity_id theo nhóm.
Cuối `compile_all()` gọi `load_registry.cache_clear()` để subscription mới có hiệu lực ngay.

# Liên quan

- [Entity Registry](entity_registry.md) · [User Output Workflow](../pipelines/user_output.md)
- [User Deliverables](../datasets/user_deliverables.md) · [Daily Agent Run](../playbooks/daily_agent_run.md)

[^compile]: [compile.py](project/src/users/compile.py)
[^manifest]: [manifest.yaml (DEV switch)](project/config/entities/manifest.yaml)
[^anpt-yaml]: [AnPT.yaml](project/config/entities/users/AnPT.yaml)
[^user-workflow-design]: [Per-user output workflow](project/docs/design/13-per-user-output-workflow.md)
