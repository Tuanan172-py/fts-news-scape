---
name: dsh-conductor
description: Điều phối đợt xử lý bài đăng trên DSH — chạy trọn một đợt trong một bước, không hỏi xác nhận, không để nội dung lô lọt vào ngữ cảnh.
---

# DSH Conductor — News-Scape

## Nguồn chân lý

- `.agents/dsh/RUNBOOK-article-lane.md` — quy trình vận hành, đọc cái này trước
- `plans/20260918-1651-article-lane-unified/plan.md` — thiết kế và lý do
- `docs/proposals/dsh-surface-verified-2026-09-18.md` — bề mặt DSH kèm số dòng mã nguồn
- `.agents/pipeline.yaml` · `.agents/registry.yaml` — DAG và danh sách tác nhân

---

## Điều quan trọng nhất: chi phí tỉ lệ với SỐ BƯỚC

Mỗi bước gửi lại **toàn bộ** lịch sử đã tích luỹ, và DSH không cắt tỉa gì trước ngưỡng nén 80%. Nên chi phí của bạn tăng theo **bình phương số bước**, không theo số bài.

Con số thật đo được: một đợt 25 bài chạy 19 bước tốn 845 nghìn token, trong khi nội dung duy nhất chỉ 82 nghìn. Hệ số lãng phí 12 lần, và toàn bộ đến từ số bước.

Hệ quả thực hành: **gộp mọi thứ vào ít bước nhất có thể**. Một đợt nên là một bước.

---

## Chạy một đợt

### Bước 0 — radar chỉ lệnh, không tự nghĩ lệnh

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/pipeline_radar.py status',
  description: 'Radar'
});
return r.stdout.text;
```

Radar đọc trạng thái đợt gần nhất rồi in **đúng một lệnh kế tiếp**: chạy chương trình điều phối, `--repair`, `--finish`, mở đợt mới với đúng số bài đang chờ, hoặc giao hàng. Chạy lệnh ấy. Radar cũng in dòng `Cơ sở dữ liệu: ✅/❌` cho **đúng phiên đang chạy**. Dưới `workspace-write` dòng này luôn là ❌, và đó là bình thường: DB nằm ngoài kho, không cấu hình nào mở rộng được quyền ghi. Chuẩn bị đợt, chạy mô hình và `--repair` vẫn làm được. Chỉ `--finish` và giao hàng cần `danger-full-access`.

Mọi lệnh `scripts/...` chạy với **cwd = `project/`**. Cần đường dẫn, cwd hay quyền ghi DB thì hỏi `scripts/article_run.py --where`. Lệnh này trả lời trong một bước, 0 token.

### Bước 1 — một lệnh chuẩn bị

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/article_run.py --wave W01 --today --limit 1000',
  description: 'Chuẩn bị đợt'
});
return r.stdout.text;
```

Lệnh này kiểm prefix, đóng gói packet, in dự toán và **sinh sẵn chương trình** cho bước sau. Nó không tiêu token mô hình. Nếu phiên không ghi được DB, lệnh in một dòng ⓘ nhắc trước rằng `--finish` phải chạy với `danger-full-access`, nhưng không chặn.

**Cỡ lô tự chọn; không cần truyền `--batch`.** Bỏ cờ này thì đợt tự tính `batch = clamp(ceil(số_bài / 10), 100, 500)`, giữ số lô bằng đúng `maxParallelSubCalls` mặc định của DSH là 10. Mọi đợt tới 5.000 bài chạy trọn trong **một sóng song song**: 415 bài → 5 lô, 1.000 → 10 lô, 2.000 → 10 lô × 200 bài.

**Không có gate token nào.** `maxTokens` 256.000 là `max_tokens` của một request, không phải cổng chặn đợt. Chạm mốc ấy thì adapter ánh xạ `finish_reason: "length"` thành `{kind:"max-tokens"}`, vòng lặp agent kết thúc turn **bình thường không lỗi**, và `salvage_records` bóc mọi bản ghi hoàn chỉnh đã sinh; phần thiếu do `--repair` vá. Con số token trong dự toán là **ước lượng**, không phải trần.

Đừng bao giờ đề nghị hạ số bài mỗi đợt, và đừng tự chia nhỏ lô để phòng cắt cụt. Chia lô ở đây để **chạy song song cho nhanh**, không phải để né trần token. Nếu lô trả về thiếu bài thì chạy `article_run.py --wave <mã> --repair`: nó đóng gói lại **đúng phần thiếu** rồi sinh chương trình chạy bù. Vá sau rẻ hơn phòng trước, vì phòng trước thì trả giá ở mọi đợt còn vá thì chỉ trả cho phần thật sự mất.

### Bước 2 — một lệnh chạy mô hình

Đọc tệp `project/data/agent_tasks/article/wave_<mã>.conductor.ts` rồi chạy **trọn nội dung** trong **một** lệnh `run_code`.

Chương trình đó đã tự lo: đọc trọn **mọi** packet trước, hâm bộ nhớ đệm bằng một lượt tí hon, chạy mọi lô song song, ghi kết quả thẳng ra đĩa, và chỉ trả về vài con số.

Kết quả có khoá `stopped` nghĩa là đọc packet hỏng và **chưa lượt gọi mô hình nào chạy**. Trường `failed[].why` nói rõ công cụ đọc trả về kiểu gì. Báo nguyên văn lỗi đó; **đừng tự sửa tệp `.ts`**. Chương trình là mã sinh ra, lỗi của nó phải vá ở `article_run.py` để không lặp lại ở đợt sau.

**Đừng tách nó ra.** Đừng đọc packet ở một bước rồi gọi agent ở bước khác. Đừng in nội dung packet hay đầu ra của lô.

### Bước 2b — vá phần thiếu, chỉ khi có

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/article_run.py --wave W01 --repair',
  description: 'Vá phần thiếu'
});
return r.stdout.text;
```

Không thiếu bài thì lệnh báo ngay, không sinh việc thừa. Có thiếu thì chạy trọn `wave_<mã>.repair.ts` trong một lệnh `run_code`, rồi mới sang bước hoàn tất.

### Bước 3 — một lệnh hoàn tất

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/article_run.py --wave W01 --finish',
  description: 'Hoàn tất đợt',
  sandbox_permissions: 'danger-full-access',
  justification: 'Nạp kết quả vào DB C:\\data\\news-scape\\monocle.db, nằm ngoài kho mã'
});
return r.stdout.text;
```

Bung bản ghi, nạp cơ sở dữ liệu, **hậu kiểm theo đúng tập bài của đợt**, ghi sổ cái token, sinh bàn giao, đo áp suất ngữ cảnh — tất cả trong một lệnh.

Đợt chỉ xong khi lệnh **thoát 0 và in `✅ ĐỢT <mã> HOÀN TẤT`**. Thấy `❌ ĐỢT <mã> CHƯA HOÀN TẤT` thì đọc lý do, rồi chạy đúng lệnh mà khung ấy in ra, thường là `--finish --only ingest,verify,ledger,handoff`. Đừng chạy lại cả `--finish` và đừng tự nạp tay.

Khi báo cáo độ phủ, lấy số từ **bảng hậu kiểm của đợt** (`nhận diện thực thể`, `phân tích nội dung`). Từ 23/09, hai lệnh nạp chỉ nhận tệp của đúng đợt, nên dòng `ingested: done=… failed=…` cũng là số của đợt. Trước đó chúng quét cả thư mục, và đợt W365 đã báo nhầm "L1 failed=123" từ đúng dòng ấy.

### Bước 4 — giao hàng

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/write_user_output.py --date today',
  description: 'Giao hàng',
  sandbox_permissions: 'danger-full-access',
  justification: 'Đọc DB ngoài kho mã và ghi users/output'
});
return r.stdout.text;
```

Script nằm ở `project/scripts/` như mọi script khác. Chỉ **thư mục đầu ra** `users/output/` là nằm ở gốc kho.

---

## Bất biến

1. **Không hỏi xác nhận.** ADR 0008 đã được sửa ngày 2026-09-18: lệnh đợt do người vận hành gõ tường minh **là** quyết định rồi. Không trình cổng, không đề nghị duyệt, không chờ. Hai chốt duy nhất là tự động và nằm trong script.
2. **Không để nội dung lô vào ngữ cảnh.** Chỉ `print` và `return` mới vào lịch sử. Kết quả của lô ghi thẳng ra đĩa. Một đợt trăm bài chỉ nên để lại vài chục token trong ngữ cảnh của bạn.
3. **Không đọc lại tệp vừa ghi.** Việc kiểm định thuộc về cổng nghiệm thu ngoài, vốn làm cùng việc đó với chi phí bằng không.
4. **Không đọc mã nguồn để suy ra hợp đồng.** Hợp đồng nào cũng có lệnh in ra: `scripts/article_run.py --where` cho DB, quyền ghi, cwd và thư mục đợt; `scripts/write_user_output.py --where` cho thư mục giao hàng. Nếu câu hỏi chưa có lệnh trả lời thì báo thiếu lệnh, đừng đi đào. Vệt ngày 21/09 tốn khoảng tám bước để chẩn đoán lỗi ghi DB và dò đường dẫn, trong khi `--where` trả lời cả hai trong một bước.
5. **Không tự làm việc của script.** Việc nào có câu trả lời đúng duy nhất và kiểm được bằng mã thì script làm.
6. **Đóng phiên khi áp suất tới mức vàng.** Mở phiên mới rẻ hơn mang theo ngữ cảnh đã phình, vì bộ nhớ đệm nằm ở phía nhà cung cấp chứ không gắn với phiên.

---

## Dấu hiệu cần báo ngay

Sau mỗi đợt, `article_run.py --finish` in ra các số này. Thấy bất thường thì **nêu rõ trong báo cáo**, đừng bỏ qua.

| Dấu hiệu | Nghĩa là gì |
|---|---|
| `❌ ĐỢT … CHƯA HOÀN TẤT` | Bước ghi hỏng hoặc độ phủ của đợt dưới 90%. Chạy đúng lệnh khung đó in ra |
| `turns_max > 1` | Worker sa vào viết chương trình thay vì trả lời thẳng. Persona cần sửa |
| `reasoning > 0` | Chế độ suy luận chưa tắt, đang tính tiền theo giá đầu ra |
| lô trả về thiếu bài | Lượt đó bị cắt cụt — chạy `--repair`, đừng chia nhỏ mọi lô |
| áp suất vàng hoặc đỏ | Đọc bàn giao rồi đóng phiên |

### Token là số ghi nhận, không phải cổng

**Không có giới hạn token nào**, theo bài, theo lô hay theo đợt, và không có mức cảnh báo token nào. Sổ cái ghi token và USD để người dùng tự đánh giá, tự ước lượng. Khi báo cáo, chép nguyên các con số của sổ cái. **Đừng** nhận xét chúng là "cao", "vượt" hay "bất thường", **đừng** đề nghị giảm số bài hay chia nhỏ lô vì token, và **đừng** dừng đợt vì token.

Sổ cái chỉ tính **phiên worker được tạo sau mốc đóng gói** (`--workers-only`). Dòng sổ cái trước 23/09 gộp cả phiên điều phối sống lâu, nên W365 từng ghi 25.628 token/bài và `turns_max=12`; số của riêng worker là khoảng 2.850 token/bài và `turns_max=1`. Tỷ lệ trúng cache của worker khoảng 9%: mỗi lô tái dùng phần tiền tố tĩnh (khoảng 10 nghìn token), còn nội dung bài luôn là token mới.

---

## Lane cũ đã ngừng

Article Lane là đường xử lý duy nhất (ADR 0010). Không gọi `l1_route.py`, `l1_ingest.py --code-first` hay `requeue.py`, kể cả khi thấy chúng trong tài liệu cũ. Row `agent_l1`/`agent_gold` đã gỡ khỏi preset. Tệp tồn của lane cũ nằm ở `data/archive/legacy-lane-20260923/`, không phải việc của đợt.

---

## Vai kiểm toán tách khỏi vai điều phối

Bất biến 4 và 5 ràng buộc **phiên điều phối**. Việc đánh giá một đợt sau khi chạy xong là vai khác: phiên kiểm toán được phép đọc mã nguồn và truy vấn chỉ đọc, vì nhiệm vụ của nó chính là tìm chỗ hợp đồng lệnh còn hổng. Phát hiện của phiên kiểm toán phải kết thúc bằng một lệnh hoặc một bản vá cho script, không phải một lời nhắc "đừng làm vậy nữa" gửi phiên điều phối.
