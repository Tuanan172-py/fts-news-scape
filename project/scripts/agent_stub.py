"""
agent_stub.py — AGENT GIẢ LẬP TẤT ĐỊNH (KHÔNG LLM) để chạy end-to-end khi chưa tích hợp LLM.

Đây là "stand-in" cho bước agent: đọc task-packet → sinh output hợp lệ theo schema (đủ DoD)
BẰNG QUY TẮC (không phân tích ngữ nghĩa). Dùng để nghiệm thu luồng input→output; KHÔNG phải
phân tích thật. Khi có LLM, thay script này bằng adapter gọi model (xem docs/design/13 §14.4).

Usage:
    python scripts/agent_stub.py --queue l1   --out data/agent_outputs_l1
    python scripts/agent_stub.py --queue main --out data/agent_outputs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.entities import load_registry           # noqa: E402
from src.core.models import now_vn_iso                  # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402

force_utf8_stdio()

_TYPE2CAT = {
    "TICKER": "ticker_company", "SECURITY_OTHER": "ticker_company",
    "ETF": "etf_fund", "INDEX": "index", "EXCHANGE": "exchange",
}


def _find_surface(title: str, candidates: list[str]) -> str | None:
    """Trả CHUỖI CON nguyên văn của title khớp 1 candidate (case-insensitive)."""
    tl = title.lower()
    for cand in candidates:
        if not cand:
            continue
        i = tl.find(str(cand).lower())
        if i >= 0:
            return title[i:i + len(str(cand))]
    return None


def _cat_of(entity_type: str) -> str:
    if entity_type in _TYPE2CAT:
        return _TYPE2CAT[entity_type]
    if entity_type.startswith(("IND_", "INDUSTRY", "SECTOR")):
        return "industry_sector"
    return "ticker_company"


def stub_l1(packet: dict, reg) -> dict:
    title = packet["input"]["title"]
    eids = packet["input"].get("code_first", {}).get("entity_ids") or []
    entities, cats = [], {k: "none" for k in
                         ("ticker_company", "etf_fund", "index", "exchange", "industry_sector")}
    for eid in eids:
        e = reg.get(eid)
        if not e:
            continue
        surface = _find_surface(title, [e.get("code")] + (e.get("aliases") or []))
        if not surface:
            continue
        entities.append({"surface": surface, "entity_id": eid, "type": e["type"],
                         "method": "exact_code" if surface == e.get("code") else "alias",
                         "in_list": True, "confidence": 0.85})
        cats[_cat_of(e["type"])] = "done"
    recognized = bool(entities)
    return {
        "l1_output_version": "1.0", "article_id": packet["article_id"], "title": title,
        "recognized": recognized, "entities": entities, "categories": cats,
        "citations": [{"source_span": title}] if recognized else [],
        "confidence": 0.85 if recognized else 0.6,
        "processing_metadata": {"agent_provider": "stub", "model_used": "rule-based",
                                "timestamp": now_vn_iso()},
    }


def stub_agent(packet: dict) -> dict:
    inp = packet.get("input") or {}
    text = (inp.get("cleaned_text") or packet.get("cleaned_text") or "").strip()
    s1, s2 = text[:80].strip(), text[80:180].strip()
    return {
        "output_schema_version": "1.0", "article_id": packet["article_id"],
        "summary": {"abstractive": (text[:200] or "N/A"),
                    "key_points": [s1[:60]] if s1 else ["N/A"]},
        "implication": {"text": "Bản tóm tắt tự động (stub) — chưa phân tích ngữ nghĩa.",
                        "affected_parties": ["thị trường"], "impact_area": "market"},
        "materiality": {"score": 0.5, "time_sensitivity": "this_week"},
        "confidence": 0.7, "event_type": "other",
        "sentiment": {"overall": 0.0, "polarity": "neutral"},
        "citations": [{"claim": "trích 1", "source_span": s1, "source_offset": 0},
                      {"claim": "trích 2", "source_span": s2, "source_offset": 80}],
        "extraction_quality": "medium",
        "processing_metadata": {"agent_provider": "stub", "model_used": "rule-based",
                                "timestamp": now_vn_iso()},
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", choices=["l1", "main"], required=True)
    ap.add_argument("--tasks", help="thư mục packet (mặc định theo queue)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    tasks_dir = Path(args.tasks or ("data/agent_tasks/l1" if args.queue == "l1" else "data/agent_tasks"))
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    reg = load_registry() if args.queue == "l1" else None

    n = skip = 0
    for p in sorted(tasks_dir.glob("*.json")):
        try:
            packet = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            skip += 1; continue
        out = stub_l1(packet, reg) if args.queue == "l1" else stub_agent(packet)
        if args.queue == "main" and len((out["citations"][1]["source_span"])) < 20:
            skip += 1; continue          # bài quá ngắn không đủ grounding → bỏ
        (out_dir / f"{packet['article_id']}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    print(f"stub {args.queue}: wrote={n} skipped={skip} → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
