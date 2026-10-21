"""Expand the compact model record into the two full schemas at zero token cost."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.entities import load_registry           # noqa: E402
from src.core import paths                             # noqa: E402
from src.agent.intent_resolve import (                 # noqa: E402
    GROUPS_WITHOUT_RESOLVER,
    IntentResolver,
    ResolveReport,
    reconcile,
)
from src.agent.article_contract import (               # noqa: E402,F401
    MIN_CITATION_CHARS,
    SENTIMENT_MAP,
    TIME_MAP,
    parse_and_validate,
    salvage_records,
    unwrap_tool_envelope,
)
from src.agent.l1_router import TYPE_GROUP             # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = paths.article_packets_dir()
IN_DIR = paths.agent_outputs_dir("_article")
L1_OUT_DIR = paths.agent_outputs_dir("_l1")
GOLD_OUT_DIR = paths.agent_outputs_dir()
MENTIONS_DIR = paths.article_mentions_dir()

CATEGORY_KEYS = ("ticker_company", "etf_fund", "index", "exchange",
                 "industry_sector", "macro_geo", "asset_class", "institution")

UNKNOWN_PROVENANCE = "unknown"


def now_vn_iso() -> str:
    """Build the current timestamp in the Vietnam time zone.

    Returns:
        ISO 8601 timestamp string with the UTC offset.
    """
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")


def build_l1_output(article_id: str, title: str, resolved: list,
                    labels: dict[str, str], *,
                    agent_provider: str = UNKNOWN_PROVENANCE,
                    model_used: str = UNKNOWN_PROVENANCE) -> dict:
    """Build the entity recognition record in the `l1-entity-output-v1` schema.

    The schema requires every verbatim string to appear in the title, so only
    entities found in the title are included. Entities the model found in the
    body go to the side file built by :func:`build_mentions`: they help catalog
    expansion but do not fit this schema.

    Args:
        article_id: Article identifier.
        title: Verbatim title.
        resolved: Resolved entity list.
        labels: Reconciliation labels between the model and the code layer.
        agent_provider: Analysis runtime provider.
        model_used: Name of the model used.

    Returns:
        Record dict conforming to the schema.
    """
    in_title = [e for e in resolved if e.in_title and e.surface in title]

    entities = []
    for e in in_title:
        if not (e.in_list and e.entity_id and e.type):
            continue
        entities.append({
            "surface": e.surface,
            "entity_id": e.entity_id,
            "type": e.type,
            "method": e.method,
            "in_list": True,
        })

    unlisted = sorted({e.surface for e in resolved if not e.in_list and e.surface})

    groups = {TYPE_GROUP.get(e["type"]) for e in entities}
    recognized = bool(entities)
    categories = {}
    for key in CATEGORY_KEYS:
        if key in groups:
            categories[key] = "done"
        elif recognized and unlisted:
            categories[key] = "none"
        else:
            categories[key] = "none"

    citations = [{"source_span": entities[0]["surface"]}] if recognized else []

    return {
        "l1_output_version": "1.0",
        "article_id": article_id,
        "title": title,
        "recognized": recognized,
        "entities": entities,
        "categories": categories,
        "unlisted_candidates": unlisted,
        "citations": citations,
        "processing_metadata": {
            "agent_provider": agent_provider,
            "model_used": model_used,
            "timestamp": now_vn_iso(),
            "intent_source": labels,
        },
    }


def _is_index(value) -> bool:
    """Check that a value is a true integer index, excluding booleans.

    Args:
        value: Value to check.

    Returns:
        True when the value is an `int` and not a `bool`.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def build_gold_output(article_id: str, record: dict, paragraphs: list[str]) -> tuple[dict | None, str]:
    """Build the content analysis record in the `agent-output-v2-lean` schema.

    Citations are taken verbatim by the paragraph indexes the model gives, so
    they are always exact substrings of the source content and need no
    re-verification. When an article has only one paragraph long enough to cite,
    one citation suffices and the record carries a `citation_basis` marker so
    the DoD gate relaxes the threshold accordingly.

    Args:
        article_id: Article identifier.
        record: Compact record emitted by the model.
        paragraphs: Paragraph array sent to the model in the packet.

    Returns:
        Pair of the schema-conforming record and a reason string when the
        article must be skipped.
    """
    summary = (record.get("s") or "").strip()
    implication = (record.get("im") or "").strip()
    key_points = [str(k).strip() for k in (record.get("k") or []) if str(k).strip()]

    if not summary:
        return None, "thiếu tóm tắt"
    if len(implication) < 40:
        return None, "hàm ý ngắn hơn 40 ký tự"
    if not key_points:
        return None, "thiếu luận điểm"
    if record.get("sn") not in SENTIMENT_MAP:
        return None, "sn ngoài enum"
    if record.get("ts") not in TIME_MAP:
        return None, "ts ngoài enum"

    eligible = [p for p in paragraphs if len(p) >= MIN_CITATION_CHARS]
    need = 1 if len(eligible) < 2 else 2
    citations: list[str] = []
    for raw in record.get("c") or []:
        if _is_index(raw) and 0 <= raw < len(paragraphs):
            para = paragraphs[raw]
            if len(para) >= MIN_CITATION_CHARS and para not in citations:
                citations.append(para)
    if len(citations) < need:
        return None, "không đủ hai đoạn trích dẫn hợp lệ" if need == 2 else "không đủ trích dẫn hợp lệ"

    # Key points must not copy a citation verbatim (anti-copy gate).
    key_points = [k for k in key_points if k not in citations]
    if not key_points:
        return None, "luận điểm trùng nguyên văn trích dẫn"

    row = {
        "article_id": article_id,
        "summary": summary,
        "key_points": key_points,
        "implication": implication,
        "sentiment": SENTIMENT_MAP[record["sn"]],
        "time_sensitivity": TIME_MAP[record["ts"]],
        "citations": citations,
    }
    if need == 1:
        row["citation_basis"] = "single-paragraph"
    return row, ""


def build_mentions(article_id: str, title: str, resolved: list,
                   labels: dict[str, str]) -> dict:
    """Record the entities the model found outside the title.

    The current recognition schema accepts only strings located in the title,
    so these entities have no official place to live. They are kept because
    they feed catalog expansion, and because the person-name group only becomes
    useful once enough of it accumulates.

    Args:
        article_id: Article identifier.
        title: Verbatim title.
        resolved: Resolved entity list.
        labels: Reconciliation labels between the model and the code layer.

    Returns:
        Side-file dict listing the entities found outside the title.
    """
    body = [e for e in resolved if not e.in_title]
    return {
        "article_id": article_id,
        "title": title,
        "created_at": now_vn_iso(),
        "mentions": [{
            "surface": e.surface,
            "group": e.group,
            "entity_id": e.entity_id,
            "type": e.type,
            "in_list": e.in_list,
            "source": "body",
        } for e in body],
        "intent_source": labels,
    }


def load_repair_ids(task_dir: Path, batch_id: str) -> set[str]:
    """Collect article ids that repair batches of the same wave already provided.

    When a batch is truncated, the missing part is repacked as a separate repair
    batch with an _rNN suffix. A repair batch carries exactly the article ids
    for which the original batch produced no record. Counting the original
    batch's missing part while ignoring repair batches makes every repaired wave
    report a failure above the threshold, and --finish blocks even the ingest
    step although the real coverage is sufficient.

    Args:
        task_dir: Directory holding packets and mapping files.
        batch_id: Original batch id under review, without the repair suffix.

    Returns:
        Set of article ids that have records thanks to repair batches of the
        same wave.
    """
    provided: set[str] = set()
    for map_path in sorted(glob.glob(str(task_dir / f"{batch_id}_r*.map.json"))):
        try:
            sibling = json.loads(Path(map_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        provided.update(str(v) for v in (sibling.get("index") or {}).values())
    return provided


def process_batch(batch_id: str, out_text: str, packet: dict, mapping: dict,
                  resolver: IntentResolver, reg, report: ResolveReport,
                  repaired_ids: set[str] | None = None,
                  default_provenance: tuple[str, str] | None = None) -> dict:
    """Process one model output batch into result files.

    Args:
        batch_id: Batch id.
        out_text: Raw text the model returned.
        packet: Packet content sent to the model.
        mapping: Mapping from local index to article id.
        resolver: Identifier resolver.
        reg: Entity registry.
        report: Resolution statistics counter.
        repaired_ids: Article ids already provided by repair batches of the
            same wave. Articles in this set are not counted as missing because
            their records are already on disk.
        default_provenance: (provider, model) pair used when the batch has no
            meta file. When omitted, a batch without meta is rejected.

    Returns:
        Statistics dict describing the batch processing result.
    """
    parsed = parse_and_validate(out_text, packet)
    broken = parsed.counters.get("broken", 0)
    by_index = {str(i): r for i, r in parsed.records.items()}
    index_map = mapping.get("index") or {}
    articles = {str(a.get("i")): a for a in (packet.get("a") or [])}

    L1_OUT_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_OUT_DIR.mkdir(parents=True, exist_ok=True)
    MENTIONS_DIR.mkdir(parents=True, exist_ok=True)

    repaired_ids = repaired_ids or set()
    l1_rows: list[dict] = []
    gold_rows: list[dict] = []
    mention_rows: list[dict] = []
    missing: list[str] = []
    gold_skipped: list[tuple[str, str]] = []

    meta_path = IN_DIR / f"{batch_id}.meta.json"
    batch_provider = batch_model = ""
    if meta_path.exists():
        try:
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            batch_provider = meta_data.get("agent_provider") or ""
            batch_model = meta_data.get("model_used") or ""
        except (OSError, ValueError):
            pass
    if not (batch_provider and batch_model) and default_provenance:
        batch_provider, batch_model = default_provenance
    if not (batch_provider and batch_model):
        return {"batch_id": batch_id,
                "error": "thiếu meta provenance (agent_provider, model_used)",
                "expected": len(index_map), "owned": len(index_map), "repaired": 0,
                "records": 0, "invalid": {}, "counters": {}, "broken": 0,
                "missing": list(index_map), "l1": 0, "gold": 0, "mentions": 0,
                "gold_skipped": [], "parse_fail_rate": 1.0}

    for idx, article_id in index_map.items():
        rec = by_index.get(idx)
        if rec is None:
            # An article already recorded by a repair batch is not missing;
            # counting it here would charge the same cost twice.
            if str(article_id) not in repaired_ids:
                missing.append(idx)
            continue
        src = articles.get(idx) or {}
        title = src.get("t") or ""
        paragraphs = src.get("p") or []

        resolved = resolver.resolve_many(rec.get("e") or [], title=title, report=report)
        code_ids = {d["entity_id"] for d in reg.detect(title)}
        labels = reconcile(resolved, code_ids)

        l1_rows.append(build_l1_output(article_id, title, resolved, labels,
                                       agent_provider=batch_provider,
                                       model_used=batch_model))

        gold, reason = build_gold_output(article_id, rec, paragraphs)
        if gold:
            gold_rows.append(gold)
        else:
            gold_skipped.append((idx, reason))

        mentions = build_mentions(article_id, title, resolved, labels)
        if mentions["mentions"]:
            mention_rows.append(mentions)

    if l1_rows:
        (L1_OUT_DIR / f"{batch_id}.output.json").write_text(
            json.dumps(l1_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if gold_rows:
        (GOLD_OUT_DIR / f"{batch_id}.output.json").write_text(
            json.dumps(gold_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if mention_rows:
        (MENTIONS_DIR / f"{batch_id}.mentions.json").write_text(
            json.dumps(mention_rows, ensure_ascii=False, indent=1), encoding="utf-8")

    # The failure-count ceiling is the number of articles this batch must really
    # produce, after subtracting the part repair batches carry.
    owned = sum(1 for a in index_map.values() if str(a) not in repaired_ids)
    total = len(index_map)
    return {
        "batch_id": batch_id,
        "expected": total,
        "owned": owned,
        "repaired": total - owned,
        "records": len(parsed.records),
        "invalid": {str(i): codes for i, codes in parsed.errors.items()},
        "counters": parsed.counters,
        "broken": broken,
        "missing": missing,
        "l1": len(l1_rows),
        "gold": len(gold_rows),
        "mentions": len(mention_rows),
        "gold_skipped": gold_skipped,
        # The next two sets serve the wave-wide gate in main: an article with a
        # record in any batch (including sibling repair batches, not only direct
        # children) counts as received.
        "received_ids": sorted({index_map[idx] for idx in by_index if idx in index_map}),
        "all_ids": sorted(set(index_map.values())),
        # The denominator is the part this batch must really produce, not the
        # whole packet. A repair batch already paid for its share, so counting
        # that share here would count it twice.
        "parse_fail_rate": (len(missing) + broken) / owned if owned else 0.0,
    }


def drop_superseded_expanded(results: list[dict], outputs: list[str]) -> int:
    """Drop old expanded rows when a newer record exists in another batch.

    A refresh round yields a second record for the same article (the old one
    from a short-excerpt packet, the new one from the full Silver body).
    Expanded files are written per batch, so the old row stays on disk and the
    ingest gate rejects it because its citations cannot be matched against the
    new body, blocking the whole wave although the new record passed. Exactly
    one row per article is kept: the row from the batch with the newest raw
    output. Raw model outputs are untouched, so the audit trail stays intact.
    When there are no duplicates, no file is modified.

    Args:
        results: Per-batch statistics of the current expansion round.
        outputs: Paths of the raw output files just processed.

    Returns:
        Number of rows removed from the expanded files.
    """
    order: dict[str, tuple[float, str]] = {}
    for out_path in outputs:
        batch_id = Path(out_path).name.replace(".output.json", "")
        try:
            order[batch_id] = (Path(out_path).stat().st_mtime, batch_id)
        except OSError:
            continue
    by_batch: dict[str, list[tuple[str, dict]]] = {}
    for kind, filename, out_dir in (
            ("l1", ".output.json", L1_OUT_DIR),
            ("gold", ".output.json", GOLD_OUT_DIR),
            ("mentions", ".mentions.json", MENTIONS_DIR)):
        for r in results:
            path = out_dir / f"{r['batch_id']}{filename}"
            if not path.exists():
                continue
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and row.get("article_id"):
                    by_batch.setdefault(r["batch_id"], []).append((kind, row))
    if not any(len(items) > 0 for items in by_batch.values()):
        return 0
    seen: dict[str, tuple[float, str]] = {}
    for batch_id, items in by_batch.items():
        for _kind, row in items:
            aid = row["article_id"]
            stamp = order.get(batch_id, (0.0, batch_id))
            if aid not in seen or stamp > seen[aid]:
                seen[aid] = stamp
    dropped = 0
    for r in results:
        for kind, filename, out_dir in (
                ("l1", ".output.json", L1_OUT_DIR),
                ("gold", ".output.json", GOLD_OUT_DIR),
                ("mentions", ".mentions.json", MENTIONS_DIR)):
            path = out_dir / f"{r['batch_id']}{filename}"
            if not path.exists():
                continue
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(rows, list):
                continue
            stamp = order.get(r["batch_id"], (0.0, r["batch_id"]))
            kept = [row for row in rows
                    if not (isinstance(row, dict) and row.get("article_id"))
                    or seen.get(row["article_id"]) == stamp]
            if len(kept) != len(rows):
                dropped += len(rows) - len(kept)
                path.write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                                encoding="utf-8")
                if kind in r:
                    r[kind] = len(kept)
    return dropped


def main(argv=None) -> int:
    """Run the command-line interface that expands compact records.

    Args:
        argv: Command-line argument list. Defaults to `sys.argv`.

    Returns:
        Exit code 0 on success (in wave mode, the wave-wide failure rate is
        below the threshold), 1 when the failure threshold is exceeded, 2 when
        there is no work.
    """
    ap = argparse.ArgumentParser(description="Bung bản ghi gọn thành hai lược đồ đầy đủ")
    ap.add_argument("source", nargs="?", default=str(IN_DIR),
                    help="Thư mục chứa đầu ra thô của mô hình")
    ap.add_argument("--task-dir", default=str(TASK_DIR), help="Thư mục chứa packet")
    ap.add_argument("--batch", help="Chỉ xử lý một lô cụ thể")
    ap.add_argument("--wave", help="Chỉ xử lý các lô của một đợt, gồm cả lô vá")
    ap.add_argument("--default-provider", help="Provider cho lô không có tệp meta, ví dụ dsh")
    ap.add_argument("--default-model", help="Mô hình cho lô không có tệp meta")
    ap.add_argument("--fail-threshold", type=float, default=0.10,
                    help="Tỷ lệ hỏng khiến lệnh trả mã lỗi")
    ap.add_argument("--json", action="store_true", help="Xuất thống kê dạng JSON")
    args = ap.parse_args(argv)

    src_dir = Path(args.source)
    task_dir = Path(args.task_dir)
    # Without a filter, every completion would re-expand all old waves in the
    # directory, and the "worst" failure rate would span long-closed waves.
    pattern = (f"{args.batch}.output.json" if args.batch
               else f"article_{args.wave}_*.output.json" if args.wave
               else "*.output.json")
    outputs = sorted(glob.glob(str(src_dir / pattern)))
    if not outputs:
        print(f"Không có đầu ra nào trong {src_dir}. Chạy wave trước đã.")
        return 2

    reg = load_registry()
    resolver = IntentResolver(reg)
    report = ResolveReport()
    results = []

    for out_path in outputs:
        batch_id = Path(out_path).name.replace(".output.json", "")
        packet_path = task_dir / f"{batch_id}.task.json"
        map_path = task_dir / f"{batch_id}.map.json"
        if not packet_path.exists() or not map_path.exists():
            print(f"⚠️  Bỏ qua {batch_id}: thiếu packet hoặc bảng ánh xạ.")
            continue
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
        text = Path(out_path).read_text(encoding="utf-8")
        repaired_ids = load_repair_ids(task_dir, batch_id)
        default_prov = ((args.default_provider, args.default_model or args.default_provider)
                        if args.default_provider else None)
        results.append(process_batch(batch_id, text, packet, mapping, resolver, reg,
                                     report, repaired_ids, default_prov))

    if not results:
        print("Không lô nào xử lý được.")
        return 2

    dropped = drop_superseded_expanded(results, outputs)
    if dropped:
        print(f"Đã bỏ {dropped} hàng bung cũ bị bản ghi mới hơn thay thế.")

    # Wave-wide gate: an article with a record in any batch counts as received.
    # Counting missing items by the worst batch and blocking the whole wave is
    # wrong when repair batches overlap generations (E1): an article missing in
    # the parent batch but present in a sibling repair batch would still count
    # as failed. The per-batch table is kept for inspection and is not used to
    # block in wave mode.
    wave_ids: set[str] = set()
    wave_got: set[str] = set()
    for r in results:
        wave_ids.update(r.get("all_ids") or [])
        wave_got.update(r.get("received_ids") or [])
    wave_missing = sorted(wave_ids - wave_got)
    wave_rate = len(wave_missing) / len(wave_ids) if wave_ids else 0.0

    if args.json:
        print(json.dumps({"batches": results,
                          "resolve": report.summary(),
                          "wave_fail_rate": wave_rate,
                          "wave_missing": wave_missing}, ensure_ascii=False))
        return 0

    no_meta = [r["batch_id"] for r in results if r.get("error")]
    if no_meta:
        print(f"Lô thiếu meta provenance, không bung: {', '.join(no_meta)}")
        print("Ghi tệp meta cho lô, hoặc truyền --default-provider và --default-model.")
        return 1
    worst = max(r["parse_fail_rate"] for r in results)
    print("=" * 84)
    print(" 🧩  BUNG BẢN GHI GỌN THÀNH LƯỢC ĐỒ ĐẦY ĐỦ")
    print("=" * 84)
    print(f"{'lô':28} {'chờ':>5} {'nhận':>6} {'L1':>5} {'nội dung':>9} {'hỏng':>6} {'thiếu':>6} {'vá':>5}")
    print("-" * 90)
    for r in results:
        print(f"{r['batch_id']:28} {r['expected']:>5} {r['records']:>6} {r['l1']:>5} "
              f"{r['gold']:>9} {r['broken']:>6} {len(r['missing']):>6} "
              f"{r['repaired']:>5}")
    print("-" * 90)

    print("\nTỷ lệ tra cứu định danh theo nhóm:")
    for group, total, ok, rate in report.summary():
        note = "  (chưa có bảng tra, đúng thiết kế)" if group in GROUPS_WITHOUT_RESOLVER else ""
        print(f"  {group:5} {ok:>4}/{total:<4} {rate:>6.0%}{note}")

    skipped = [(r["batch_id"], s) for r in results for s in r["gold_skipped"]]
    if skipped:
        print(f"\nBài không dựng được phần nội dung: {len(skipped)}")
        for batch_id, (idx, reason) in skipped[:8]:
            print(f"  {batch_id} #{idx}: {reason}")

    invalid = [(r["batch_id"], i, c) for r in results for i, c in r["invalid"].items()]
    if invalid:
        print(f"\nBản ghi bị từ chối theo hợp đồng, chuyển sang vòng vá: {len(invalid)}")
        for batch_id, idx, codes in invalid[:8]:
            print(f"  {batch_id} #{idx}: {','.join(codes)}")

    print(f"\nTỷ lệ hỏng cao nhất trong đợt: {worst:.1%} "
          f"(ngưỡng dừng {args.fail_threshold:.0%})")
    gate = worst
    if args.wave:
        print(f"Tỷ lệ hỏng toàn đợt: {wave_rate:.1%} "
              f"({len(wave_missing)}/{len(wave_ids)} bài chưa có bản ghi "
              f"ở bất kỳ lô nào)")
        gate = wave_rate
    print("=" * 84)
    print("Bước tiếp: `l1_ingest.py data/agent_outputs_l1` rồi `agent_ingest.py data/agent_outputs`")
    return 1 if gate > args.fail_threshold else 0


if __name__ == "__main__":
    raise SystemExit(main())
