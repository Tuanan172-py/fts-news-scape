"""
Chẩn đoán từng domain: fetch_list() + parse_item() sample, báo lỗi.
Bỏ qua dedup/DB/enrich để test sạch kết nối + parse của TỪNG nguồn.

Usage:
    python scripts/diagnose_sources.py            # tất cả domain có config
    python scripts/diagnose_sources.py cafef tnck
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

# Windows console cp1252 → ép utf-8 để in tiếng Việt không crash
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

import src.scrapers  # noqa: F401 — trigger @register


def diagnose(names: list[str] | None = None, enrich_test: bool = True) -> int:
    setup_logging("WARNING", "logs")  # tắt log INFO ồn ào
    store = ArticleStore("data/monocle.db")
    dedup = DedupCache(store)
    http = HTTPClient(rate_limit_delay=3.0, max_retries=3)

    names = names or list_domains(enabled_only=False)
    rows = []
    for name in names:
        row = {"name": name, "method": "?", "enabled": True,
               "fetched": 0, "parsed": 0, "status": "", "detail": ""}
        try:
            cfg = load_domain_config(name)
        except Exception as e:
            row.update(status="CONFIG_ERR", detail=str(e)[:120])
            rows.append(row)
            continue
        row["method"] = cfg.get("method", "?")
        row["enabled"] = cfg.get("enabled", True)
        if not row["enabled"]:
            row.update(status="DISABLED", detail="enabled: false")
            rows.append(row)
            continue

        try:
            scraper = build_scraper(cfg, http, dedup)
        except Exception as e:
            row.update(status="BUILD_ERR", detail=str(e)[:120])
            rows.append(row)
            continue

        t0 = time.monotonic()
        try:
            raw = scraper.fetch_list()
            row["fetched"] = len(raw)
        except Exception as e:
            row.update(status="FETCH_ERR",
                       detail=f"{type(e).__name__}: {str(e)[:100]}")
            rows.append(row)
            continue

        # thử parse tối đa 10 item đầu, giữ lại article để test enrich
        parsed, perrs, arts = 0, [], []
        for item in raw[:10]:
            try:
                a = scraper.parse_item(item)
                if a:
                    parsed += 1
                    arts.append(a)
            except Exception as e:
                perrs.append(f"{type(e).__name__}: {str(e)[:60]}")
        row["parsed"] = parsed

        # test enrich (fetch trang chi tiết) trên 2 bài đầu — điểm dễ lỗi
        # bỏ qua api nặng (cafef/fireant enrich 600 bài, có luồng riêng)
        enr_ok, enr_err = 0, []
        if enrich_test and row["method"] != "api":
            for a in arts[:2]:
                try:
                    scraper.enrich(a)
                    has_body = bool((a.content_text or "").strip())
                    if has_body:
                        enr_ok += 1
                    else:
                        enr_err.append("empty content_text")
                except Exception as e:
                    enr_err.append(f"{type(e).__name__}: {str(e)[:50]}")

        dt = time.monotonic() - t0
        if row["fetched"] == 0:
            row.update(status="EMPTY", detail=f"0 items ({dt:.1f}s)")
        elif parsed == 0:
            row.update(status="PARSE_ERR",
                       detail="; ".join(perrs[:2]) or "parse trả None")
        elif enrich_test and row["method"] != "api" and enr_ok == 0 and arts:
            row.update(status="ENRICH_ERR",
                       detail="; ".join(enr_err[:2]) or "enrich rỗng")
        elif perrs or enr_err:
            note = perrs[0] if perrs else enr_err[0]
            row.update(status="OK*",
                       detail=f"parse {parsed}/{min(10,len(raw))}, enrich {enr_ok}; lỗi: {note}")
        else:
            row.update(status="OK", detail=f"enrich {enr_ok}/2 ok ({dt:.1f}s)")
        rows.append(row)
        print(f"  [{row['status']:>10}] {name:<14} fetched={row['fetched']:<4} {row['detail']}")

    dedup.close()

    # bảng tổng kết
    print("\n" + "=" * 78)
    print(f"{'DOMAIN':<15}{'METHOD':<7}{'FETCH':>6}  {'STATUS':<11}DETAIL")
    print("-" * 78)
    bad = []
    for r in rows:
        print(f"{r['name']:<15}{r['method']:<7}{r['fetched']:>6}  "
              f"{r['status']:<11}{r['detail'][:34]}")
        if r["status"] not in ("OK", "OK*", "DISABLED"):
            bad.append(r)
    print("=" * 78)
    ok = sum(1 for r in rows if r["status"] in ("OK", "OK*"))
    print(f"TỔNG: {len(rows)} domain | OK={ok} | "
          f"disabled={sum(1 for r in rows if r['status']=='DISABLED')} | "
          f"LỖI={len(bad)}")
    if bad:
        print("\nCÁC NGUỒN CÓ VẤN ĐỀ:")
        for r in bad:
            print(f"  ✗ {r['name']:<14} [{r['status']}] {r['detail']}")
    return len(bad)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_enrich = "--no-enrich" in sys.argv
    sys.exit(diagnose(args or None, enrich_test=not no_enrich))
