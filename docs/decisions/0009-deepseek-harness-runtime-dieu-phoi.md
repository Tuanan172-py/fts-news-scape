# ADR 0009 — DeepSeek Harness làm runtime điều phối mạng lưới agent News-Scape

- **Ngày:** 2026-09-17
- **Trạng thái:** **accepted** (người dùng duyệt toàn bộ plan 2026-09-17, chốt D1–D6)
- **Lane:** **high-risk** — chạm Harness Core / automation substrate
- **Story:** US-020 (H1) → US-023 (H4), mỗi phase một story theo rule 07 §4
- **Kế hoạch:** `plans/20260917-1538-dsh-harness-integration/plan.md`
- **Đề xuất gốc:** `docs/proposals/dsh-harness-mapping-2026-09-17.md`

---

## 1. Bối cảnh & Vấn đề

Ba spine dữ liệu (registry/pipeline/metrics) đã chín nhưng thiếu runtime LLM: `OPEN-ITEMS C2` xác nhận không module nào gọi API LLM; `A0-6` ghi nhận `agy.exe --dangerously-skip-permissions` nằm ngoài repo, không pin version, không tái lập. US-016…US-019 đã khắc phục lỗi toàn vẹn dữ liệu và dựng mô hình kéo theo nhu cầu (Q5). ADR 0008 đặt yêu cầu người-trong-vòng-lặp + trần token.

## 2. Quyết định

### 2.1 DSH là runtime điều phối
Dùng DSH (agent presets + in-process subagent + PTC + hook pipeline) làm runtime điều phối. `registry.yaml`, `pipeline.yaml`, `harness.db`, `.agents/skills` giữ vai trò nguồn chân lý; composition DSH được SINH từ chúng (generator ở H3).

### 2.2 Cognitive agent là subagent in-process (Option A)
Mỗi cognitive agent là một instance `dsh-tool-subagent` với `provider: spawn`, `persona` riêng, `toolFilter` và `maxDepth` theo vai. Agent con kế thừa composition của cha; ranh giới per-agent nằm ở cấu hình instance, không phải preset riêng.

> **AMENDMENT 2026-09-18 — sửa `maxDepth: 0` thành `maxDepth: 1`.**
>
> Bản gốc quy định `maxDepth: 0` với ý định "chặn đệ quy". Đọc lại mã nguồn DSH 0.1.5 cho thấy hiểu như vậy là **sai**: `dsh-subagent/lib/types/child-agent.js:32-41` tính `childDepth = delegationDepthOf(parent) + 1`, nên **con đầu tiên đã ở depth 1**, và `1 > 0` khiến mọi lời gọi ném `SubagentDepthError`. README của `dsh-tool-subagent` dòng 53 ghi thẳng: *"`0` forbids delegation"*.
>
> **Hệ quả đã xảy ra:** `agent_l1` và `agent_gold` **chưa bao giờ spawn được** kể từ khi preset ra đời. Đây là một trong hai lý do phiên 17/09 phải chạy bằng `subagent` generic (lý do còn lại là phiên sai preset), và vì `subagent` generic không có `toolFilter` nên toàn bộ ranh giới 2-I/O bị mất — dẫn thẳng tới vệt 845K token.
>
> **Sửa:** dùng `maxDepth: 1` — cho đúng một tầng con, cháu vẫn bị chặn, đạt đúng ý định ban đầu.
>
> **Bổ sung — `toolFilter` không cưỡng chế được như bản gốc mô tả.** `dsh-tools/lib/index.js:2874` chèn `run_code` vào tập tool nhìn thấy **sau** lớp lọc `toolFilter`, và `:2800` ném lỗi nếu `restrict()` cố đặt tên `run_code`. Dưới `mode: ptc`, con với `allow: []` vẫn có `run_code`, chỉ khác là SDK bên trong rỗng nên nó không chạm được file. Ranh giới vẫn đạt, nhưng tiêu chí kiểm là **"sdkSchemas rỗng" và "turns == 1"**, không phải "0 tool".
>
> **Bổ sung — không đặt được `mode` cho con.** Schema row subagent có đúng 9 khoá (`dsh-tool-subagent/lib/index.js:252-270`), không có `mode`. Con kế thừa mode của cha, nên Conductor bắt buộc giữ `ptc`.
>
> Neo: `plans/20260918-1651-article-lane-unified/plan.md` §3.1, §4.2.

### 2.3 Chỉ dùng model họ DeepSeek Flash 4.1
Mọi route agent = `deepseek-official/deepseek-flash` (`DeepSeek-V41-Flash`). Cấm `deepseek-v4-pro` vì chi phí token. Bốn agent `pro` trong registry hạ về flash; `entity-curator` vẫn giữ Tier-3 gate.

### 2.4 Cổng cấp quyền ADR 0008 được cưỡng chế
Trước mọi lần tiêu token: hiển thị số batch, số bài, model, ước lượng token, effort; mặc định hỏi. Trần L1 60.000, Gold 40.000 token mỗi lần. H3 biến cổng thành tool `ns_activate` hard-enforce.

### 2.5 PTC + fallback native
Conductor ở `mode: ptc`. Van wave do script điều phối giữ, không do cấu hình harness.

> **AMENDMENT 2026-09-18 — gỡ `maxParallelSubCalls: 3` và gỡ phương án fallback native.**
>
> **Gỡ `maxParallelSubCalls: 3`.** Tham số này **chưa từng được cấu hình ở đâu** trong repo hay trong profile DSH; giá trị thực tế luôn là mặc định **10**. Nó cũng **không thuộc row subagent** mà thuộc row `@deepseek-ai/dsh-tools` ở host-plane (`dsh-tools/lib/index.js:2575`), nên preset không đặt được.
>
> Lý do gốc của van wave là chống lỗi 429. Lý do đó **hết hiệu lực**: DeepSeek **không có giới hạn TPM/RPM**, chỉ giới hạn concurrency ở mức 2.500 cho `deepseek-flash` — cao hơn nhu cầu của hệ này ba bậc độ lớn.
>
> **Thay bằng:** van wave nằm ở `project/scripts/article_run.py` (`--concurrency`, mặc định 3), tức trong mã của dự án, nơi đọc được và test được. Không đụng host config.
>
> **Gỡ fallback native.** Bản gốc nêu "nếu chất lượng flash dưới PTC không đạt thì fallback native". Phương án này **không còn khả dụng**: dưới `native`, kết quả sub-call đi thẳng vào context của Conductor, nên mỗi batch sẽ đổ ~30.000 token vào phiên điều phối. `ptc` là điều kiện cần của kiến trúc, không phải một tuỳ chọn hiệu năng.
>
> Neo: `plans/20260918-1651-article-lane-unified/plan.md` §4.2 R1, §16.

### 2.6 Lộ trình đóng gói
H1–H2 wiring bằng `cordis.patch.yml`; H3–H4 đóng gói bundle local `@news-scape/dsh-harness`.

### 2.7 `agy` giữ làm option, không phải mặc định
Đường mặc định dùng DSH; `auto_pilot.py`/`agy` được giữ như runner thay thế có thể thực thi, chưa thực thi, kiểm chứng chất lượng để sau. Mọi runner đều phải qua ADR 0008.

## 3. Phương án đã cân nhắc

| Phương án | Vì sao không chọn |
|---|---|
| Giữ `agy` làm mặc định | Không tái lập, không có cổng người, không cưỡng chế 2-I/O |
| Mỗi agent một preset top-level (Option B) | Nhiều process, điều phối nặng; DSH vốn cho con kế thừa composition |
| Tự viết runner LLM trong repo | Trùng lặp với DSH; không có sẵn preset/skill/hook |
| Dùng `deepseek-v4-pro` cho QA/brief | Vượt ngân sách token (D6) |

## 4. Hệ quả

**Tích cực:** tự động hoá cognitive có kiểm soát; 2-I/O, wave, gate, WIP, metric cưỡng chế bằng máy; skill dự án tự nạp; thay runner ngoài repo không tái lập.

**Tiêu cực / quản trị:** phụ thuộc runtime DSH ngoài repo (phải pin version); chất lượng QA/brief trên flash chưa kiểm chứng (đo ở H4); child kế thừa PTC; cần amendment registry.

## 5. Nghiệm thu

| Tier | Điều kiện |
|---|---|
| Unit | Generator sinh byte-identical; `ns_activate` không xác nhận thì không spawn |
| Integration | Child chỉ thấy `read`/`write`; guard gate/WIP chặn đúng |
| **Platform** | H1: DB hash không đổi. H2: 1 wave L1 DoD ≥ 95% + metric. H4: toàn workflow 17/09 trên DB vận hành, 0 model ngoài flash |
