"""Xuat ban toan bo ket qua phan tich ngay 2026-09-29 ra Excel va CSV giao hang."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# Dam bao encoding UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_CURRENT_DIR))

from process_batches import validate_batch_output

OUTPUTS_DIR = _CURRENT_DIR / "outputs"
PACKETS_DIR = _CURRENT_DIR / "packets"
USER_OUTPUT_DIR = _CURRENT_DIR.parent / "users" / "output" / "AnPT"

manifest_path = PACKETS_DIR / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
batches = manifest["batches"]

all_rows = []

for b in batches:
    bid = b["batch_id"]
    out_file = OUTPUTS_DIR / f"{bid}.output.json"
    map_file = PACKETS_DIR / f"{bid}.map.json"

    if not out_file.exists() or not map_file.exists():
        continue

    mapping = json.loads(map_file.read_text(encoding="utf-8"))
    content = out_file.read_text(encoding="utf-8")
    is_ok, records, _ = validate_batch_output(content, b["articles_count"])

    for r in records:
        idx_str = str(r["i"])
        meta = mapping.get(idx_str, {})
        all_rows.append({
            "article_id": meta.get("article_id", ""),
            "title": meta.get("title", ""),
            "domain": meta.get("domain", ""),
            "tier": "Tier 1 (Watchlist)" if meta.get("tier") == 1 else "Tier 2 (Market)",
            "tier_reason": meta.get("reason", ""),
            "sentiment": r.get("sentiment", ""),
            "materiality_score": r.get("materiality_score", 0.0),
            "summary": r.get("summary", ""),
            "key_points": " • " + "\n • ".join(r.get("key_points", [])),
            "citations": json.dumps(r.get("citations", [])),
        })

# Sap xep theo do quan trong giam dan
all_rows.sort(key=lambda x: (0 if "Tier 1" in x["tier"] else 1, -x["materiality_score"]))

csv_path = OUTPUTS_DIR / "processed_2026-09-29.csv"
fieldnames = [
    "tier",
    "tier_reason",
    "sentiment",
    "materiality_score",
    "title",
    "summary",
    "key_points",
    "domain",
    "article_id",
    "citations",
]

with open(csv_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"[+] Da xuat CSV tong hop: {csv_path} ({len(all_rows)} dong)")

# Xuat ra Excel
try:
    import pandas as pd
    df = pd.DataFrame(all_rows)
    xlsx_path = OUTPUTS_DIR / "processed_2026-09-29.xlsx"
    df.to_excel(xlsx_path, index=False)
    print(f"[+] Da xuat Excel tong hop: {xlsx_path}")

    # Xuat ban rieng cho user AnPT (Tier 1 Watchlist)
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tier1_df = df[df["tier"].str.contains("Tier 1")]
    anpt_xlsx = USER_OUTPUT_DIR / "2026-09-29-OpenRouter-AnPT.xlsx"
    tier1_df.to_excel(anpt_xlsx, index=False)
    print(f"[+] Da xuat ban giao hang AnPT: {anpt_xlsx} ({len(tier1_df)} bai)")
except Exception as e:
    print(f"[!] Loi xuat Excel: {e}")
