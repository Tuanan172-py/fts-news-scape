# Domains — Báo tài chính quốc tế (RSS, language: en)

Cập nhật: 2026-07-26 · 5 nguồn `language: en` → orchestrator **ép sentiment neutral/0.0** (lexicon
VN không áp tiếng Anh). Verify 2026-07-25.

## cnbc — `cnbc.yaml` (**có filter**)
- **2 feeds:** `search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258`
  (World Economy), `&id=100003114` (Top News). **summary-only** (`extract_full: false`, cap 0).
- **filter.any** (18 keyword: stock, market, fed, inflation, rate, earnings, economy, oil, gold,
  treasury, bond, china, asia, tariff, gdp, central bank, currency, vietnam), `drop_unmatched: true`.
- **Quirk:** cần **browser UA**. Top News nhiễu cao → filter bắt buộc. ~30+30 items.

## marketwatch — `marketwatch.yaml`
- **1 feed:** `https://feeds.content.dowjones.io/public/rss/mw_topstories`. **summary-only** (cap 0).
- **Quirk:** curated ~10 items, nhiễu thấp → không cần filter. Detail = **paywall Dow Jones** →
  summary-only. (Lưu ý: feed Dow Jones đôi khi syndicate link wsj.com/barrons.com/investors.com →
  `source_domain` của bài có thể là các domain đó, không phải marketwatch.)

## fed — `fed.yaml`
- **1 feed:** `https://www.federalreserve.gov/feeds/press_all.xml`. `extract_full: true`, cap 10.
- **Quirk:** **BOM** trước `<?xml`. ~20 items, tần suất thấp nhưng **signal macro rất cao**. Press
  release ngắn → full text đáng lấy.

## oilprice — `oilprice.yaml`
- **1 feed:** `https://oilprice.com/rss/main`. `extract_full: true`, cap 10.
- **Quirk:** ~15 items, tin dầu/năng lượng/địa chính trị. **Opinionated** — đọc như commentary,
  không phải tin thuần.

## yahoofinance — `yahoofinance.yaml` (**có filter block-list**)
- **1 feed:** `https://finance.yahoo.com/news/rssindex`. **summary-only** (cap 0).
- **filter.none** (~28 term block lifestyle/retail-finance): cd rates, add-on cd, mortgage,
  refinance, heloc, home equity, high-yield savings, savings/checking account, business bank
  account, bank review, student aid, tax bill, money advice, trump account, social security,
  medicare, scammers, financial planner, retirement, 401(k), credit card, …
- **Quirk:** ~42 items. Detail page có **consent wall** → summary-only. Cần browser UA. Dùng
  **block-list** (không allow-list) vì tiêu đề tin thị trường quá đa dạng (nhiều tin chỉ là tên
  công ty) — allow-list sẽ loại nhầm. Xem lý do đầy đủ ở [../design/03-source-strategy.md](../design/03-source-strategy.md) §4.

## Chung cho nhóm quốc tế

- `language: en` → **không** chấm sentiment VN (ép neutral). Nếu sau này muốn sentiment EN thật →
  cần engine riêng (ngoài phạm vi hiện tại).
- Phần lớn summary-only (paywall/consent) → dựa vào title + summary làm tín hiệu.
- fed + oilprice là 2 nguồn full-text (cap thấp = 10) vì nội dung ngắn, giá trị cao.
