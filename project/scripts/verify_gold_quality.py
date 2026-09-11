"""Đo lường chất lượng phân tích chuyên sâu Gold và kiểm định cổng DoD."""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.dod import _norm, check_dod, load_thresholds   # noqa: E402
from src.core.config import load_settings                     # noqa: E402
from src.core.stdio import force_utf8_stdio                    # noqa: E402
from src.db.store import ArticleStore                          # noqa: E402

force_utf8_stdio()

_SQL = """
SELECT o.id, o.article_id, o.output_json, o.dod_pass, o.agent_provider, o.model_used,
       w.package_path
FROM agent_outputs o
LEFT JOIN work_items w ON w.id = o.work_item_id
"""


def _load(s):
    try:
        return json.loads(s) if s else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _cleaned_text(package_path: str | None) -> str:
    """`cleaned_text` của work-package. Thiếu file → chuỗi rỗng (predicate liên quan bỏ qua)."""
    if not package_path:
        return ""
    try:
        return _load(Path(package_path).read_text(encoding="utf-8")).get("cleaned_text") or ""
    except OSError:
        return ""


def analyse(store: ArticleStore) -> dict:
    conn = store._connect_ro()
    try:
        rows = [dict(r) for r in conn.execute(_SQL)]
    finally:
        conn.close()

    th = load_thresholds()
    impl_counter: collections.Counter = collections.Counter()
    area_counter: collections.Counter = collections.Counter()
    prov_counter: collections.Counter = collections.Counter()
    kp_is_copy = 0
    boiler = 0
    failing: list[tuple[int, list[str]]] = []

    for r in rows:
        o = _load(r["output_json"])
        impl = ((o.get("implication") or {}).get("text") or "")
        impl_counter[_norm(impl)] += 1
        area_counter[(o.get("implication") or {}).get("impact_area")] += 1
        prov_counter[(r["agent_provider"], r["model_used"])] += 1
        if any(b and b in _norm(impl) for b in th["boilerplate_implications"]):
            boiler += 1
        spans = {_norm((c or {}).get("source_span", "")) for c in (o.get("citations") or [])}
        spans.discard("")
        kps = (o.get("summary") or {}).get("key_points") or []
        if kps and spans and all(_norm(k) in spans for k in kps):
            kp_is_copy += 1

        wp = {"cleaned_text": _cleaned_text(r["package_path"])}
        ok, reasons = check_dod(o, wp)
        # Predicate `grounded`/`auditable` cần work-package; thiếu file thì bỏ qua để không
        # kết tội oan vì Bronze đã dọn, chỉ giữ các lý do đọc được từ chính output.
        if not wp["cleaned_text"]:
            reasons = [x for x in reasons if "grounded" not in x and "cleaned_text" not in x]
            ok = not reasons
        if not ok and r["dod_pass"] == 1:
            failing.append((r["id"], reasons))

    n = len(rows) or 1
    return {
        "total": len(rows),
        "dod_pass": sum(1 for r in rows if r["dod_pass"] == 1),
        "implication_distinct": len(impl_counter),
        "implication_top": impl_counter.most_common(3),
        "implication_boilerplate": boiler,
        "implication_boilerplate_pct": round(100 * boiler / n, 1),
        "key_points_copy_citations": kp_is_copy,
        "key_points_copy_pct": round(100 * kp_is_copy / n, 1),
        "impact_area": dict(area_counter.most_common(6)),
        "provider": {f"{k[0]}/{k[1]}": v for k, v in prov_counter.most_common(6)},
        "would_fail_new_gate": len(failing),
        "_failing": failing,
    }


def _print_report(res: dict) -> None:
    n = res["total"] or 1
    print(f"agent_outputs           : {res['total']}")
    print(f"dang dod_pass=1         : {res['dod_pass']} ({round(100*res['dod_pass']/n,1)}%)")
    print(f"implication distinct    : {res['implication_distinct']}  <-- cang thap cang la template")
    print(f"implication boilerplate : {res['implication_boilerplate']} ({res['implication_boilerplate_pct']}%)")
    print(f"key_points = citations  : {res['key_points_copy_citations']} ({res['key_points_copy_pct']}%)")
    print(f"impact_area             : {res['impact_area']}")
    print(f"provider/model          : {res['provider']}")
    print(f"SE TRUOT cong moi       : {res['would_fail_new_gate']}")
    print("\n3 cau implication pho bien nhat:")
    for text, cnt in res["implication_top"]:
        print(f"  {cnt:6d}  {text[:90]}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="ha dod_pass ve 0 cho ban ghi truot cong moi (doc ADR 0004 truoc)")
    ap.add_argument("--json", action="store_true", help="in ket qua dang JSON")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path, init_schema=False)
    res = analyse(store)

    if args.json:
        print(json.dumps({k: v for k, v in res.items() if not k.startswith("_")},
                         ensure_ascii=False, indent=2))
    else:
        _print_report(res)

    if not args.apply:
        if res["would_fail_new_gate"]:
            print(f"\n(chi bao cao) Chay lai voi --apply de ha co {res['would_fail_new_gate']} "
                  f"ban ghi. Backup {db_path} truoc.")
        return 0

    for row_id, reasons in res["_failing"]:
        store.set_agent_dod(row_id, 0, json.dumps(reasons, ensure_ascii=False))
    print(f"\nDa ha dod_pass=0 cho {len(res['_failing'])} ban ghi. "
          f"output_json GIU NGUYEN. Cac bai nay se quay lai hang doi Gold vong sau.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
