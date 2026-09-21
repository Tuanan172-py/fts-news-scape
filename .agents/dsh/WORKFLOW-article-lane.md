# Lưu đồ vận hành — Article Lane

|  |  |
| --- | --- |
| Lập | 2026-09-21 |
| Mô tả | Toàn bộ quy trình agent sau đợt tối ưu bộ nhớ đệm 21/09 |
| Cách chạy | [`RUNBOOK-article-lane.md`](RUNBOOK-article-lane.md) — tệp này giải thích **vì sao**, runbook nói **gõ gì** |
| Việc tay trên DSH | [`DSH-VIEC-THU-CONG.md`](DSH-VIEC-THU-CONG.md) |
| Thiết kế gốc | `plans/20260918-1651-article-lane-unified/plan.md` |

> Nhãn trong lưu đồ để **không dấu** theo đúng quy ước sẵn có của kho (`project/docs/design/*`). Phần diễn giải quanh lưu đồ vẫn có dấu đầy đủ.

---

## 0. Ba vùng chi phí — đọc lưu đồ theo vùng, không theo bước

Mọi lưu đồ dưới đây tô theo **ai trả tiền**, vì đó là thứ quyết định kiến trúc:

| Ký hiệu | Vùng | Chi phí | Ai chạy |
| --- | --- | --- | --- |
| 🟩 | **Terminal** — script Python | **0 token** | Anh gõ lệnh, máy làm |
| 🟦 | **Phiên DSH** — Conductor | ~50–200 token mỗi **bước** | Mô hình điều phối |
| 🟥 | **Worker** — `agent_article` | ~1.550 vào + ~900 ra **mỗi bài** | Mô hình xử lý |
| ⬜ | **Người** | — | Quyết định, không thao tác |

Nguyên tắc chi phối toàn bộ thiết kế: **chi phí phiên điều phối tỉ lệ với số BƯỚC, không tỉ lệ với số bài.** Vì vậy cả một đợt trăm bài được nén vào **đúng một bước** của Conductor.

---

## 1. Toàn cảnh một đợt

```mermaid
flowchart TB
  subgraph L0["L0 - CHUAN BI MOT LAN - 0 token"]
    direction LR
    CAT[("entities.json<br/>1.262 thuc the")] --> GEN["build_article_prefix.py"]
    GEN --> PFX[/"ARTICLE_SYSTEM_CORE.md - 6.343 token"/]
    PFX -.->|"DAN TAY - viec thu cong duy nhat"| PRESET["persona trong<br/>agent.cordis.yml"]
    PRESET --> CHK{{"--check<br/>2 ve: catalog + persona"}}
  end

  subgraph L1A["L1 - CHUAN BI DOT - 0 token - terminal"]
    direction TB
    RUN1["article_run.py --wave W --limit N --batch B"] --> P1["kiem prefix 2 ve"]
    P1 --> P2["article_pack.py<br/>xep tang + chat loc + chia lo"]
    P2 --> ART[("packet .task.json<br/>+ map .map.json")]
    P2 --> MAN[("wave_W.json<br/>manifest + du toan")]
    P2 --> PROG[/"wave_W.conductor.ts"/]
  end

  subgraph L2["L2 - CHAY MO HINH - DUNG 1 BUOC cua Conductor"]
    direction TB
    RC["run_code - dan tron conductor.ts"] --> WARM{"tu 2 lo?"}
    WARM -->|"co"| W1["luot ham cache<br/>1 bai rac"]
    WARM -->|"khong"| SKIP["bo qua"]
    W1 --> PAR
    SKIP --> PAR[["chay MOI lo song song<br/>agent_article"]]
    PAR --> OUT[("agent_outputs_article<br/>cac tep .output.json")]
    PAR --> RET[["return chi con so<br/>noi dung KHONG vao ngu canh"]]
  end

  subgraph L1B["L1 - HOAN TAT - 0 token - terminal"]
    direction TB
    FIN["article_run.py --wave W --finish"] --> EXP["article_expand.py<br/>salvage tung ban ghi"]
    EXP --> RES["resolver theo nhom<br/>chuoi nguyen van sang entity_id"]
    RES --> DB[("monocle.db<br/>l1_outputs + agent_outputs")]
    DB --> LED["token_ledger append<br/>+ kiem san cache"]
    LED --> HO["handoff.py + ctx_probe.py"]
  end

  subgraph L3["GIAO HANG - 0 token"]
    DEL["write_user_output.py --date today"] --> USR[/"thu muc users/output o GOC KHO"/]
  end

  CHK ==> RUN1
  PROG ==>|"anh dan vao phien DSH"| RC
  OUT ==> FIN
  HO ==> DEL

  classDef zero fill:#e8f5e9,stroke:#2e7d32
  classDef cond fill:#e3f2fd,stroke:#1565c0
  classDef work fill:#ffebee,stroke:#c62828
  class L0,L1A,L1B,L3 zero
  class L2 cond
  class PAR,W1 work
```

**Điều đáng chú ý nhất trong lưu đồ này:** hai khối xanh lá kẹp lấy một khối xanh dương rất mỏng. Mọi việc cơ học — đọc dữ liệu, chắt lọc, chia lô, tra cứu định danh, nạp cơ sở dữ liệu, tính tiền — nằm ở vùng 0 token. Mô hình chỉ làm đúng phần không code hoá được: **nhận diện thực thể và xử lý nội dung**.

---

## 2. Trình tự thời gian — ai gọi ai

```mermaid
sequenceDiagram
  autonumber
  actor N as Nguoi van hanh
  participant T as Terminal - 0 token
  participant C as Conductor - phien DSH
  participant W as Worker agent_article
  participant D as DeepSeek

  N->>T: article_run.py --wave W01 --limit 100 --batch 100
  T->>T: kiem prefix - catalog + persona
  T->>T: dong goi packet + sinh conductor.ts
  T-->>N: du toan miss / hit / out + duong dan chuong trinh

  N->>C: dan TRON conductor.ts vao MOT lenh run_code

  rect rgb(240, 245, 255)
    Note over C,D: TAT CA nam trong DUNG MOT buoc cua Conductor
    opt tu 2 lo tro len
      C->>W: luot ham - packet 1 bai rac
      W->>D: prefix tinh 11.143 token - MISS
      D-->>W: ghi bo nho dem
    end
    par moi lo chay song song
      C->>W: lo 1 - packet doc theo cua so dong
      W->>D: prefix HIT + noi dung MISS
      D-->>W: mang JSON ban ghi
      W-->>C: ghi thang ra dia
    and
      C->>W: lo 2 - packet
      W->>D: prefix HIT + noi dung MISS
      D-->>W: mang JSON ban ghi
      W-->>C: ghi thang ra dia
    end
    C-->>N: chi tra ve con so - so lo xong, lo nao hong
  end

  N->>T: article_run.py --wave W01 --finish
  T->>T: bung ban ghi, tra cuu dinh danh, nap DB
  T->>T: ghi so cai + kiem san bo nho dem
  T-->>N: da chot so + tep ban giao
```

Ba điều bất biến mà trình tự này bảo vệ:

1. **Kết quả của worker không bao giờ đi qua ngữ cảnh của Conductor.** Dưới chế độ `ptc`, chỉ thứ chương trình `return` mới vào ngữ cảnh — nên một đợt để lại dưới 100 token. Đổi sang `native` là mỗi lô đổ ~30.000 token JSON vào phiên cha, tức làm sống lại đúng lớp đốt token mà cả kiến trúc này chữa.
2. **Worker xong trong đúng một bước.** Nó không có tool nào, nên không tích luỹ kết quả tool, nên không có lịch sử để gửi lại.
3. **Lượt hâm đi trước, không phải lô đầu.** Bộ nhớ đệm chỉ được ghi khi có một request thật đi qua — nhưng request ấy không cần mang trăm bài.

---

## 3. Bên trong chương trình điều phối

```mermaid
flowchart TB
  S([bat dau run_code]) --> Q{"BATCHES.length >= 2 ?"}
  Q -->|"khong"| L
  Q -->|"co"| WU["agent_article - WARM<br/>packet 1 bai rac"]
  WU -.->|"that bai thi bo qua"| L
  WU --> L["vong chay theo CONCURRENCY"]

  subgraph RB["runBatch - lap cho tung lo"]
    direction TB
    R1["doc packet theo cua so dong<br/>offset va limit da tinh san"] --> R2{"packet rong?"}
    R2 -->|"co"| R3["danh dau hong, di tiep"]
    R2 -->|"khong"| R4["agent_article - packet that"]
    R4 --> R5["boc phan text khoi vo<br/>kind, runId, output"]
    R5 --> R6[("ghi ra dia<br/>batch_id.output.json")]
  end

  L --> RB
  RB --> E(["return: wave, so lo, danh sach lo hong"])

  classDef warn fill:#fff8e1,stroke:#f9a825
  class R2,R3,R5 warn
```

Ba chi tiết trong lưu đồ này đều là **vết sẹo của sự cố thật**, không phải thiết kế thừa:

- **Đọc theo cửa sổ dòng.** Công cụ đọc của DSH cắt ở 2.000 ký tự mỗi dòng, 51.200 byte và 2.000 dòng mỗi lần gọi. Lô 100 bài nặng ~348 KB nên phải phân trang 7–8 lần. Các lần đọc ấy nằm **trong cùng một chương trình** nên không sinh thêm bước nào của mô hình.
- **Bóc lớp vỏ trước khi ghi.** Công cụ gọi agent trả về `{kind, runId, output:[{type,text}]}`. Ghi thẳng cả đối tượng ấy ra đĩa thì bộ bung bản ghi đọc nhầm lớp vỏ thành một bản ghi rác — đúng thứ đã xảy ra với các tệp `_cNN` của W1 và W2.
- **Chỉ `return` con số.** Mọi thứ khác ở lại trong chương trình.

---

## 4. Vòng đời token của một lô — tiền đi đâu

```mermaid
flowchart LR
  subgraph REQ["MOT request cua worker"]
    direction TB
    A["harness identity + AGENTS.md<br/>+ section tool/SDK<br/>~4.800 token"]:::hit
    B["persona = ARTICLE_SYSTEM_CORE<br/>6.343 token"]:::hit
    C["packet - tieu de + doan noi dung<br/>~1.542 token moi bai"]:::miss
    D["runtime context<br/>noi SAU packet"]:::hit
    A --> B --> C --> D
  end

  REQ --> LLM[["deepseek-flash"]]
  LLM --> OUT["ban ghi ~900 token moi bai"]:::out

  classDef hit fill:#e8f5e9,stroke:#2e7d32
  classDef miss fill:#fff3e0,stroke:#ef6c00
  classDef out fill:#ffebee,stroke:#c62828
```

Thứ tự trên **không phải do dự án sắp** — DSH đã dựng sẵn đúng chiều tối ưu cho bộ nhớ đệm: phần tĩnh ở đầu, ảnh chụp runtime nối **sau** packet như một thông điệp người dùng, và `dsh-time-context` không được mount nên không có đồng hồ nào chen vào giữa.

**Giá ba rổ, off-peak, USD trên 1 triệu token:**

| Rổ | Đơn giá | So với rổ rẻ nhất |
| --- | ---: | ---: |
| Đầu vào trúng cache | 0,003 | 1× |
| Đầu vào mới | 0,15 | **50×** |
| Đầu ra | 0,60 | **200×** |

**Hệ quả xếp hạng đòn bẩy — đo trên số thật của W2:**

| | Token | Chi phí | Tỷ trọng |
| --- | ---: | ---: | ---: |
| Đầu ra | 162.703 | $0,0976 | **62%** |
| Đầu vào mới | 360.365 | $0,0541 | 34% |
| Đầu vào trúng cache | 1.723.520 | $0,0052 | 3,3% |

Hai kết luận đi kèm nhau, bỏ một cái là hiểu sai:

- Tiền tố tĩnh **chỉ đáng 1,4%** hoá đơn ở cỡ lô 100 bài. Nó không phải cần gạt tiết kiệm.
- Nhưng nếu không có cache, 1,72 triệu token tái dùng của W2 bị tính giá mới: hoá đơn thành **$0,410 thay vì $0,157**. Cache là **bảo hiểm** cho những lượt lặp bước và những lần chạy lại.

---

## 5. Cây quyết định khi có sự cố

```mermaid
flowchart TB
  S{"Trieu chung?"} --> A["Lo tra ve thieu bai"]
  S --> B["So cai bao BO NHO DEM TRUOT"]
  S --> C["turns_max lon hon 1"]
  S --> D[reasoning > 0]
  S --> E["Ap suat vang hoac do"]
  S --> F["token moi bai vuot 2.500"]

  A --> A1["--repair"] --> A2{"Trang thai"}
  A2 -->|"chua lo nao chay"| A3["ma thoat 2<br/>chay chuong trinh dieu phoi truoc"]
  A2 -->|"du bai"| A4["khong can va"]
  A2 -->|"thieu bai"| A5["sinh packet bu + repair.ts<br/>chi dong goi dung phan thieu"]

  B --> B1["build_article_prefix.py --check"]
  B1 -->|"persona lech"| B2["dan lai persona - nguyen nhan so 1"]
  B1 -->|"khop"| B3{"co doi tool set, model<br/>hay effort giua dot?"}
  B3 -->|"co"| B4["doi giua HAI dot, khong doi giua dot"]
  B3 -->|"khong"| B5["phien nao cham nguong nen 80%<br/>vung surface da bi viet lai"]

  C --> C1["persona troi: doan tuyen bo<br/>KHONG CO TOOL phai dung dau"]
  D --> D1["dat reasoningEffort off - CO dau nhay"]
  E --> E1["doc ban giao, DONG PHIEN, mo phien moi"]
  F --> F1{"gop nham phien khac?"}
  F1 -->|"co"| F2["thu hep moc --since"]
  F1 -->|"khong"| F3["soi histogram token moi bai<br/>cua article_pack"]

  classDef fix fill:#e8f5e9,stroke:#2e7d32
  class A3,A4,A5,B2,B4,B5,C1,D1,E1,F2,F3 fix
```

---

## 6. Ranh giới ba lớp — luật không được vi phạm

```mermaid
flowchart LR
  subgraph MAY["MAY LAM - 0 token"]
    M1["doc va chat loc noi dung"]
    M2["xep tang uu tien"]
    M3["chia lo"]
    M4["tra chuoi nguyen van sang entity_id"]
    M5["bung trich dan theo chi so"]
    M6["cham cong nghiem thu"]
    M7["do token va tinh tien"]
  end

  subgraph LLM["LLM LAM - khong code hoa duoc"]
    N1["nhan dien thuc the tu ngu canh"]
    N2["tom tat va rut luan diem"]
    N3["ham y thi truong"]
    N4["sac thai va do khan"]
    N5["chon doan lam chung cu"]
  end

  subgraph NGUOI["NGUOI LAM"]
    H1["duyet plan va ADR"]
    H2["chon uu tien va lich chay"]
    H3["dan persona vao preset"]
    H4["xu ly bat thuong"]
  end

  MAY -.->|"packet"| LLM
  LLM -.->|"ban ghi gon"| MAY
  NGUOI -.->|"lenh dot"| MAY
```

Hai luật hai chiều, và cả hai đều từng bị vi phạm:

- **Code không được quyết định thay LLM.** Trần chắt lọc 900 token từng bỏ **46% nội dung nghiệp vụ** trước khi mô hình kịp đọc — tức code đang chọn hộ mô hình được đọc gì. Đã tắt.
- **LLM không được làm thay code.** Không đọc tệp, không tra danh mục, không tự chấm nghiệm thu, không phát định danh chuẩn. Vệt 845 nghìn token ngày 17/09 là hậu quả của việc agent tự đi dò `entities.json`: riêng việc đó chiếm 53% nội dung của cả vệt.

---

## 7. Bản đồ lệnh và tệp

| Lệnh | Sinh ra | Đọc vào |
| --- | --- | --- |
| `build_article_prefix.py` | `data/prefix/ARTICLE_SYSTEM_CORE.md` + `.meta.json` | `entities.json`, `taxonomy.json` |
| `build_article_prefix.py --check` | — | tệp prefix + `persona` trong preset |
| `article_run.py --wave W` | `article_W_NN.task.json`, `.map.json`, `wave_W.json`, `wave_W.conductor.ts` | `monocle.db`, gói tầng bạc |
| *chương trình điều phối* | `agent_outputs_article/*.output.json` | packet trên đĩa |
| `article_run.py --wave W --repair` | `*_rNN.task.json`, `wave_W.repair.ts` | packet gốc + đầu ra đã có |
| `article_run.py --wave W --finish` | bản ghi trong `monocle.db`, dòng `token_ledger`, `HANDOFF-*.md` | đầu ra của lô, checkpoint phiên DSH |
| `pipeline_radar.py token --wave W` | — | `harness.db` + checkpoint phiên |
| `estimate_wave.py --wave W` | — | manifest + `harness.db` |
| `write_user_output.py --date today` | `users/output/...` ở **gốc kho** | `monocle.db` |

---

## 8. Những gì đợt 21/09 đã đổi trong lưu đồ này

| Chỗ trong lưu đồ | Trước | Sau |
| --- | --- | --- |
| §1 khối `CHK` | `--check` chỉ so tệp với danh mục | So **hai vế**, thêm vế persona ↔ tệp |
| §3 nhánh `WARM` | Lô đầu chạy một mình để ghi cache | Lượt hâm tí hon; đợt một lô không hâm |
| §1 khối `P2` | Thứ tự bài phụ thuộc kế hoạch truy vấn | Tất định, kèm băm packet |
| §4 khối tiền tố | Dự toán chỉ đếm persona 6.343 | Đếm cả phần harness: **11.143** |
| §1 khối `LED` | Chỉ ghi số | Thêm **sàn cache** `hit ≥ tiền tố × (số phiên − 1)` |
| §7 `radar token` | Nhân định mức chết 450 / 1.470 | Đọc sổ cái và checkpoint thật |
| §5 nhánh `--repair` | Chưa chạy lần nào cũng báo "không cần vá" | Phân biệt ba trạng thái |
| §1 khối `LED` — sàn cache | Đếm mọi phiên như một worker | Đếm **lượt gọi worker** đọc từ mô tả đợt |
| §7 `radar token --date` | So ngày máy với mốc UTC của sổ cái | Đổi ngày máy thành khoảng UTC trước khi tra |

Chi tiết số đo và lý do: `plans/20260918-1651-article-lane-unified/plan.md` §17.
