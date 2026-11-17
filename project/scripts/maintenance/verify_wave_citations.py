"""Audit citation grounding and anti-copy invariants for article lane waves."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.article_run import wave_article_ids
from src.agent.silver_source import read_silver_text
from src.core import paths
from src.core.stdio import force_utf8_stdio
from src.db.preflight import resolve_db_path

force_utf8_stdio()

_BOILERPLATE_IMPLICATIONS = (
    "nội dung bài viết phản ánh thông tin và diễn biến quan trọng",
    "thông tin phản ánh diễn biến hoạt động kinh doanh, cơ cấu tài chính",
    "nội dung bài viết tác động tới nhận định thị trường",
)


def _norm(s: str) -> str:
    """Normalize text by collapsing whitespace and converting to lowercase.

    Args:
        s: Input text string.

    Returns:
        Normalized string with single whitespace separators.
    """
    return " ".join((s or "").split()).lower()


def load_cleaned_text(article_id: str, package_path: str | None, domain: str | None) -> str:
    """Load the full source cleaned content text for an article.

    Args:
        article_id: Hash identifier of the article.
        package_path: Relative or absolute path to the work package.
        domain: Domain of the publication source.

    Returns:
        Extracted cleaned text or an empty string if unresolvable.
    """
    candidate_paths: list[Path] = []
    if package_path:
        candidate_paths.append(paths.resolve_data_path(package_path))
    candidate_paths.append(paths.work_packages_dir() / f"{article_id}.json")
    candidate_paths.append(paths.agent_tasks_dir() / f"{article_id}.task.json")

    for p in candidate_paths:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                text = (
                    data.get("cleaned_text")
                    or (data.get("input") or {}).get("cleaned_text")
                    or ""
                )
                if text:
                    return text
            except (OSError, ValueError):
                continue

    silver = read_silver_text(domain, None, article_id)
    if silver:
        return silver

    return ""


def audit_wave_citations(
    wave_id: str,
    db_path: Path | None = None,
    sample_count: int = 5,
) -> dict:
    """Audit citation grounding and key points originality for a wave.

    Args:
        wave_id: Identifier of the wave to audit.
        db_path: Path to monocle.db SQLite file.
        sample_count: Number of sample articles to inspect in detail.

    Returns:
        Audit report dictionary with forensic statistics and findings.
    """
    db_file = db_path or resolve_db_path()
    article_ids = wave_article_ids(wave_id)

    if not article_ids:
        return {
            "wave_id": wave_id,
            "error": f"No map files or article IDs found for wave {wave_id}",
            "verdict": "FAIL",
        }

    uri = f"file:{db_file.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row

    try:
        raw_rows = []
        for i in range(0, len(article_ids), 400):
            chunk = article_ids[i : i + 400]
            marks = ",".join("?" * len(chunk))
            query = (
                f"SELECT ao.id, ao.article_id, ao.output_json, ao.dod_pass, ao.dod_reasons, "
                f"       wi.package_path, wi.domain, wi.raw_sha256 "
                f"FROM agent_outputs ao "
                f"LEFT JOIN work_items wi ON wi.id = ao.work_item_id "
                f"WHERE ao.article_id IN ({marks}) "
                f"ORDER BY ao.id DESC"
            )
            raw_rows.extend(conn.execute(query, chunk).fetchall())

        # Group by article_id, selecting the passing or most recent output
        records: dict[str, dict] = {}
        for r in raw_rows:
            aid = r["article_id"]
            if aid not in records or (r["dod_pass"] and not records[aid]["dod_pass"]):
                records[aid] = dict(r)

    finally:
        conn.close()

    total_citations = 0
    exact_grounded_citations = 0
    normalized_grounded_citations = 0
    citation_length_sum = 0
    min_citation_len = 999999
    max_citation_len = 0
    citation_failures: list[dict] = []

    total_key_points = 0
    copied_key_points = 0
    copy_violations: list[dict] = []

    implication_violations: list[dict] = []
    implication_length_sum = 0
    min_implication_len = 999999
    max_implication_len = 0

    sentiment_counts: dict[str, int] = {}
    time_sensitivity_counts: dict[str, int] = {}

    missing_cleaned_text: list[str] = []

    valid_sample_aids = [aid for aid in article_ids if aid in records]
    sample_targets: set[str] = set()
    if sample_count > 0 and valid_sample_aids:
        step = max(1, len(valid_sample_aids) // sample_count)
        for idx in range(0, len(valid_sample_aids), step):
            sample_targets.add(valid_sample_aids[idx])
            if len(sample_targets) >= sample_count:
                break
    sample_inspections: list[dict] = []

    for aid in article_ids:
        rec = records.get(aid)
        if not rec:
            continue

        raw_json = rec.get("output_json") or "{}"
        try:
            output = json.loads(raw_json)
        except (TypeError, ValueError):
            continue

        package_path = rec.get("package_path")
        domain = rec.get("domain")
        cleaned_text = load_cleaned_text(aid, package_path, domain)

        if not cleaned_text:
            missing_cleaned_text.append(aid)

        citations = output.get("citations") or []
        raw_cites: set[str] = set()
        norm_cites: set[str] = set()

        for idx, cit in enumerate(citations):
            span = cit if isinstance(cit, str) else (cit.get("source_span", "") if isinstance(cit, dict) else "")
            span_clean = span.strip()
            total_citations += 1
            span_len = len(span_clean)
            citation_length_sum += span_len
            min_citation_len = min(min_citation_len, span_len)
            max_citation_len = max(max_citation_len, span_len)

            raw_cites.add(span_clean)
            norm_cites.add(_norm(span_clean))

            if cleaned_text and span_clean in cleaned_text:
                exact_grounded_citations += 1
                normalized_grounded_citations += 1
            elif cleaned_text and _norm(span_clean) in _norm(cleaned_text):
                normalized_grounded_citations += 1
                citation_failures.append({
                    "article_id": aid,
                    "citation_index": idx,
                    "reason": "exact_whitespace_mismatch",
                    "preview": span_clean[:60],
                })
            else:
                citation_failures.append({
                    "article_id": aid,
                    "citation_index": idx,
                    "reason": "not_in_cleaned_text",
                    "preview": span_clean[:60],
                })

        key_points = output.get("key_points") or []
        for idx, kp in enumerate(key_points):
            kp_str = str(kp).strip()
            total_key_points += 1
            norm_kp = _norm(kp_str)

            if kp_str in raw_cites or norm_kp in norm_cites:
                copied_key_points += 1
                copy_violations.append({
                    "article_id": aid,
                    "kp_index": idx,
                    "reason": "verbatim_citation_copy",
                    "kp_preview": kp_str[:60],
                })

        impl = output.get("implication")
        impl_text = impl if isinstance(impl, str) else (impl.get("text", "") if isinstance(impl, dict) else "")
        impl_text = impl_text.strip()
        impl_len = len(impl_text)
        implication_length_sum += impl_len
        min_implication_len = min(min_implication_len, impl_len) if impl_len else min_implication_len
        max_implication_len = max(max_implication_len, impl_len)

        if impl_len < 40:
            implication_violations.append({"article_id": aid, "reason": "too_short", "len": impl_len})
        if cleaned_text and _norm(impl_text) in _norm(cleaned_text):
            implication_violations.append({"article_id": aid, "reason": "verbatim_content_copy"})
        if any(b in _norm(impl_text) for b in _BOILERPLATE_IMPLICATIONS):
            implication_violations.append({"article_id": aid, "reason": "boilerplate"})

        sent = output.get("sentiment", "unknown")
        sentiment_counts[sent] = sentiment_counts.get(sent, 0) + 1

        ts = output.get("time_sensitivity", "unknown")
        time_sensitivity_counts[ts] = time_sensitivity_counts.get(ts, 0) + 1

        if aid in sample_targets:
            sample_inspections.append({
                "article_id": aid,
                "citations_count": len(citations),
                "citations_sample": [
                    {
                        "preview": (cit if isinstance(cit, str) else (cit.get("source_span", "") if isinstance(cit, dict) else "")).strip()[:100],
                        "length": len((cit if isinstance(cit, str) else (cit.get("source_span", "") if isinstance(cit, dict) else "")).strip()),
                        "exact_grounded": ((cit if isinstance(cit, str) else (cit.get("source_span", "") if isinstance(cit, dict) else "")).strip() in cleaned_text) if cleaned_text else False,
                    }
                    for cit in citations[:2]
                ],
                "key_points_count": len(key_points),
                "key_points_sample": [
                    {
                        "preview": str(kp).strip()[:100],
                        "is_copied": str(kp).strip() in raw_cites or _norm(str(kp).strip()) in norm_cites,
                    }
                    for kp in key_points[:2]
                ],
                "implication": impl_text,
                "sentiment": sent,
                "time_sensitivity": ts,
            })

    ingested_count = len(records)
    dod_pass_count = sum(1 for r in records.values() if r.get("dod_pass") == 1)
    dod_pass_rate = dod_pass_count / max(1, ingested_count)
    exact_grounding_rate = exact_grounded_citations / max(1, total_citations)
    copy_rate = copied_key_points / max(1, total_key_points)

    verdict = (
        "APPROVE"
        if (
            exact_grounding_rate == 1.0
            and copy_rate == 0.0
            and dod_pass_rate >= 0.95
            and len(citation_failures) == 0
            and len(copy_violations) == 0
            and len(implication_violations) == 0
        )
        else "REQUEST_CHANGES"
    )

    report = {
        "wave_id": wave_id,
        "database": str(db_file),
        "total_wave_articles": len(article_ids),
        "ingested_articles": ingested_count,
        "dod_passed_articles": dod_pass_count,
        "dod_pass_rate": round(dod_pass_rate, 4),
        "citations": {
            "total_checked": total_citations,
            "exact_grounded": exact_grounded_citations,
            "exact_grounding_rate": round(exact_grounding_rate, 4),
            "normalized_grounded": normalized_grounded_citations,
            "avg_length": round(citation_length_sum / max(1, total_citations), 1),
            "min_length": min_citation_len if total_citations else 0,
            "max_length": max_citation_len,
            "failures_count": len(citation_failures),
            "sample_failures": citation_failures[:5],
        },
        "key_points": {
            "total_checked": total_key_points,
            "copied_count": copied_key_points,
            "copy_rate": round(copy_rate, 4),
            "copy_violations": copy_violations[:5],
        },
        "implications": {
            "avg_length": round(implication_length_sum / max(1, ingested_count), 1),
            "min_length": min_implication_len if ingested_count else 0,
            "max_length": max_implication_len,
            "violations_count": len(implication_violations),
            "sample_violations": implication_violations[:5],
        },
        "distributions": {
            "sentiments": sentiment_counts,
            "time_sensitivities": time_sensitivity_counts,
        },
        "missing_cleaned_text_count": len(missing_cleaned_text),
        "sample_inspections": sample_inspections,
        "verdict": verdict,
    }
    return report


def main() -> None:
    """Execute the wave citation and anti-copy audit via CLI."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wave", default="W_BKL_01_10301528", help="Wave identifier")
    parser.add_argument("--db", default=None, help="Path to monocle.db")
    parser.add_argument("--samples", type=int, default=5, help="Number of sample records to inspect in detail")
    parser.add_argument("--json", action="store_true", help="Print result as JSON")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else None
    report = audit_wave_citations(args.wave, db_path, sample_count=args.samples)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if report.get("verdict") == "APPROVE" else 1)

    print("\n" + "=" * 78)
    print(f" EMPIRICAL CHALLENGER AUDIT REPORT: WAVE {report.get('wave_id')}")
    print("=" * 78)
    print(f" Database        : {report.get('database')}")
    print(f" Wave Articles   : {report.get('total_wave_articles'):,} packed")
    print(f" Ingested Records: {report.get('ingested_articles'):,} rows")
    print(f" DoD Pass Rate   : {report.get('dod_passed_articles')}/{report.get('ingested_articles')} ({report.get('dod_pass_rate', 0):.2%})")

    c = report.get("citations", {})
    print("\n--- [1] CITATION GROUNDING (EXACT SUBSTRING CONTAINMENT) ---")
    print(f" Total Citations Checked  : {c.get('total_checked'):,}")
    print(f" Exact Substring Grounded : {c.get('exact_grounded'):,} ({c.get('exact_grounding_rate', 0):.2%})")
    print(f" Normalized Grounded      : {c.get('normalized_grounded'):,}")
    print(f" Length Distribution (c)  : min={c.get('min_length')}, avg={c.get('avg_length')}, max={c.get('max_length')} chars")
    print(f" Grounding Failures       : {c.get('failures_count')}")

    kp = report.get("key_points", {})
    print("\n--- [2] KEY POINTS ORIGINALITY (ANTI-COPY GATE) ---")
    print(f" Total Key Points Checked : {kp.get('total_checked'):,}")
    print(f" Copied from Citations    : {kp.get('copied_count')} ({kp.get('copy_rate', 0):.2%})")

    imp = report.get("implications", {})
    print("\n--- [3] MARKET IMPLICATION QUALITY ---")
    print(f" Length Distribution (im) : min={imp.get('min_length')}, avg={imp.get('avg_length')}, max={imp.get('max_length')} chars")
    print(f" Semantic Violations      : {imp.get('violations_count')}")

    dist = report.get("distributions", {})
    print("\n--- [4] SEMANTIC ENUM DISTRIBUTIONS ---")
    print(f" Sentiments               : {dist.get('sentiments')}")
    print(f" Time Sensitivities       : {dist.get('time_sensitivities')}")

    samples = report.get("sample_inspections", [])
    if samples:
        print("\n--- [5] FORENSIC SAMPLE INSPECTIONS ---")
        for s in samples:
            print(f" • Article {s['article_id']}:")
            print(f"   - Citations ({s['citations_count']} total):")
            for cs in s["citations_sample"]:
                status = "EXACT_MATCH" if cs["exact_grounded"] else "FAIL"
                print(f"     [{status}] ({cs['length']} chars) \"{cs['preview']}...\"")
            print(f"   - Key Points ({s['key_points_count']} total):")
            for ks in s["key_points_sample"]:
                status = "ORIGINAL" if not ks["is_copied"] else "COPY_VIOLATION"
                print(f"     [{status}] \"{ks['preview']}...\"")
            print(f"   - Implication ({len(s['implication'])} chars): \"{s['implication'][:100]}...\"")
            print(f"   - Metadata: sentiment={s['sentiment']}, time_sensitivity={s['time_sensitivity']}")

    print("\n" + "=" * 78)
    print(f" FINAL CHALLENGE VERDICT: {report.get('verdict')}")
    print("=" * 78 + "\n")

    sys.exit(0 if report.get("verdict") == "APPROVE" else 1)


if __name__ == "__main__":
    main()
