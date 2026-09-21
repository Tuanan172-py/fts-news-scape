# Những việc chỉ làm được bằng tay trong DSH

|                       |                                                                                                                                                                                                                                                                                                                                                                |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lập                  | 2026-09-21                                                                                                                                                                                                                                                                                                                                                     |
| Vì sao có tệp này | Đợt tối ưu bộ nhớ đệm 21/09 sửa được phần nằm trong kho mã. Phần còn lại nằm trong runtime DSH — preset đã nạp, cấu hình toàn cục, việc chọn preset khi mở phiên — và không script nào của dự án với tới được. Liệt kê ra đây để chúng không rơi vào khoảng trống giữa "đã sửa" và "chưa ai làm" |
| Liên quan            | [`RUNBOOK-article-lane.md`](RUNBOOK-article-lane.md) · [`RUNBOOK.md`](RUNBOOK.md) · `docs/proposals/dsh-surface-verified-2026-09-18.md` · skill `dsh-preflight-validator`                                                                                                                                                                                    |
| Kiểm chứng lần cuối  | 2026-09-21 — đối chiếu `%USERPROFILE%\.dsh\settings.yaml`, junction preset, `StartTime` tiến trình cổng 3080, `--check-prefix`                                                                                                                                                                                                                              |

Mỗi mục ghi rõ **bắt buộc** hay **tuỳ chọn**, và hậu quả nếu bỏ qua.

> **Quy tắc chống mục cho tệp này.** Mỗi giá trị runtime chép vào đây phải kèm **ngày đo** và **lệnh kiểm**. Tệp từng mục vì ba giá trị (`ptc`, `standard`, `high`) được chép vào mà không có cách nào kiểm lại — kiểm ngày 21/09 cho thấy **cả ba đều sai**.
>
> Cổng nghiệm thu tự động cho toàn bộ checklist: skill `dsh-preflight-validator` (`.agents/skills/dsh-preflight-validator/SKILL.md`) — 12 hạng mục, chạy trong một lệnh, 0 token.

---

## 1. Dán persona sau mỗi lần sinh lại prefix — **bắt buộc**

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" scripts/build_article_prefix.py
# chép trọn project/data/prefix/ARTICLE_SYSTEM_CORE.md vào `persona`
# của row `tool-subagent-article` trong .agents/dsh/presets/news-scape-conductor/agent.cordis.yml
& "C:\venvs\news-scape\Scripts\python.exe" scripts/build_article_prefix.py --check-preset
```

Bộ nhớ đệm khớp theo tiền tố tính từ token 0. Lệch một khoảng trắng là **mọi** token sau chỗ lệch bị tính giá token mới, đắt hơn năm mươi lần, mà kết quả nghiệp vụ vẫn đúng nên không có triệu chứng nào khác.

Hai cái bẫy đã gặp ở loại thao tác này: trình soạn thảo tự thụt lề lại khối YAML, và chép thiếu dòng cuối. Cả hai đều bị `--check-preset` bắt trong một giây. Hiện tại persona đang khớp — đã kiểm bằng máy ngày 21/09, `19.029` ký tự, không lệch dòng nào.

## 2. Chọn đúng preset khi mở phiên — **bắt buộc, mỗi phiên**

Settings → General → Agent preset → **News-Scape Conductor**.

Mặc định toàn cục **đã đúng** — kiểm ngày 21/09, `%USERPROFILE%\.dsh\settings.yaml` khai `agent-presets.default: news-scape-conductor`. Nhưng **không tin mặc định**: preset là trạng thái **theo từng phiên**, ghi đè được, và phiên đang mở vẫn giữ preset cũ sau khi mặc định đổi. Chạy sai preset là mất toàn bộ ranh giới công cụ của agent con; đây đúng là nguyên nhân gốc của vệt 845 nghìn token ngày 17/09.

Kiểm bằng máy, đừng đọc tệp:

```powershell
Get-Content "$env:USERPROFILE\.dsh\settings.yaml" | Select-String "default:|reasoningEffort"
```

Sai preset còn làm vỡ cache theo một đường riêng: bộ tool khác nhau thì system prompt khác nhau, nên tiền tố không còn giống đợt trước.

## 3. Nạp lại DSH sau khi sửa preset — **bắt buộc**

Preset được nạp lúc mount. Sửa `agent.cordis.yml` xong mà không khởi động lại thì phiên đang mở vẫn chạy bản cũ — và tệ hơn, hai phiên chạy hai bản persona khác nhau sẽ trượt cache của nhau.

Đây là **trạng thái hỏng im lặng**: YAML đúng, prefix đúng, junction đúng, không lỗi nào nổi lên — chỉ có hoá đơn sai. Ngày 18/09 host khởi động lúc 17:46 còn `agent.cordis.yml` được sửa lúc 21/09 13:43, nghĩa là toàn bộ đợt tối ưu bộ nhớ đệm **chưa từng có hiệu lực** mà không ai thấy.

Không tự biết được "đã nạp lại chưa" bằng cách đọc tệp. Phải so hai mốc thời gian:

```powershell
$p = (Get-NetTCPConnection -LocalPort 3080 -State Listen).OwningProcess
"server : " + (Get-Process -Id $p).StartTime
"preset : " + (Get-Item ".agents\dsh\presets\news-scape-conductor\agent.cordis.yml").LastWriteTime
```

**Đạt khi dòng `server` mới hơn dòng `preset`.** Ngược lại thì bản sửa chưa vào, phải dừng host rồi mở lại.

Trình tự: `Ctrl+C` ở cửa sổ đang chạy `npx @deepseek-ai/dsh web` → chạy lại `npx @deepseek-ai/dsh web` → mở phiên mới đúng preset. **Không có cách nào để agent tự làm ba bước này**: nó chạy bên trong chính tiến trình cần khởi động lại, nên kill host là tự sát giữa lượt.

## 4. Giữ nguyên tool set, model và effort trong suốt một đợt — **bắt buộc**

Đổi bất cứ thứ nào trong ba thứ này giữa chừng là đổi system prompt, tức vỡ tiền tố. Nếu cần đổi, đổi **giữa hai đợt**, không đổi giữa đợt.

## 5. `compaction` cho worker — **đã quyết: giữ `auto: true`**

Plan §8.4 đề xuất tắt nén tự động cho phiên worker, vì nén viết lại vùng surface và làm mất cache từ điểm viết lại.

Tôi **không tự sửa** vì một lý do kỹ thuật: con dùng chung composition với Conductor (`R2`), mà row `compaction-basic` không có khoá phân biệt cha con. Đặt `auto: false` là tắt nén cho **cả Conductor**.

Đánh đổi thật:

- Worker chạy đúng một bước, đỉnh ngữ cảnh khoảng 12% cửa sổ — nó không bao giờ chạm ngưỡng nén 80%, nên tắt hay không với nó không khác gì.
- Conductor được thiết kế để ở dưới 25%, nhưng nếu có gì bất thường làm nó phình thì nén là lưới an toàn cuối cùng. Tắt đi là chọn để phiên chết thay vì tự cắt.

**Quyết định: giữ nguyên `auto: true`** — và preset hiện đã đúng như vậy: row `compaction-basic` trong `agent.cordis.yml` không đặt `config`, nên thừa hưởng mặc định `true`. Không cần sửa gì thêm.

Lợi ích cache bằng không trong mọi tình huống bình thường, còn cái mất là lưới an toàn duy nhất. Nếu sau này muốn tắt, sửa row `compaction-basic` thành `config: { auto: false }` — nhưng đọc lại đánh đổi ở trên trước.

## 6. `maxParallelSubCalls` nếu chạy quá 10 lô song song — **tuỳ chọn**

Mặc định là **10**, và nó thuộc row `dsh-tools` ở host plane chứ không thuộc row subagent — preset của dự án không đặt được. Đợt hiện tại chạy 1–3 lô nên chưa chạm. Khi nào một đợt vượt 10 lô thì phần dư xếp hàng chờ, không lỗi, chỉ chậm.

## 7. Kiểm `reasoningEffort` sau mỗi lần nâng cấp DSH — **bắt buộc khi nâng cấp**

Bản ghi cũ nói `.dsh/settings.yaml` (tệp này **không tồn tại** — cấu hình thật nằm ở `%USERPROFILE%\.dsh\settings.yaml`) để `high`; kiểm ngày 21/09 cho thấy **đã là `off`**:

```yaml
# %USERPROFILE%\.dsh\settings.yaml
agent-default-model:
  reasoningEffort: off
```

Row worker vẫn đè bằng `"off"` (có dấu nháy — YAML đọc `off` trần thành boolean). Hiện nó đè lên `off`, tức vô hại; giữ lại làm chốt phòng khi mặc định toàn cục đổi.

Lý do phải kiểm lại **sau mỗi lần nâng cấp DSH**: nâng cấp có thể đổi cách hợp nhất cấu hình, và khoá YAML gõ sai bị **bỏ qua im lặng**. Dấu hiệu hỏng duy nhất: cột `reasoning` trong sổ cái khác 0.

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py report --date today
```

> **Đừng tin tệp, tin runtime.** Cách duy nhất chắc chắn là khẳng định tập tool hiệu lực và `sdkSchemas` ngay trong phiên, vì YAML sai không báo lỗi.

## 8. Chạy chương trình điều phối trong **một** lệnh `run_code` — **bắt buộc, mỗi đợt**

Chi phí phiên điều phối tỉ lệ với số bước. Tách chương trình thành nhiều bước là nhân chi phí mà không được gì.

## 9. Xếp lịch đợt bulk vào giờ thấp điểm — **tuỳ chọn, giá trị lớn nhất trong danh sách này**

Off-peak rẻ hơn **50% ở cả ba rổ token**. Cao điểm là 08:00–11:00 và 13:00–17:00 giờ VN, T2–T6; mọi khung khác kể cả cuối tuần đều rẻ một nửa.

Đo trên đợt 300 bài: `$0,233` off-peak so với `$0,466` peak. Chênh lệch ấy lớn gấp khoảng **36 lần** toàn bộ phần tiết kiệm mà tối ưu tiền tố mang lại cho cùng đợt. Chỉ Tier 1 mới đáng trả giá cao điểm để đổi độ trễ.

## 10. Thí nghiệm digest mã chứng khoán trong prefix — **tuỳ chọn**

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/build_article_prefix.py --with-tickers
# dán persona mới, --check-preset, chạy một đợt, rồi so resolve_rate nhóm COM/TIC
```

Thêm trọn 1.093 mã nặng khoảng **21.500 token** mỗi lượt gọi, nhưng nằm trong phần trúng cache nên đợt 300 bài chỉ đắt thêm khoảng **1,5%**. Đây là cách dùng cache đúng hướng: cache biến prefix thành **ngân sách tri thức**, không phải khoản giảm giá để thu.

Biến thể được ghi vào tệp mô tả nên `--check` tự dựng lại đúng biến thể, không báo lệch oan. Muốn quay về thì chạy lại lệnh sinh không kèm cờ, rồi dán lại persona.

Điều kiện để giữ: `resolve_rate` nhóm `COM` và `TIC` tăng đo được. Nếu không tăng thì bỏ — 21.500 token vẫn là 21.500 token của cửa sổ ngữ cảnh.

---

## Đã cân nhắc và **không** làm

**Vá bằng cách gửi lại trọn packet gốc.** Ý tưởng: thay vì đóng gói lại phần thiếu, gửi lại nguyên packet cũ kèm một dòng ở đuôi "chỉ trả về các bài còn thiếu", để cả packet trúng cache. Số học không ủng hộ: vá 8 bài trên 100 hiện tốn khoảng `$0,0019` token đầu vào; cách kia tốn `$0,0005`. Tiết kiệm `$0,0014`, đổi lấy rủi ro mô hình hiểu sai và phát lại trọn 100 bản ghi — tức `$0,054` đầu ra, đắt hơn ba mươi lần phần vừa tiết kiệm. Giữ nguyên cách vá hiện tại.
