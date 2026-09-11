"""Cập nhật các bí danh từ cấu hình YAML vào tệp danh mục thực thể."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTITIES_JSON = PROJECT_ROOT / "data" / "entities" / "entities.json"

# type thực thể -> khoá nhóm trong _load_all_domain_aliases()
_TYPE_TO_GROUP = {
    "INDUSTRY_GICS1": "industries", "INDUSTRY_GICS2": "industries", "INDUSTRY_GICS3": "industries",
    "MACRO_GEO": "nations", "MACRO_THEME": "themes",
    "ASSET_CLASS": "assets", "INSTITUTION": "institutions",
    "TICKER": "tickers",
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Áp lại alias yaml lên entities.json")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ báo cáo, không ghi")
    args = ap.parse_args(argv)

    # import muộn: build_entities kéo theo pandas, chỉ cần hàm nạp yaml
    from scripts.build_entities import _load_all_domain_aliases

    groups = _load_all_domain_aliases()
    doc = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))

    changed = 0
    for e in doc["entities"]:
        group = _TYPE_TO_GROUP.get(e["type"])
        if not group:
            continue
        cfg = groups.get(group, {}).get(e["code"])
        if cfg is None:
            continue
        extra = cfg.get("aliases", []) if isinstance(cfg, dict) else list(cfg)
        # Mirror ĐÚNG build_entities:
        #  - TICKER: giữ các alias pháp lý có sẵn, chỉ append thêm các alias trong tickers.yaml
        #  - _industry() ghép tên ngành lên đầu
        #  - các nhóm khác (nations/themes/assets/institutions) lấy NGUYÊN danh sách trong yaml.
        if e["type"] == "TICKER":
            merged = list(e.get("aliases") or [])
        elif e["type"].startswith("INDUSTRY_"):
            merged = [e["canonical_name"]]
        else:
            merged = []
        for a in extra:
            a = str(a).strip()
            if a and a not in merged:
                merged.append(a)

        if merged != e.get("aliases"):
            before = len(e.get("aliases") or [])
            print(f"  {e['entity_id']:46} {before} -> {len(merged)} alias")
            if not args.dry_run:
                e["aliases"] = merged
            changed += 1

    if changed and not args.dry_run:
        ENTITIES_JSON.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'DRY-RUN ' if args.dry_run else ''}cập nhật: {changed} thực thể")
    print("Lưu ý: entities.csv/xlsx chỉ được sinh lại bởi scripts/build_entities.py "
          "(cần FRA - Data đã tải về máy).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
