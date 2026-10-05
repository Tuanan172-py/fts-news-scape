# Bề mặt DSH đã xác minh — 2026-09-18

|  |  |
| --- | --- |
| Loại tài liệu | **Tham chiếu kỹ thuật tĩnh.** Không phải plan, không hết hạn theo plan |
| Nguồn | `%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai` — DSH `0.1.5` |
| Vì sao nằm ở đây | Trích từ `plans/20260918-1624-dsh-token-economy-workmethod/plan.md` §6. Thư mục `plans/` bị dọn định kỳ và file nguồn đã mang nhãn SUPERSEDED; bản đồ này phải sống lâu hơn mọi plan vì nó là thứ duy nhất cho phép **đối chiếu lại khi DSH nâng phiên bản** |
| Cách dùng khi nâng cấp DSH | Với mỗi dòng có `file:line`, mở lại đúng file đó ở phiên bản mới và kiểm hành vi còn đúng không. Dòng nào lệch thì cập nhật ở đây **trước**, rồi mới sửa plan/preset phụ thuộc |
| Nhãn | **[V]** đã kiểm chứng bằng mã nguồn · **[U]** chưa |

> Bốn sự thật chịu lực nhất, nếu chỉ đọc một thứ thì đọc phần này: `maxDepth: 0` cấm delegation hoàn toàn · `run_code` được chèn sau `toolFilter` nên con PTC không bao giờ 0 tool · row subagent không có khoá `mode` nên con luôn kế thừa mode của cha · pruner kết quả tool không đăng ký listener nên không có gì cắt transcript trước ngưỡng compaction 80%.

---

## 6. Bề mặt DSH thật (xác minh mã nguồn 2026-09-18)

Nguồn: `@deepseek-ai/*` **0.1.5-rc.1** (`%USERPROFILE%\.dsh\profiles\node_modules` là **junction** tới cây npx). Nhãn **[V]** đã kiểm chứng · **[U]** chưa.

### 6.1 Sự thật chịu lực

| Hạng mục | Thực tế đã xác minh | Nguồn |
| --- | --- | --- |
| Phiên bản | **0.1.5-rc.1**; hai đường dẫn là **cùng một cây nguồn** (junction) | `npx/package.json`; SHA256 khớp |
| Profile ship sẵn | **Đúng 5**: `acp`, `web`, `headless`, `sdk`, `sdk-minimal`. `tui`/`rescue`/`desktop` không tồn tại (`desktop` bị chặn cứng) | `dsh-app-boot/lib/index.js:327-355` |
| Profile tự khởi tạo | Thiếu `$DSH_HOME/profiles/<name>/package.json` + tên là template ⇒ **tự tạo**, không lỗi | `dsh-app-boot/lib/index.js:886-892` |
| `headless` | Một task một tiến trình; stdout **chỉ** thông điệp cuối; reasoning ra stderr; exit 0/1; **không preset, không `--json`, không usage**; phải khởi động **qua launcher `dsh`** | `dsh-headless/lib/index.js:26,163-167`; `README.md:12,123,126` |
| Layer patch | `--patch <file>` và `$DSH_HOME/profiles/<name>/cordis.patch.yml` được áp **sau mọi bundle layer** ⇒ đây là **cơ chế duy nhất** để có composition tinh gọn cho headless/sdk | `dsh/lib/profile-boot-*.js:305-310` |
| Row subagent — 9 khóa | `provider`(req) · `toolName` · `modelSelectionSettings` · `enableRunInBackground` · `backgroundMode` · `agentOptions` · `persona` · `toolFilter` · `maxDepth` | `dsh-tool-subagent/lib/index.js:252-270` |
| `provider` của row | Là **backend** (spawn/fork/acp/codex/claude-code), **không** phải LLM provider | `dsh-tool-subagent/README.md:83` |
| `agentOptions` — 4 khóa | `provider` · `model` · `reasoningEffort` · `maxTokens` | `dsh-tool-subagent/lib/index.js:258-263` |
| `reasoningEffort` | Chỉ **`off` · `low` · `high` · `max`** (không có `medium`/`minimal`/`none`) | `dsh-llm-deepseek/lib/index.js:26-28` |
| `maxTokens` mặc định | **256.000** (`DEFAULT_MAX_TOKENS = 256e3`); con kế thừa của cha | `dsh-llm-deepseek:1394,1998`; `dsh-subagent/lib/types/child-agent.js:79-92` |
| `maxDepth` | Trần **tuyệt đối** theo depth của con; **`0` cấm delegation hoàn toàn** (con đầu tiên đã là depth 1) | `dsh-subagent/lib/types/child-agent.js:32-41`; `README.md:53` |
| `toolFilter` | Chỉ `{allow?, deny?}`. `{allow: []}` **hợp lệ** và gỡ mọi tool **kế thừa**; `{}` ném lỗi lúc mount; tên lạ ném lỗi ở **lần delegation đầu**, không phải lúc mount | `dsh-tool-subagent:265-268,370`; `dsh-tools:2795-2804` |
| `run_code` dưới `ptc` | Được **thêm lại SAU** restriction; dưới `ptc` gọi trực tiếp `read`/`write` bị từ chối | `dsh-tools:2874,2994` |
| Kế thừa của con | Con **join preset của cha** (`composeFrom`); **không có khóa nào để tắt** | `dsh-subagent/lib/index.js:543`; `dsh-tool-subagent` schema |
| Prompt của con | Section order **cố định**, tool list lexicographic; **runtime/time context nối ở ĐUÔI** ⇒ prefix ổn định, đuôi biến động mỗi bước | `dsh-system-prompt:96,112,133`; `dsh-time-context:231` |
| AGENTS.md | Nạp lại cho **mọi** agent (kể cả con), dedup theo digest. **Gỡ được** bằng `agent-instructions.config.maxBytes <= 0` | `dsh-agent-instructions:668,1270` |
| Pruner kết quả tool | `thresholdChars 8192 / head 4096 / tail 1024` — **nhưng không đăng ký listener**; chỉ chạy **bên trong một lượt compaction** | `dsh-compaction-tool-result-pruner:11,137` |
| Compaction | Tự chạy ở **80%** cửa sổ context, giữ lại **16%**; khoá `thresholdRatio 0.8`, `retainRatio 0.16`, `auto true`; viết lại vùng surface ⇒ **mất cache** từ điểm viết lại | `dsh-compaction-basic:15,17,76,111` |
| Spill | Ngưỡng **50.000 byte** (`maxInlineBytes`), preview head/tail + đường dẫn; **miễn trừ `read`** và call lồng nhau | `dsh-spill-policy:74,104,157`; `dsh-base/cordis.patch.yml:386` |
| Kết quả tool văn bản | **Không** lưu theo tham chiếu ⇒ nằm nguyên văn, gửi lại **mỗi bước** cho tới khi spill/prune/compact | `dsh-session:1204,1269` |
| Cấu trúc bước | **Một request mỗi BƯỚC**; mọi tool call trong một assistant message chạy trong bước đó (song song ≤ **10**), rồi **một** request mới | `dsh-agent-loop:1116,1118,1226` |
| `maxParallelSubCalls` | Mặc định **10**; thuộc row `dsh-tools`, **không** thuộc row subagent; **chưa** được cấu hình ở đây | `dsh-tools:2575` |
| Cô lập con | Chỉ **thông điệp cuối** của con qua lại; transcript và tool I/O ở lại. Thông điệp cuối **không có trần** (chỉ dòng tóm tắt 120 ký tự, diagnostics 4096 byte) | `dsh-subagent:185,217,661,2475` |
| Usage — trường | `assistant/message.data.usage` = `{inputTokens, outputTokens, totalTokens, cacheReadTokens, reasoningTokens}`. DSH **đổi tên và tách rời** các rổ: DeepSeek `prompt_tokens` gồm cả cache hit, harness trừ ra nên `inputTokens = prompt_tokens − cacheRead` = **uncached**. Tên gốc `prompt_cache_hit_tokens` **không** được lưu. | `dsh-llm-deepseek:1146-1166` |
| Usage — 6 cạm bẫy | (1) `inputTokens` là **uncached**, không phải prompt size; (2) `totalTokens` **theo từng request**, không tích luỹ; (3) `reasoningTokens` là **tập con** của `outputTokens`; (4) `cacheWriteTokens` **luôn 0** với adapter DeepSeek; (5) DSH **không lưu giá/tiền** ở bất kỳ đâu ⇒ `billed_usd` phải tính ngoài; (6) `surfaceTokens = systemTokens + messageTokens` (**không** cộng `toolsTokens`), còn `pressureTokens = input + cacheRead + cacheWrite` của mẫu mới nhất (**không** gồm output) | đo thật, đối soát khớp tuyệt đối tại `seq=283` |
| Usage — GUI | Không có lệnh `/usage`, không có `dsh usage`, không có lệnh chi phí. Con số "Usage" trên GUI = `uncachedInput + cacheRead + cacheWrite + output` ⇒ **có tính cache read**; pill theo lượt lại dán nhãn uncached là "Input". Vì vậy mọi con số báo cáo phải nêu rõ thước | `dsh-client-ui-chat/lib/client.js:3942,4016` |
| Usage — quy kết con | Burn của con **không** xuất hiện trong `tokenUsage` của cha (đo: cha 158.277 uncached, ba con 158.898 + 126.250 + 125.100). Muốn đủ chi phí một wave phải duyệt `subagentCatalog` rồi cộng projcache của từng con | `session_projcache` thật |
| Budget | DSH **không có** trần token/chi phí theo phiên hay theo ngày (grep toàn bộ `.js`: chỉ có nhận diện lỗi `QUOTA` phía provider). Các giới hạn số duy nhất: `maxTokens` 256.000/request, `contextWindow` 1M, compaction 0,8×, pruner 8192 ký tự, spill 50.000 byte | `dsh-llm:132,174`; `dsh-compaction-basic:14-18` |
| Nguồn đọc usage ngoài tiến trình | **JSONL** tại `~/.dsh/sessions/<workspace-key>/<uuid>/` (**không** phải SQLite): `dsh-session-query-sqlite` được mount **trơ** (`path: ':memory:'`, `openAt: never`) | `dsh-base/cordis.patch.yml:110-113,129-133` |
| Hook bridge CC/Codex | Có package nhưng **không** composition nào mount ⇒ không dùng được mặc định; chỉ có extension point native | grep toàn bộ `.yml` |
| `dsh-token-meter` | Chỉ expose **projection trong tiến trình**; script ngoài phải tự parse JSONL | `dsh-token-meter/lib/index.js:609-615` |
| PTC trong phiên GUI hiện tại | **Không bật** nếu preset là `standard` (không mount code-runtime); `tool-presentation` mặc định `native` | `dsh-agent-presets/presets/standard`; `dsh-tools/types/ptc.js` |
| Preset mặc định | `.dsh/settings.yaml` khai **`ptc`**; base do web-app đăng ký là **`standard`**; **dù giá trị nào cũng KHÔNG phải `news-scape-conductor`** | `settings.yaml:11-12`; `dsh-web-app/cordis.patch.yml:480-484` |

### 6.2 Câu hỏi đã được trả lời (thay cho U1–U6 của rev 1)

| # | Câu hỏi | Kết luận |
| :-: | --- | --- |
| U1 | `toolFilter.allow: []` hợp lệ? | **Hợp lệ**, gỡ mọi tool kế thừa. Nhưng dưới `ptc`, `run_code` được thêm lại ⇒ phải dùng **`mode: native`** để có 0 tool (E15) |
| U2 | `reasoningEffort` có mức tắt? | **Có: `off`** (hợp lệ trong 4 giá trị) |
| U3 | `maxTokens` mặc định? | **256.000**, không phải 8K (E17) |
| U4 | Thông điệp cuối của con có vào context cha? | **Dưới `ptc`: KHÔNG** (kết quả sub-call chỉ vào `tool/ptc-dispatch` trong log bền; chỉ log + giá trị `return`/`print` là model-facing). **Ở `native`: CÓ**. ⇒ Xác nhận giả định chịu lực của kiến trúc, **với điều kiện Conductor ở `ptc`** |
| U5 | Nguồn usage | **JSONL** `~/.dsh/sessions/...`, field `assistant/message.usage`; SQLite phiên **trơ** |
| U6 | `headless` chọn được preset? | **Không.** Tinh gọn bằng `--patch`/overlay profile |
| U7 | Preset mặc định thực tế của GUI | **[U]** `settings.yaml` (`ptc`) và base web (`standard`) mâu thuẫn ⇒ Phase 00 xác nhận bằng một lệnh. Không đổi kết luận E2 |
| U8 | `--patch`/overlay headless hoạt động end-to-end? | **[U]** cần một lần chạy thật ở Phase 00 |

---
