---
type: Configuration
title: Secrets Configuration
description: Quản lý biến môi trường và token của API ngoài (FireAnt, v.v.) — file bảo mật được gitignore.
resource: project/config/secrets.yaml
tags: [config, yaml, secrets, security]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: secrets-example
    resource: project/config/secrets.yaml.example
    title: Secrets template
  - id: readme
    resource: project/README.md
    title: Project README
sources_last_checked: 2026-08-04
---

File `config/secrets.yaml` lưu các token và secret được hệ thống đọc trong quá trình chạy. File này được đưa vào `.gitignore` để bảo mật, chỉ có template `secrets.yaml.example` được commit.[^secrets-example]

## Cấu trúc

```yaml
fireant:
  bearer_token: "your-token-here"
```

Nếu file không tồn tại hoặc thiếu token, scraper tương ứng (FireAnt) sẽ tự động bị vô hiệu hóa mà không gây crash hệ thống.[^readme]

## Cách thiết lập

```powershell
cp config/secrets.yaml.example config/secrets.yaml
# → Sửa file, điền Bearer token thật của FireAnt
```

## Liên quan

- [settings.yaml](settings.md) — Cấu hình toàn cục
- [watchlist.yaml](watchlist.md) — Danh sách mã theo dõi
- [Domain Sources](domain_sources.md) — Danh sách 23 domain config

[^secrets-example]: [Secrets template](project/config/secrets.yaml.example)
[^readme]: [Project README](project/README.md)
