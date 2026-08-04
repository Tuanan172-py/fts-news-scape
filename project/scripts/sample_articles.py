"""
Xuất bài đăng mẫu từ TỪNG nguồn — tổ chức kim tự tháp để đọc logic:

    logs/sample_articles/
      README.md               index: cách đọc + bảng tổng quan + đối chiếu DB
      01-layer0-exchanges.md  nguồn chính thống Sở GD (hnx, hose)
      02-api-aggregators.md   API chuyên CK (cafef, tnck, fireant, vndirect)
      03-vn-press-rss.md      báo chí VN (12 domain RSS)
      04-intl-rss.md          quốc tế EN (cnbc, marketwatch, yahoo, fed, oilprice)

Mỗi domain: luồng tin + breakdown feed; bài ĐẦU minh hoạ ĐẦY ĐỦ 6 giai đoạn
pipeline (RAW→PARSE→DEDUP→ENRICH→NLP→DB), các bài sau dạng thẻ gọn.
Chỉ đọc, KHÔNG ghi DB / KHÔNG mark_seen.

Usage:
    python scripts/sample_articles.py                 # tất cả nguồn, 2 bài/feed
    python scripts/sample_articles.py cafef vnexpress # chọn nguồn (vẫn ghi đủ bộ file)
    python scripts/sample_articles.py --n 3           # 3 bài/feed
"""

from __future__ import annotations

import io
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import list_domains, load_domain_config
from src.core.logging import setup_logging
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.orchestrator import build_scraper
from src.processor.classifier import classify_rule_based
from src.processor.sentiment import SentimentEngine

import src.scrapers  # noqa: F401

_SNIP = 240
_RAW_VAL = 110
OUT_DIR = Path("logs/sample_articles")

# Phân nhóm theo tầng nguồn tin — khớp taxonomy docs/domains/
GROUPS = {
    "01-layer0-exchanges": {
        "title": "Layer 0 — Nguồn chính thống Sở Giao dịch",
        "desc": "Công bố thông tin trực tiếp từ Sở (signal sơ cấp, title là tín hiệu chính).",
        "domains": ["hnx", "hose"],
    },
    "02-api-aggregators": {
        "title": "API chuyên chứng khoán (reverse-engineered)",
        "desc": "Nguồn giá trị cao nhất về độ liên quan CK — fetch theo watchlist, có detail endpoint.",
        "domains": ["cafef", "tnck", "fireant", "vndirect"],
    },
    "03-vn-press-rss": {
        "title": "Báo chí Việt Nam (RSS)",
        "desc": "Phủ rộng tin kinh tế/CK tiếng Việt — generic RSSScraper, sentiment lexicon VN.",
        "domains": ["vietstock", "vneconomy", "vnexpress", "vietnambiz", "dantri",
                    "tuoitre", "thanhnien", "znews", "cafebiz", "vietnamplus",
                    "vietnamnet", "baodautu"],
    },
    "04-intl-rss": {
        "title": "Quốc tế (RSS, tiếng Anh)",
        "desc": "Bối cảnh vĩ mô toàn cầu (Fed, dầu, US markets) — sentiment neutral by design.",
        "domains": ["cnbc", "marketwatch", "yahoofinance", "fed", "oilprice"],
    },
}


def _t(s, n=_SNIP) -> str:
    s = str(s or "").strip().replace("\n", " ")
    return (s[: n] + "…") if len(s) > n else s


def _anchor(name: str) -> str:
    return name.lower().replace(" ", "-")


def _flow_description(cfg: dict) -> list[str]:
    lines = []
    method = cfg.get("method")
    if method == "rss":
        feeds = cfg.get("rss", {}).get("feeds", [])
        lines.append(f"- **Luồng:** RSS ({len(feeds)} feed) → generic `RSSScraper`")
        for f in feeds:
            lines.append(f"  - `{f.get('name', '?')}` — {f.get('url')}")
    elif method == "api":
        api = cfg.get("api", {})
        lines.append(f"- **Luồng:** REST API → scraper riêng (`src/scrapers/{cfg['name']}.py`)")
        if api.get("list_url"):
            lines.append(f"  - List: `{api['list_url']}` params={api.get('params', {})}")
        if api.get("detail_url_template"):
            lines.append(f"  - Detail: `{api['detail_url_template']}`")
        if cfg.get("auth"):
            lines.append(f"  - Auth: {cfg['auth'].get('type')} (secrets key: `{cfg['auth'].get('secret_key')}`)")
    filt = cfg.get("filter") or {}
    if filt.get("any"):
        lines.append(f"- **Filter giữ (any):** {len(filt['any'])} từ khoá"
                     + (" — bài không khớp bị loại" if filt.get("drop_unmatched", True) else ""))
    if filt.get("none"):
        lines.append(f"- **Filter chặn (none):** {len(filt['none'])} từ khoá block-list")
    detail = cfg.get("detail") or {}
    if detail.get("extract_full", True):
        lines.append(f"- **Enrich:** fetch trang chi tiết (cap {detail.get('max_details_per_cycle', 30)} bài/cycle; "
                     f"quá cap → summary + `detail_deferred`)")
    else:
        lines.append("- **Enrich:** KHÔNG fetch chi tiết (summary-only by design)")
    if cfg.get("link_rewrites"):
        lines.append(f"- **Link rewrites:** {len(cfg['link_rewrites'])} rule")
    lines.append(f"- **Rate limit:** {cfg.get('rate_limit', 3.0)}s | timeout {cfg.get('timeout', 30)}s"
                 f" | language={cfg.get('language', 'vi')}")
    if cfg.get("pitfalls"):
        lines.append(f"- **Pitfalls (đã verify):** {cfg['pitfalls']}")
    return lines


def _raw_block(raw: dict) -> list[str]:
    lines = ["**[1] RAW — item thô từ nguồn:**", "", "```"]
    shown = 0
    for k, v in raw.items():
        if v in (None, "", [], {}):
            continue
        if shown >= 12:
            lines.append(f"... (+{len(raw) - shown} field khác)")
            break
        lines.append(f"{k}: {_t(v, _RAW_VAL)}")
        shown += 1
    lines.append("```")
    return lines


def _db_row_block(a) -> list[str]:
    row = a.to_row()
    lines = ["**[6] DB ROW — bảng `articles` (INSERT OR IGNORE qua DBWriter):**", "",
             "| Cột | Giá trị |", "|-----|---------|"]
    for col, val in row.items():
        if col in ("content_html", "content_text"):
            shown = f"({len(str(val or ''))} ký tự) {_t(val, 80)}"
        elif col == "metadata_json":
            shown = _t(val, 130)
        elif col == "url_title_hash":
            shown = f"`{str(val)[:16]}…`"
        else:
            shown = _t(val, 130)
        lines.append(f"| {col} | {str(shown).replace('|', chr(92) + '|')} |")
    return lines


def _nlp_apply(a, sentiment_engine):
    """Đúng logic orchestrator.run_cycle: classify + sentiment (vi only)."""
    for cat in classify_rule_based(a.title, a.content_text):
        if cat not in a.categories and cat != "uncategorized":
            a.categories.append(cat)
    if a.metadata.get("language", "vi") == "vi":
        a.sentiment, a.sentiment_score = sentiment_engine.analyze(a.title, a.content_text)
        return "lexicon VN"
    a.sentiment, a.sentiment_score = "neutral", 0.0
    return "bài EN → neutral by design"


def _full_pipeline_block(cfg, scraper, raw, a, dedup, sentiment_engine) -> list[str]:
    """Bài minh hoạ: đầy đủ 6 giai đoạn."""
    out = _raw_block(raw) + [""]
    out += ["**[2] PARSE → Article chuẩn hoá:**", "",
            f"- url: {a.url}",
            f"- source_domain: `{a.source_domain}` | published_at: `{a.published_at or '(trống)'}`"
            f" | author: {a.author or '—'}",
            f"- symbols: {', '.join(a.symbols) or '—'} | categories khởi tạo: {', '.join(a.categories) or '—'}",
            f"- summary ({len(a.summary)} ký tự): {_t(a.summary, 170)}", ""]
    seen = dedup.is_duplicate(a.url, a.title)
    out += ["**[3] DEDUP:**", "",
            f"- hash = `{a.url_title_hash[:20]}…` (SHA-256 url+title)",
            f"- seen_articles: {'⏭️ đã seen cycle trước → cycle thật bỏ qua (hiển thị để minh hoạ)' if seen else '🆕 chưa seen → cycle thật sẽ lưu DB'}",
            ""]
    had_inline = bool(a.metadata.get("_inline_html"))
    try:
        scraper.enrich(a)
        if had_inline:
            path = "dùng `content:encoded` sẵn trong feed"
        elif a.metadata.get("detail_deferred"):
            path = "quá cap detail → giữ summary (`detail_deferred`, enrich_deferred bù sau)"
        elif not (cfg.get("detail") or {}).get("extract_full", True) and cfg.get("method") == "rss":
            path = "summary-only by design (`extract_full: false`)"
        else:
            path = "fetch trang chi tiết → extract"
        out += ["**[4] ENRICH — lấy body:**", "",
                f"- Đường đi: {path}",
                f"- content_html: {len(a.content_html)} ký tự (nguyên bản) | "
                f"content_text ({len(a.content_text)} ký tự): {_t(a.content_text)}", ""]
    except Exception as e:
        a.content_text = a.content_text or a.summary
        out += [f"**[4] ENRICH:** ⚠️ {type(e).__name__}: {_t(e, 90)} → fallback summary", ""]
    note = _nlp_apply(a, sentiment_engine)
    out += ["**[5] CLASSIFY + SENTIMENT:**", "",
            f"- categories: {', '.join(a.categories) or '—'}",
            f"- sentiment: **{a.sentiment}** (score={a.sentiment_score}) — {note}", ""]
    out += _db_row_block(a) + [""]
    return out


def _compact_card(scraper, raw, a, sentiment_engine) -> list[str]:
    """Bài phụ: thẻ gọn — vẫn chạy đủ enrich+NLP nhưng chỉ hiện kết quả chính."""
    try:
        scraper.enrich(a)
    except Exception:
        a.content_text = a.content_text or a.summary
    _nlp_apply(a, sentiment_engine)
    feed = raw.get("_feed_name", "")
    return [
        f"> **{a.title}**" + (f"  *(feed: {feed})*" if feed else ""),
        f"> 📅 {a.published_at or '—'} | 📊 {', '.join(a.symbols) or '—'}"
        f" | 🏷️ {', '.join(a.categories[:3]) or '—'}"
        f" | 💬 {a.sentiment} ({a.sentiment_score})"
        f" | 📄 body {len(a.content_text)} ký tự",
        f"> 🔗 {a.url}",
        f"> 📝 {_t(a.content_text, 200)}",
        "",
    ]


def dump(only: list[str] | None = None, n: int = 2) -> int:
    setup_logging("ERROR", "logs")
    store = ArticleStore("data/monocle.db")
    dedup = DedupCache(store)
    http = HTTPClient(rate_limit_delay=3.0, max_retries=3)
    sentiment_engine = SentimentEngine()

    all_names = list_domains(enabled_only=False)
    grouped = set(d for g in GROUPS.values() for d in g["domains"])
    ungrouped = [d for d in all_names if d not in grouped]   # domain mới chưa xếp nhóm

    summary_rows = []      # bảng tổng quan cho README
    group_files: dict[str, list[str]] = {}

    for gkey, ginfo in GROUPS.items():
        gdomains = ginfo["domains"] + (ungrouped if gkey == "03-vn-press-rss" else [])
        body = [f"# {ginfo['title']}", "", ginfo["desc"], "",
                "← Quay lại [tổng quan](README.md). Pipeline 6 giai đoạn giải thích trong README.", ""]
        for name in gdomains:
            if name not in all_names:
                continue
            if only and name not in only:
                continue
            try:
                cfg = load_domain_config(name)
            except Exception as e:
                body += [f"\n---\n\n## {name}\n\n⚠️ config lỗi: {e}"]
                summary_rows.append((gkey, name, "?", 0, 0, 0, "CONFIG_ERR"))
                continue

            print(f">> {name} ...")
            body += [f"\n---\n\n## {name}  ({cfg.get('method')})", ""]

            if not cfg.get("enabled", True):
                body += ["**DISABLED** (`enabled: false`)", ""]
                if cfg.get("pitfalls"):
                    body += [f"- Lý do: {cfg['pitfalls']}", ""]
                summary_rows.append((gkey, name, cfg.get("method"), 0, 0, 0, "disabled"))
                continue

            body += _flow_description(cfg) + [""]

            scraper = build_scraper(cfg, http, dedup)
            try:
                raw_items = scraper.fetch_list()
            except Exception as e:
                body += [f"⚠️ fetch_list lỗi: {type(e).__name__}: {e}", ""]
                summary_rows.append((gkey, name, cfg.get("method"), 0, 0, 0, "FETCH_ERR"))
                continue

            is_rss = cfg.get("method") == "rss"
            n_feeds = len(cfg.get("rss", {}).get("feeds", [])) if is_rss else 1
            if is_rss:
                counts = Counter(i.get("_feed_name") for i in raw_items)
                cfg_feeds = [f.get("name", f.get("url")) for f in cfg.get("rss", {}).get("feeds", [])]
                body += ["**Breakdown theo feed:**", ""]
                for fn in cfg_feeds:
                    flag = "" if counts.get(fn) else " ⚠️ 0 item"
                    body += [f"- `{fn}`: {counts.get(fn, 0)} item{flag}"]
                body += [""]
            if scraper.errors:
                body += ["⚠️ **Lỗi fetch:** " + "; ".join(scraper.errors[:5]), ""]

            # chọn mẫu: RSS → n bài/feed; API → n bài đầu
            picked = []
            if is_rss:
                per_feed: dict[str, int] = {}
                for item in raw_items:
                    fn = item.get("_feed_name", "?")
                    if per_feed.get(fn, 0) >= n:
                        continue
                    try:
                        a = scraper.parse_item(item)
                    except Exception:
                        a = None
                    if a:
                        picked.append((item, a))
                        per_feed[fn] = per_feed.get(fn, 0) + 1
            else:
                for item in raw_items:
                    try:
                        a = scraper.parse_item(item)
                    except Exception:
                        a = None
                    if a:
                        picked.append((item, a))
                    if len(picked) >= n:
                        break

            if not picked:
                body += ["⚠️ 0 bài parse được (bị filter hết hoặc thiếu url/title)", ""]
                summary_rows.append((gkey, name, cfg.get("method"), n_feeds, len(raw_items), 0, "no-parse"))
                continue

            # Bài 1: pipeline đầy đủ; các bài sau: thẻ gọn
            raw0, a0 = picked[0]
            feed_tag = f" — feed: `{raw0['_feed_name']}`" if raw0.get("_feed_name") else ""
            body += [f"### 🔬 Pipeline đầy đủ — bài minh hoạ: {a0.title}{feed_tag}", ""]
            body += _full_pipeline_block(cfg, scraper, raw0, a0, dedup, sentiment_engine)
            if len(picked) > 1:
                body += [f"### 📋 {len(picked) - 1} bài mẫu khác (thẻ gọn)", ""]
                for raw_i, a_i in picked[1:]:
                    body += _compact_card(scraper, raw_i, a_i, sentiment_engine)

            avg_body = sum(len(a.content_text) for _, a in picked) // len(picked)
            note = ("EN" if cfg.get("language") == "en" else "") \
                + ("/summary-only" if not (cfg.get("detail") or {}).get("extract_full", True) else "")
            summary_rows.append((gkey, name, cfg.get("method"), n_feeds,
                                 len(raw_items), len(picked), note.strip("/") or "—"))
        group_files[gkey] = body

    # ---- README index ----
    readme = [
        "# Sample Articles — Index & Tổng quan",
        "",
        "Bộ báo cáo mẫu bài đăng theo **tầng nguồn tin** (đọc từ tổng quan → nhóm → chi tiết):",
        "",
    ]
    for gkey, ginfo in GROUPS.items():
        gdoms = [r[1] for r in summary_rows if r[0] == gkey]
        readme += [f"- **[{ginfo['title']}]({gkey}.md)** — {len(gdoms)} domain: {', '.join(gdoms)}"]
    readme += [
        "",
        "## Pipeline 6 giai đoạn (áp dụng cho MỌI bài — giải thích 1 lần tại đây)",
        "",
        "```",
        "[1] RAW      fetch_list()  — item thô từ RSS feed / API JSON",
        "[2] PARSE    parse_item()  — chuẩn hoá Article (url, title sạch, date ISO +07:00, symbols)",
        "[3] DEDUP    SHA-256(url+title) tra seen_articles + fuzzy title ≥90 (window 48h)",
        "[4] ENRICH   lấy body: inline content:encoded / fetch detail / summary-only",
        "[5] NLP      classify rule-based + sentiment lexicon VN (bài EN → neutral by design)",
        "[6] DB       Article.to_row() → INSERT OR IGNORE bảng articles (16 cột, SQLite WAL)",
        "```",
        "",
        "Trong mỗi domain: **bài đầu** minh hoạ đầy đủ 6 giai đoạn; các bài sau là thẻ gọn",
        "(vẫn chạy enrich + NLP thật, chỉ hiển thị kết quả chính).",
        "",
        "> **3 khái niệm 'domain':** (1) *domain config* = đơn vị scraper (bảng dưới);",
        "> (2) *feed* = nguồn con trong domain (breakdown trong từng section);",
        "> (3) *source_domain trong DB* = domain thật của URL bài — nhiều hơn config vì",
        "> aggregator (marketwatch thuộc Dow Jones → wsj.com/barrons.com). Bảng cuối trang.",
        "",
        "## Bảng tổng quan",
        "",
        "| Domain | Nhóm | Method | Feeds | Items/lần fetch | Bài mẫu | Ghi chú |",
        "|--------|------|--------|------:|------:|------:|---------|",
    ]
    for gkey, name, method, n_feeds, items, samples, note in summary_rows:
        readme += [f"| [{name}]({gkey}.md#{_anchor(name)}) | {gkey[3:]} | {method} "
                   f"| {n_feeds} | {items} | {samples} | {note} |"]

    # đối chiếu DB
    try:
        conn = store._connect()
        rows = conn.execute("SELECT source_domain, COUNT(*) n FROM articles "
                            "GROUP BY source_domain ORDER BY n DESC").fetchall()
        conn.close()
        readme += ["", "## Đối chiếu: source_domain thực tế trong DB", "",
                   f"{len(rows)} distinct source_domain (từ URL bài thật):", "",
                   "| source_domain | số bài |", "|---|---:|"]
        readme += [f"| {r['source_domain']} | {r['n']} |" for r in rows]
    except Exception as e:
        readme += ["", f"(Không đọc được DB: {e})"]

    dedup.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "README.md").write_text("\n".join(readme), encoding="utf-8")
    for gkey, body in group_files.items():
        (OUT_DIR / f"{gkey}.md").write_text("\n".join(body), encoding="utf-8")
    print(f"\n>>> Bộ báo cáo: {OUT_DIR.resolve()}\\README.md (+{len(group_files)} file nhóm)")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    n = 2
    if "--n" in argv:
        i = argv.index("--n")
        n = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    names = [a for a in argv if not a.startswith("--")]
    sys.exit(dump(names or None, n))
