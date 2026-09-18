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

### Bước 1 — một lệnh chuẩn bị

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/article_run.py --wave W01 --today --limit 300',
  description: 'Chuẩn bị đợt'
});
return r.stdout.text;
```

Lệnh này kiểm prefix, đóng gói packet, in dự toán và **sinh sẵn chương trình** cho bước sau. Nó không tiêu token mô hình.

### Bước 2 — một lệnh chạy mô hình

Đọc tệp `project/data/agent_tasks/article/wave_<mã>.conductor.ts` rồi chạy **trọn nội dung** trong **một** lệnh `run_code`.

Chương trình đó đã tự lo: phân trang đọc packet, chạy lô đầu một mình để ghi bộ nhớ đệm, rồi mới song song phần còn lại, ghi kết quả thẳng ra đĩa, và chỉ trả về vài con số.

**Đừng tách nó ra.** Đừng đọc packet ở một bước rồi gọi agent ở bước khác. Đừng in nội dung packet hay đầu ra của lô.

### Bước 3 — một lệnh hoàn tất

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/article_run.py --wave W01 --finish',
  description: 'Hoàn tất đợt'
});
return r.stdout.text;
```

Bung bản ghi, nạp cơ sở dữ liệu, ghi sổ cái token, sinh bàn giao, đo áp suất ngữ cảnh — tất cả trong một lệnh.

---

## Bất biến

1. **Không hỏi xác nhận.** ADR 0008 đã được sửa ngày 2026-09-18: lệnh đợt do người vận hành gõ tường minh **là** quyết định rồi. Không trình cổng, không đề nghị duyệt, không chờ. Hai chốt duy nhất là tự động và nằm trong script.
2. **Không để nội dung lô vào ngữ cảnh.** Chỉ `print` và `return` mới vào lịch sử. Kết quả của lô ghi thẳng ra đĩa. Một đợt trăm bài chỉ nên để lại vài chục token trong ngữ cảnh của bạn.
3. **Không đọc lại tệp vừa ghi.** Việc kiểm định thuộc về cổng nghiệm thu ngoài, vốn làm cùng việc đó với chi phí bằng không.
4. **Không đọc mã nguồn để suy ra hợp đồng.** Hợp đồng nào cũng có lệnh in ra. Nếu chưa có thì báo, đừng đi đào.
5. **Không tự làm việc của script.** Việc nào có câu trả lời đúng duy nhất và kiểm được bằng mã thì script làm.
6. **Đóng phiên khi áp suất tới mức vàng.** Mở phiên mới rẻ hơn mang theo ngữ cảnh đã phình, vì bộ nhớ đệm nằm ở phía nhà cung cấp chứ không gắn với phiên.

---

## Bốn dấu hiệu cần báo ngay

Sau mỗi đợt, `article_run.py --finish` in ra các số này. Thấy bất thường thì **nêu rõ trong báo cáo**, đừng bỏ qua.

| Dấu hiệu | Nghĩa là gì |
|---|---|
| `turns_max > 1` | Worker sa vào viết chương trình thay vì trả lời thẳng. Persona cần sửa |
| `reasoning > 0` | Chế độ suy luận chưa tắt, đang tính tiền theo giá đầu ra |
| token mỗi bài vượt 1.500 | Hoặc mốc quy kết gộp nhầm phiên khác, hoặc packet quá dày |
| áp suất vàng hoặc đỏ | Đọc bàn giao rồi đóng phiên |

---

## Khi cần trinh sát

Một lệnh duy nhất, không tự nghĩ ra chuỗi lệnh khác:

```ts
const r = await tools.pwsh({
  command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/pipeline_radar.py status',
  description: 'Radar'
});
return r.stdout.text;
```

---

## Quay lui

Đường L1 và Gold cũ vẫn gọi được qua `agent_l1` và `agent_gold`. Chỉ dùng khi đường mới trượt nghiệm thu hai đợt liên tiếp, và báo rõ lý do khi dùng.
