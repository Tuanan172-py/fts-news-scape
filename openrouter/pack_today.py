"""Dong goi toan bo bai dang trong ngay thanh cac Mega-Batch toi uu cho OpenRouter API."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Thiet lap duong dan import tu project
_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent / "project"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.agent.distill import distill
from src.agent.entities import load_registry
from src.core.stdio import force_utf8_stdio
from src.db.preflight import resolve_db_path

force_utf8_stdio()

PACKETS_DIR = _CURRENT_DIR / "packets"
MAX_LINE_LIMIT = 1900
DEFAULT_BATCH_COUNT = 25  # 25 lo (khoang 15 bai/lo) chay cuc nhanh (~75s), tranh timeout Cloudflare 300s

_MACRO_URGENT_RE = re.compile(
    r"(?:ngân\s*hàng\s*nhà\s*nước|nhnn|lãi\s*suất|tỷ\s*giá|room\s*tín\s*dụng"
    r"|lạm\s*phát|cpi|gdp|thuế\s*quan|thuế\s*chống\s*bán\s*phá\s*giá|thuế\s*tự\s*vệ"
    r"|fed|fomc|nâng\s*hạng|ftse|msci|trái\s*phiếu\s*doanh\s*nghiệp)",
    re.IGNORECASE,
)


def get_watchlist_universe(reg: Any) -> tuple[set[str], set[str]]:
    """Trich xuat tap hop ma co phieu va nganh theo doi tu danh muc."""
    watched: set[str] = set()
    for subs in (getattr(reg, "subscriptions", {}) or {}).values():
        watched |= set(subs)

    industries: set[str] = set()
    for eid in watched:
        ent = reg.entities.get(eid) or {}
        attrs = ent.get("attributes") or {}
        for key in ("gics1", "gics2", "gics3"):
            if attrs.get(key):
                industries.add(str(attrs[key]).strip().lower())
    return watched, industries


def classify_tier(title: str, reg: Any, watched: set[str], industries: set[str]) -> tuple[int, str]:
    """Phan loai tang uu tien cua bai viet (Tier 1: Watchlist/Macro, Tier 2: Background)."""
    detected = reg.detect(title or "")
    ids = {d["entity_id"] for d in detected}

    hit = ids & watched
    if hit:
        return 1, f"watchlist:{sorted(hit)[0]}"

    for d in detected:
        attrs = (reg.entities.get(d["entity_id"]) or {}).get("attributes") or {}
        for key in ("gics1", "gics2", "gics3"):
            val = str(attrs.get(key) or "").strip().lower()
            if val and val in industries:
                return 1, f"industry:{val}"

    if _MACRO_URGENT_RE.search(title or ""):
        return 1, "macro-urgent"

    return 2, "background"


def load_today_articles(target_date: str = "2026-09-29") -> list[dict[str, Any]]:
    """Truy van tat ca bai viet trong ngay co day du noi dung tu CSDL Monocle."""
    db_path = resolve_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql = """
        SELECT url_title_hash AS article_id, title, content_text, published_at, source_domain
        FROM articles
        WHERE substr(published_at, 1, 10) = ?
          AND content_text IS NOT NULL
          AND length(content_text) > 100
        ORDER BY published_at DESC, url_title_hash
    """
    rows = cur.execute(sql, (target_date,)).fetchall()
    conn.close()

    reg = load_registry()
    watched, industries = get_watchlist_universe(reg)

    articles = []
    for r in rows:
        tier, reason = classify_tier(r["title"], reg, watched, industries)
        articles.append({
            "article_id": r["article_id"],
            "title": r["title"].strip(),
            "content_text": r["content_text"],
            "published_at": r["published_at"],
            "domain": r["source_domain"],
            "tier": tier,
            "tier_reason": reason,
        })

    # Sap xep uu tien: Tier 1 len truoc
    tier1 = sorted([a for a in articles if a["tier"] == 1], key=lambda x: x["published_at"], reverse=True)
    tier2 = sorted([a for a in articles if a["tier"] == 2], key=lambda x: x["published_at"], reverse=True)
    return tier1 + tier2


def prepare_packets(target_date: str = "2026-09-29", num_batches: int = DEFAULT_BATCH_COUNT) -> dict[str, Any]:
    """Tien hanh chat loc doan van, dong goi cac lo Mega-Batch va ghi tep JSON."""
    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    articles = load_today_articles(target_date)
    total_articles = len(articles)

    if total_articles == 0:
        print(f"[!] Khong co bai bao nao trong ngay {target_date} de dong goi.")
        return {}

    batch_size = math.ceil(total_articles / num_batches)
    print("=" * 80)
    print(f"DONG GOI NGAY {target_date} — TONG CONG: {total_articles} BAI")
    print(f"So luong lo du kien: {num_batches} lo (khoang {batch_size} bai / lo)")
    print(f"Thu muc packet: {PACKETS_DIR}")
    print("=" * 80)

    manifest_batches = []
    for b_idx in range(num_batches):
        batch_id = f"batch_{target_date.replace('-', '')}_{b_idx + 1:02d}"
        slice_start = b_idx * batch_size
        slice_end = min((b_idx + 1) * batch_size, total_articles)
        batch_articles = articles[slice_start:slice_end]

        if not batch_articles:
            break

        packet_items = []
        mapping = {}

        for local_i, art in enumerate(batch_articles):
            paragraphs = distill(art["content_text"])
            if not paragraphs:
                paragraphs = [art["title"]]

            packet_items.append({
                "i": local_i,
                "t": art["title"],
                "p": paragraphs,
            })
            mapping[str(local_i)] = {
                "article_id": art["article_id"],
                "title": art["title"],
                "tier": art["tier"],
                "reason": art["tier_reason"],
                "domain": art["domain"],
            }

        packet_payload = {
            "date": target_date,
            "batch_id": batch_id,
            "total_items": len(packet_items),
            "articles": packet_items,
        }

        text_content = json.dumps(packet_payload, ensure_ascii=False, indent=1)

        task_path = PACKETS_DIR / f"{batch_id}.task.json"
        map_path = PACKETS_DIR / f"{batch_id}.map.json"

        task_path.write_text(text_content, encoding="utf-8")
        map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")

        sha256 = hashlib.sha256(text_content.encode("utf-8")).hexdigest()[:16]
        tier1_count = sum(1 for a in batch_articles if a["tier"] == 1)

        manifest_batches.append({
            "batch_id": batch_id,
            "batch_index": b_idx + 1,
            "articles_count": len(batch_articles),
            "tier1_count": tier1_count,
            "tier2_count": len(batch_articles) - tier1_count,
            "bytes_size": len(text_content.encode("utf-8")),
            "sha256": sha256,
            "task_file": str(task_path.name),
            "map_file": str(map_path.name),
        })

        print(f"  [+] {batch_id}: {len(batch_articles):2d} bai (Tier 1: {tier1_count:2d}) | "
              f"Size: {len(text_content)/1024:.1f} KB | Hash: {sha256}")

    manifest_data = {
        "target_date": target_date,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": total_articles,
        "total_tier1": sum(b["tier1_count"] for b in manifest_batches),
        "total_tier2": sum(b["tier2_count"] for b in manifest_batches),
        "total_batches": len(manifest_batches),
        "openrouter_requests_needed": len(manifest_batches),
        "openrouter_remaining_quota_after": 43 - len(manifest_batches),
        "batches": manifest_batches,
    }

    manifest_path = PACKETS_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 80)
    print(f"[OK] Da dong goi thanh cong {len(manifest_batches)} packets.")
    print(f"[OK] Chi phi OpenRouter: {len(manifest_batches)} requests / 43 con lai. Du tru an toan 18 requests.")
    print(f"[OK] Manifest tong the: {manifest_path}")
    print("=" * 80)
    return manifest_data


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else "2026-09-29"
    prepare_packets(date_arg, num_batches=25)
