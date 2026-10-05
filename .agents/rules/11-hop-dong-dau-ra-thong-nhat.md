# Rule 11 — Hợp đồng đầu ra thống nhất cho mọi provider

> Bất biến cấp dự án. Quyết định: `docs/decisions/0017-hop-dong-dau-ra-article-lane-thong-nhat-moi-provider.md`. Story: US-034.

## 1. Nguyên tắc

Mọi provider đi qua cùng một hợp đồng, một khung đầu vào và một hàm kiểm. Provider chỉ là bộ chuyển vận. Sai lệch bị phát hiện và vào vòng vá, không bị sửa ngầm.

Hợp đồng bảo đảm hình dạng đầu ra, không bảo đảm nội dung ngữ nghĩa giống từng ký tự giữa các model. Độ đồng thuận ngữ nghĩa được đo bằng bộ vàng.

## 2. Luật cứng

1. **Một nguồn chân lý.** `project/schemas/article-compact-v2.schema.json` định nghĩa record gọn `{i,e,s,k,im,sn,ts,c}`. Hằng số đọc qua `project/src/agent/article_contract.py`. Prefix, bộ kiểm và bộ bung không chép tay danh sách trường, enum hay nhóm thực thể. Test `tests/test_article_contract.py` chặn lệch.
2. **Một hàm kiểm.** Mọi runner, adapter và bộ bung gọi `article_contract.parse_and_validate` hoặc `validate_record`. Cấm viết validator, bộ phân tích JSON hay bảng đổi nhóm riêng trong runner.
3. **Cấm mặc định ngữ nghĩa.** Không gán `neutral` cho `sn` sai, không gán `this_week` cho `ts` sai, không tự điền `c`, không đệm `im`, không nhận khoá đồng nghĩa, không tách `k` kiểu chuỗi. Record sai bị từ chối kèm mã lỗi và đi vào `--repair`.
4. **Chuẩn hoá cơ học có đếm.** Chỉ được bóc vỏ truyền tải (envelope, rào mã, lời dẫn, cứu từng đối tượng khi cắt cụt) và đưa về dạng chuẩn (bỏ `e` và `c` trùng, sắp `c` tăng dần, sắp `e` theo nhóm rồi chuỗi). Mọi phép chuẩn hoá ghi bộ đếm vào meta.
5. **Một khung đầu vào.** Tin nhắn người dùng là nguyên văn tệp `.task.json` qua `build_user_message`. Không thêm tiêu đề, không đóng gói lại. Prefix hệ thống là `data/prefix/ARTICLE_SYSTEM_CORE.md`.
6. **Tham số chuẩn.** `SAMPLING` trong `article_contract.py`: `temperature 0`, seed cố định. Provider không hỗ trợ thì ghi `unsupported` vào meta, không tự đổi giá trị.
7. **Meta bắt buộc.** Mỗi lô có tệp meta với `agent_provider`, `model_used`, `sampling`, `contract_version`, bộ đếm vỏ và `domain_errors`. Lô thiếu meta bị `article_expand.py` từ chối, trừ khi `article_run.py` khai provenance cho runner `dsh`.
8. **Một vòng đời.** `pack` → `run` → `parse_and_validate` → `repair` → `expand` → `--finish`. Provider mới hoặc agent kiểu khác nối vào `append_records` hoặc runner, không có đường riêng. `claude` chưa thuộc lane.
9. **Cỡ lô chuẩn 50** (`DEFAULT_BATCH_SIZE`). Cỡ khác chỉ đặt qua `--batch`, có ghi chú lý do.
10. **Provider mới qua bộ vàng.** Chấm bằng `provider_conformance.py`. Chuẩn đo là agy.

## 3. Giới hạn của record gọn

| Trường | Luật |
|---|---|
| `i` | số nguyên có trong packet, không lặp |
| `e` | cặp `[chuỗi, mã nhóm]` với 11 mã nhóm; `IND` được phát tên ngành chuẩn, nhóm khác phải là chuỗi con nguyên văn |
| `s` | 1 đến 3 câu, tiếng Việt có dấu (quá 3 câu chỉ cảnh báo) |
| `k` | mảng đúng 2 đến 4 chuỗi |
| `im` | từ 40 ký tự |
| `sn` | `pos`, `neg`, `neu` |
| `ts` | `urg`, `today`, `week`, `month`, `arch` |
| `c` | 2 đến 4 chỉ số 0-based, mỗi chỉ số trỏ vào đoạn có từ 20 ký tự; bài chỉ có một đoạn đủ dài thì 1 chỉ số |
| khoá khác | bị từ chối |

## 4. Lệnh thực thi

```powershell
python -m pytest tests/test_article_contract.py tests/test_openrouter_runner.py tests/test_conformance.py -q
python scripts/build_article_prefix.py --check        # prefix khớp catalog và persona trong preset
python scripts/provider_conformance.py baseline --gold <vàng.json> --batches <lô,lô>   # ghi mức agy
python scripts/provider_conformance.py check    --gold <vàng.json> --batches <lô,lô>   # so provider khác với agy
```

## 5. Khi đổi hợp đồng

Sửa schema trước, rồi chạy `build_article_prefix.py` và đồng bộ `persona` trong `agent.cordis.yml`. Preset nạp lúc mount, nên phải restart host DSH và mở phiên mới (rule 09). Lập ADR mới cho thay đổi lược đồ.
