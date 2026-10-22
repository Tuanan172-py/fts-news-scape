"""Apply alias updates from the YAML configuration to the entity catalog file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core import paths
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

ENTITIES_JSON = paths.entities_dir() / "entities.json"

# Entity type -> group key in _load_all_domain_aliases().
_TYPE_TO_GROUP = {
    "INDUSTRY_GICS1": "industries", "INDUSTRY_GICS2": "industries", "INDUSTRY_GICS3": "industries",
    "MACRO_GEO": "nations", "MACRO_THEME": "themes",
    "ASSET_CLASS": "assets", "INSTITUTION": "institutions",
    "TICKER": "tickers",
}


def main(argv: list[str]) -> int:
    """Reapply YAML aliases onto `entities.json`.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        Process exit code, always 0.
    """
    ap = argparse.ArgumentParser(description="Áp lại alias yaml lên entities.json")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ báo cáo, không ghi")
    args = ap.parse_args(argv)

    # Late import: build_entities pulls in pandas and only the YAML loader is needed.
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
        # Mirror build_entities exactly:
        #  - TICKER: keep the existing legal aliases and append those from tickers.yaml.
        #  - _industry() puts the industry name first.
        #  - Other groups (nations/themes/assets/institutions) take the YAML list unchanged.
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
