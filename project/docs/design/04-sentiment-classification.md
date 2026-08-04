# Thiết kế — Sentiment & phân loại (rule-based)

Cập nhật: 2026-07-26 · Đối tượng: người muốn hiểu/điều chỉnh cách chấm cảm xúc & gán nhãn.
Nguồn: `src/processor/sentiment.py`, `segment.py`, `classifier.py`, `data/lexicon/*.tsv`.

## 1. Vì sao rule-based, không LLM

Deterministic → tái lập được, rẻ, nhanh, không phụ thuộc API ngoài, không rate limit. Đủ tốt
cho tín hiệu 3 mức 🟢🟡🔴 phục vụ lọc tin. Đánh đổi: không hiểu ngữ cảnh sâu, phụ thuộc chất
lượng lexicon.

## 2. Lexicon (`data/lexicon/`)

Hai file TSV `từ<TAB>điểm`, điểm ∈ [-1, 1]:
- `vswn_polarity.tsv` — **135 term** cảm xúc tổng quát tiếng Việt.
- `finance_terms.tsv` — **181 term** tài chính chuyên ngành.

Nạp `vswn_polarity` trước, rồi `.update(finance_terms)` → **finance override** khi trùng key
(`sentiment.py:47-48`). Key ở dạng segmented nối `_`: `tăng_trần=1.0`, `giảm_sàn=-1.0`,
`vỡ_nợ=-1.0`, `lừa_đảo=-1.0`. Dòng blank / bắt đầu `#` / sai số cột bị bỏ qua, không crash
(`_load_tsv`, `sentiment.py:24-40`). Muốn chỉnh cảm xúc một cụm từ → sửa TSV, không đụng code.

## 3. Thuật toán chấm điểm — `score_tokens()` (`sentiment.py:53-75`)

1. Segment câu bằng pyvi (`segment.py`): `chứng khoán` → `chứng_khoán`. pyvi thiếu → fallback
   tách theo khoảng trắng.
2. Duyệt token trái→phải, mỗi vị trí thử n-gram **dài trước** n ∈ (3, 2, 1); key = `"_".join(tokens[i:i+n])`.
   Match đầu tiên trong lexicon thắng → nhảy `i += n` (token đã dùng không xét lại).
3. **Phủ định:** nếu token ngay trước ∈ `NEGATIONS` = {không, chưa, chẳng, không_phải, chưa_thể,
   không_còn} → đảo dấu điểm (`s = -s`).
4. Điểm câu = **trung bình** các match. Không match nào → 0.0.

## 4. Kết hợp tiêu đề + thân bài — `analyze()` (`sentiment.py:77-90`)

- `title_score = score_tokens(seg(title))`.
- Nếu có thân bài: `body_score = score_tokens(seg(text)[:100])` — chỉ **100 token đầu** (câu
  mở thường mang tín hiệu chính, tránh loãng).
- Có body → `score = 0.67·title + 0.33·body`; không body → `score = title_score`. Làm tròn 3 số.
- **Ngưỡng** (mặc định `pos=0.2`, `neg=-0.2`): `> 0.2` → positive; `< -0.2` → negative; giữa → neutral.

## 5. Nhãn ↔ emoji

Engine trả `("positive"|"negative"|"neutral", score)`. Emoji **không** nằm trong engine — chỉ
ở notifier (`file_notify.py:46`): `positive→🟢`, `negative→🔴`, `neutral→🟡` (default 🟡).

## 6. Tiếng Anh

**Không có** code phát hiện ngôn ngữ trong engine. Cơ chế thực: orchestrator xem
`metadata["language"]`; nếu `!= "vi"` thì **ép** `("neutral", 0.0)` mà **không gọi engine**
(`orchestrator.py:107-109`). Vậy bài EN không tốn công segment và không bị chấm sai.

## 7. Phân loại — `classify_rule_based()` (`classifier.py:37-49`)

Độc lập sentiment. Quét `title + body[:2000]` bằng regex `re.I` cho 4 nhóm (finance, tech,
trading, cmt); mỗi nhóm match ≥1 pattern → gán nhãn (break sau match đầu). Rỗng → `["uncategorized"]`
(orchestrator loại nhãn này khi merge). Ngoài ra `categories` còn nhận tên feed (vd "Vietstock
Chứng khoán") do scraper gắn.

## 8. Điều chỉnh & kiểm định

- Chỉnh nhạy: sửa điểm trong TSV hoặc ngưỡng `pos/neg` (`sentiment.py:45`).
- Bộ kiểm định: `data/labeled/sentiment_validation.csv`. Test: `tests/test_sentiment.py`.
- Thêm từ phủ định mới → cập nhật `NEGATIONS` (`sentiment.py:17`).

## 9. Giới hạn đã biết

- Không xử được mỉa mai / ngữ cảnh đảo nghĩa xa hơn 1 token phủ định liền trước.
- Bài EN luôn neutral → không phản ánh sentiment thật của tin quốc tế (chấp nhận theo thiết kế).
- Trung bình cộng có thể loãng khi bài dài nhiều cụm trái dấu (đã giảm thiểu bằng cap 100 token body).
