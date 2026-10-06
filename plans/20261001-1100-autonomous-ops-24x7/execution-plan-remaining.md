# Kế hoạch thực thi phần còn lại — vận hành tự chủ (US-029, ADR 0012)

- **Ngày:** 2026-10-01 15:45
- **Trạng thái:** kế hoạch, **chưa sửa mã**. Mỗi gói việc (WP) chỉ bắt đầu khi gói trước đạt nghiệm thu và cổng người (H) tương ứng đã mở.
- **Phạm vi:** những mục còn mở sau khi B1–B7, R2 và D9–D11 đã sửa (`docs/proposals/20261001-ops-council.md` §10). Không làm lại việc đã xong.

---

## 0. Mốc xuất phát (đã đo lúc 15:40)

| Hạng mục | Trạng thái thật |
|---|---|
| Mã | `project/src/ops/` cùng các script ops, **chưa commit** (untracked) trên nhánh `feature/article-lane-remove-gates` |
| Test ops | `test_ops_core.py` + `test_ops_runtime.py` + `test_ops_council_fixes.py`: **70 đạt** |
| Đợt thật | W10011351, W10011434, W10011518 đều DONE, mỗi đợt 100/100 bài, nạp DB (chạy tay, `manual`) |
| Daemon | Task `news-scape-ops` + `news-scape-ops-watchdog`, mức **L0**, sensor 2 s/lượt |
| Bài chờ | 585 trong phạm vi (30/09: 212, 01/10: 373); 10.803 ngoài phạm vi |
| Cào tin | `external`: morninger vẫn là tiến trình chạy tay từ 28/09 |
| Kênh người | Telegram chưa có token; chưa có standing order |

## 1. Mục còn mở (đã đối chiếu với mã)

| Mã | Vấn đề | Bằng chứng trong mã | Mức |
|---|---|---|---|
| A8 | `article_run.py` chạy tay không đọc `.pipeline.lock` và không loại bài đang giữ chỗ trong `ops_wave_articles`. Đợt tay có thể phân tích lại bài daemon đang chạy. | `grep pipeline.lock\|ops_wave_articles scripts/article_run.py` → không có | Chặn L1 |
| C6 | `CACHED` (OpenRouter) không có trong `RUNNER_STATUS_MAP`, nên rơi về `classify()` và thành FATAL. `max_tokens: 24000` trái ADR 0010 và cắt cụt lô 50 bài. | `breakers.py:33`; `openrouter_runner.py:370, 427` | Chặn failover |
| C12 | `probe_db` thử ghi `monocle.db` mỗi 60 s, kể cả lúc `--finish` đang nạp. Có thể gây cảnh báo critical giả và tranh khoá. | `daemon.py:239` | Chặn L1 |
| D13 | "Đợt sạch" chưa có điều kiện độ lệch thực thể. Tự hạ mức và cổng lên L1 chỉ đo kỹ thuật. | `ops.yaml` không có khoá ngưỡng | Chặn L1 |
| GAP-1 | Daemon chưa giữ morninger, vì tiến trình tay đang giữ `capture.lock`. Lỗ hổng gốc §1 của plan chưa đóng. | `status`: `Cào tin: external` | Nặng |
| A6 | Packet và đầu ra nằm trong OneDrive (`project/data/agent_tasks`, `agent_outputs_article`). Khi tệp bị khoá, `safe_atomic_write` ghi sang tên `…_HHMMSS.json`, glob `*.output.json` không thấy, và `--repair` tiêu token lại. | `wave_flow.py:20-21`, `article_run.py:40-41` | Nặng |
| G8, A11 | Hai nguồn điều phối: `drive_wave` và `pipeline.yaml`. Hai ngưỡng T1: 100 (`ops.yaml`) và 50 (`article_tick.py`). | `article_tick.py:31` | Vừa |
| S1 | Ngữ cảnh sentinel vẫn chứa đuôi log tự do; nút **[Chạy]** đứng ngay sau văn bản LLM. | `sentinel.py:100-102` | Vừa (sentinel đang draft) |
| R4 | `secrets/ops.env` là văn bản thuần. Key OpenRouter nằm trong `openrouter/.env` trên OneDrive, tức đã lên đám mây. | `config.py` `load_secrets` | Vừa |

**Ngoài phạm vi kế hoạch này, chỉ trỏ tới:**
- Story giao hàng theo người dùng (D11, D12).
- Tồn đọng 10,8 nghìn bài.
- Chống trùng đa nguồn (`docs/proposals/20261001-dedup-architecture.md`, đang chờ duyệt riêng).

---

## 2. Thứ tự và cổng

```
H1 commit mốc ─► WP1 C6 ─► WP2 A8 ─► WP3 C12(+probe tệp lạc) ─► WP4 D13
     ─► [CỔNG L1: H2 Telegram + H3 standing order L1, 5 đợt L1 quan sát]
     ─► WP5 GAP-1 (H4 dừng morninger tay) ─► WP6 A6 (ADR sửa đổi, H5) ─► WP7 G8/A11 ─► WP8 S1 ─► WP9 R4 (H6)
```

- WIP = 1. Mỗi WP xong thì chạy toàn bộ test ops, cộng các bộ test mà WP chạm tới.
- Mỗi mã có test hồi quy mang đúng tên mã, trong `tests/test_ops_remaining.py`.
- Cổng L1 chỉ mở khi `test_ops_*` đạt 100%, gồm mọi test B1–B7 và WP1–WP4.

---

## 3. Gói việc

### H1 — Chốt mốc (cổng người, không sửa mã)

- **Lý do:** bài học 1 của hội đồng: chỉ thẩm định trên SHA đã commit.
- **Việc:** commit trạng thái US-029 hiện có trên nhánh hiện tại. Tách diff `openrouter_runner.py` sang story **US-031** (OpenRouter), không gộp vào commit ops.
- **Người làm:** bạn cho phép commit. Agent soạn commit theo `docs/GIT_COMMIT_STANDARD.md`.
- **Nghiệm thu:** `git status` chỉ còn diff của US-031 và các tệp dedup/insight của phiên khác.

### WP1 — C6: trạng thái và trần đầu ra của OpenRouter (US-031, lane normal)

| | |
|---|---|
| Sửa | `breakers.RUNNER_STATUS_MAP` thêm `"CACHED": OK`. `openrouter_runner.py`: bỏ `max_tokens: 24000`, hoặc đặt bằng trần đầu ra của model; không dùng trần để chia lô (ADR 0010). |
| Tệp | `src/ops/breakers.py`, `src/agent/openrouter_runner.py` |
| Test | `test_C6_cached_is_ok`; `test_C6_no_output_cap_below_model_max` (payload gửi đi không mang `max_tokens` < trần model) |
| Nghiệm thu | Test đạt. Một lô thử 50 bài qua OpenRouter trả đủ 50 bản ghi. Lô này chỉ chạy khi bạn cho phép tiêu token. |
| Rủi ro | Đổi tham số API: lỗi 400 nếu model không nhận trường. Chặn bằng test payload. |

### WP2 — A8: một chủ duy nhất cho việc mở đợt (US-029, lane high-risk)

| | |
|---|---|
| Sửa | (1) `article_pack.load_candidates` **luôn** loại bài đang có trong `ops_wave_articles` của đợt chưa DONE/CANCELLED. Hiện chỉ loại khi có `--exclude-file`. Đọc `ops.db` chỉ đọc; thiếu `ops.db` thì bỏ qua. (2) `article_run.py` (prepare/analyze/repair) kiểm `.pipeline.lock`: daemon sống ở L1 thì từ chối và in lệnh `ops_daemon.py send pause`; cờ `--manual-override` ghi sự kiện `human.override` vào `ops.db`. |
| Tệp | `scripts/article_pack.py`, `scripts/article_run.py`, `src/ops/store.py` (hàm đọc bài giữ chỗ) |
| Test | `test_A8_pack_excludes_reserved_without_flag`; `test_A8_manual_run_refused_when_daemon_l1`; `test_A8_override_is_audited` |
| Nghiệm thu | Test đạt. `test_article_lane*` vẫn đạt. Radar vẫn đếm đúng. |
| Rủi ro | `load_candidates` cũng là bộ đếm của radar. Radar phải tách hai số "chờ" và "đang giữ chỗ" để không báo thiếu. |

### WP3 — C12: tải của probe lên DB vận hành, cộng phát hiện tệp lạc (US-029, lane normal)

| | |
|---|---|
| Sửa | (1) `probe_db` chạy mỗi 15' thay vì 60 s, và bỏ qua khi có đợt ở `FINISHING`. Khoá bận (`database is locked`) tính là đạt, nhất quán với `probe_write`. (2) Thêm `probe_stray_outputs`: đếm tệp `*_[0-9]{6}.json` trong thư mục đầu ra (dấu hiệu `safe_atomic_write` lùi tên vì OneDrive khoá). Có tệp thì cảnh báo vàng. Đây là đồng hồ đo cho WP6. |
| Tệp | `src/ops/probes.py`, `src/ops/daemon.py`, `config/ops.yaml` (`probes.db_interval_minutes: 15`) |
| Test | `test_C12_db_probe_skips_during_finishing`; `test_C12_db_probe_interval`; `test_A6_stray_output_probe` |
| Nghiệm thu | Test đạt. Chạy daemon 1 giờ: số lần mở khoá ghi trên `monocle.db` từ probe ≤ 4. |

### WP4 — D13: đợt "sạch" có nghĩa chất lượng (US-029, lane normal)

| | |
|---|---|
| Đo trước | Đọc số liệu đối chiếu model ↔ bộ nhận diện tất định của 3 đợt thật (W10011351, W10011434, W10011518) từ bàn giao của `--finish`. Lấy tỷ lệ BOTH/MODEL_ONLY/CODE_ONLY làm nền. |
| Sửa | `ops.yaml` thêm `quality.max_entity_deviation` (khởi đầu = nền + 10 điểm, ghi rõ nguồn số). `finalize`: đợt chỉ "sạch" khi bài > 0, độ phủ ≥ 90% và độ lệch ≤ ngưỡng. Đợt 0 bài, PARKED hoặc vượt ngưỡng đều reset `clean_streak`; vượt ngưỡng thì gửi cảnh báo vàng kèm mã đợt. Không chặn nạp DB: cổng DoD vẫn là cổng duy nhất của việc nạp. |
| Tệp | `src/ops/wave_flow.py`, `config/ops.yaml`, hàm đọc số đối chiếu (tái dùng, không tính lại) |
| Test | `test_D13_zero_article_not_clean`; `test_D13_deviation_over_threshold_resets_streak`; `test_D13_parked_resets_streak` |
| Nghiệm thu | Test đạt. Ba đợt thật được chấm lại, kết quả ghi vào ADR 0012. |
| Cần người | Bạn duyệt con số ngưỡng sau khi xem số nền. |

### CỔNG L1 (cổng người)

1. **H2:** tạo bot Telegram, nhắn `/start` từ **chat riêng**, rồi chạy `ops_daemon.py telegram --token …`.
2. **H3:** `ops_daemon.py order --level L1 --days 7`.
3. Quan sát 5 đợt L1 đầu: mỗi đợt có tin mở và tin kết thúc, không có đợt nào trùng bài với đợt khác (truy vấn `ops_wave_articles`), token mỗi đợt nằm trong dải của 3 đợt thật.
4. Lệch bất kỳ điểm nào thì `/pause` và quay về WP tương ứng.

### WP5 — GAP-1: daemon giữ morninger (US-029, lane normal, cần H4)

| | |
|---|---|
| Việc | **H4:** bạn cho phép dừng tiến trình morninger đang chạy tay (PID hiện tại, chạy từ 28/09). Supervisor tự sinh morninger mới ở nhịp kế tiếp (15 s). Không sửa mã, trừ khi lộ lỗi. |
| Kiểm | `status`: `Cào tin: child`. Kill morninger thì supervisor dựng lại sau ≤ 30 s. Độ tươi cào tin trên radar vẫn 🟢 sau 30'. |
| Quay lui | `ops.yaml supervisor.manage_capture: false`, rồi chạy tay morninger như cũ. |

### WP6 — A6: chuyển thư mục làm việc của đợt ra ngoài OneDrive (US-032, lane high-risk)

| | |
|---|---|
| Vì sao high-risk | Đổi đường dẫn mà 8+ script dùng chung (`article_run`, `article_pack`, `article_expand`, `token_ledger`, `pipeline_radar`, `agy_runner`, `openrouter_runner`, `src/ops`). Một chỗ quên là mất packet hoặc phân tích lại. |
| Cổng | Sửa đổi ADR 0012 (hoặc ADR mới) ghi đường dẫn mới; **H5** bạn duyệt. Chỉ làm khi WP3 đã đo được tệp lạc, hoặc bạn quyết làm phòng ngừa. |
| Sửa | Một nguồn duy nhất cho đường dẫn: `src/core/paths.py` với `ARTICLE_TASK_DIR` và `ARTICLE_OUT_DIR`, mặc định `C:\data\news-scape\agent_tasks\article` và `…\agent_outputs_article`, đè được bằng biến môi trường. Mọi script import từ đây. Di chuyển: **sao chép**, không xoá, mọi tệp hiện có sang chỗ mới; bản cũ giữ nguyên tới khi bạn cho xoá. |
| Test | `test_A6_single_path_source` (quét mã: không còn `"agent_tasks" / "article"` ghép tay ngoài `paths.py`); `test_A6_paths_outside_onedrive`; toàn bộ `test_article_lane*` đạt |
| Nghiệm thu | Một đợt L1 thật chạy trọn trên đường dẫn mới. Radar đọc đúng đợt cũ (sao chép) và đợt mới. |
| Quay lui | Đặt biến môi trường về đường dẫn cũ. |

### WP7 — G8, A11: một nguồn điều phối, một ngưỡng (US-029, lane normal)

| | |
|---|---|
| Sửa | `pipeline.yaml` mục `ops_loop` liệt kê các bước của đợt. Test đối chiếu danh sách đó với các step thật trong `drive_wave`. `article_tick.py` đọc `sensor.threshold` từ `ops.yaml` thay vì hằng 50, và in cảnh báo rằng nó là công cụ tay, daemon là chủ. |
| Test | `test_G8_pipeline_yaml_matches_drive_wave`; `test_A11_single_threshold` |

### WP8 — S1: siết ops-sentinel (US-029, lane normal; sentinel vẫn draft)

| | |
|---|---|
| Sửa | Sentinel chỉ trả **mã hành động** trong danh mục đóng (`RETRY`, `RESET_AGY`, `PAUSE`, …); daemon tự dựng nhãn nút từ mã, không lấy văn bản LLM làm nhãn. Đặt văn bản chẩn đoán và nút ở hai tin nhắn tách nhau. Ngữ cảnh chỉ còn sự kiện có cấu trúc (kind, level, mã lỗi); bỏ đuôi log tự do, vì log có thể mang tiêu đề bài, tức nguồn prompt injection. |
| Test | `test_S1_action_codes_only`; `test_S1_context_has_no_log_text`; `test_S1_injection_in_event_cannot_create_button` |

### WP9 — R4: bí mật (US-029, lane normal, cần H6)

| | |
|---|---|
| Sửa | `load_secrets` đọc Windows Credential Manager (`keyring`) trước, rồi mới tới `ops.env`. `ops_daemon.py telegram` ghi vào Credential Manager. Thêm phụ thuộc `keyring` vào `requirements.txt`. |
| H6 | Bạn xoay vòng key OpenRouter: key cũ đã nằm trên OneDrive công ty. |
| Test | `test_R4_keyring_preferred` (keyring giả) |

---

## 4. Định nghĩa xong của kế hoạch

1. Mọi test mang mã A6, A8, A11, C6, C12, D13, G8, S1, R4 đạt. Mọi test B1–B7 hiện có vẫn đạt. Toàn bộ test (trừ test ghi DB thật đã biết) đạt 100%.
2. Daemon chạy L1 ít nhất 5 đợt: không trùng bài, không đợt kẹt, cảnh báo tới Telegram.
3. Daemon giữ morninger (`Cào tin: child`).
4. ADR 0012 cập nhật: ngưỡng chất lượng D13, đường dẫn mới (nếu làm WP6), ngân sách tải của probe.
5. SESSION-LATEST, OPEN-ITEMS OPS-1 và trace harness được cập nhật sau từng WP.

## 5. Cổng người, gom một chỗ

| Mã | Việc của bạn | Chặn WP |
|---|---|---|
| H1 | Cho phép commit mốc US-029 (tách US-031) | WP1 |
| H2 | Token Telegram, chat riêng | Cổng L1 |
| H3 | Standing order L1 | Cổng L1 |
| H4 | Cho phép dừng morninger tay | WP5 |
| H5 | Duyệt ADR sửa đổi đường dẫn | WP6 |
| H6 | Xoay vòng key OpenRouter | WP9 |
| — | Duyệt ngưỡng D13 sau khi xem số nền | WP4 |
| — | Tồn đọng 10,8 nghìn bài; story giao hàng | Ngoài kế hoạch |
