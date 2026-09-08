---
type: Configuration
title: Secrets Configuration
description: Token API ngoài (FireAnt) — file gitignored, thiếu token thì scraper tự tắt chứ không crash.
resource: project/config/secrets.yaml
tags: [config, yaml, secrets, security]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: secrets-example
    resource: project/config/secrets.yaml.example
    title: Secrets template
  - id: config-loader
    resource: project/src/core/config.py
    title: load_secrets()
  - id: fireant
    resource: project/src/scrapers/fireant.py
    title: FireAnt scraper — Bearer token
sources_last_checked: 2026-09-07
---

`config/secrets.yaml` giữ token của API ngoài. File nằm trong `.gitignore`; chỉ template
`secrets.yaml.example` được commit.[^secrets-example]

# Cấu trúc

```yaml
# config/secrets.yaml
fireant_token: "PASTE_BEARER_TOKEN_HERE"
```

⚠️ Khoá là **`fireant_token`** ở cấp gốc (không phải `fireant.bearer_token` như bản mô tả cũ).

# Thiết lập

```powershell
copy config\secrets.yaml.example config\secrets.yaml
# rồi dán Bearer token thật vào
```

Lấy token: DevTools (F12) → Network → request tới `restv2.fireant.vn` → header
`Authorization: Bearer <token>`. Token hết hạn ⇒ scraper **tự disable** + log ERROR, pipeline
không crash; cập nhật thủ công.[^fireant]

# Bối cảnh hiện tại

`fireant` đang **disabled** trong [domain configs](domain_sources.md) (thuộc nhóm chưa có Bronze
capture), nên thiếu `secrets.yaml` **không** chặn vận hành hằng ngày. File chỉ cần thiết khi bật
lại FireAnt.

# Liên quan

- [settings.yaml](settings.md) · [watchlist.yaml](watchlist.md) · [Domain Sources](domain_sources.md)
- [Deployment](../playbooks/deployment.md)

[^secrets-example]: [Secrets template](project/config/secrets.yaml.example)
[^config-loader]: [config.py](project/src/core/config.py)
[^fireant]: [FireAnt scraper](project/src/scrapers/fireant.py)
