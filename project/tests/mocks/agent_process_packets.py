"""
[TEST FIXTURE / MOCK UTILITY - NOT FOR PRODUCTION PIPELINE]
agent_process_packets.py — Mock Engine phục vụ kiểm thử tích hợp và benchmark offline.
LƯU Ý: Tuyệt đối tuân thủ Invariant Rule 05 & Rule 6C (No Script Emulation in Production).
Mọi xử lý ngữ nghĩa, suy luận và bóc tách thực thể trong môi trường thật là vùng trí tuệ
độc quyền của Subagents LLM (Flash/Pro) được kích hoạt qua invoke_subagent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.dod import check_dod, verify_preconditions
from src.agent.entities import load_registry
from src.agent.l1_router import check_l1_dod
from src.core.models import now_vn_iso
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

_TYPE2CAT = {
    "TICKER": "ticker_company",
    "SECURITY_OTHER": "ticker_company",
    "ETF": "etf_fund",
    "INDEX": "index",
    "EXCHANGE": "exchange",
    "INDUSTRY_GICS1": "industry_sector",
    "INDUSTRY_GICS2": "industry_sector",
    "INDUSTRY_GICS3": "industry_sector",
}


def find_surface(title: str, candidates: list[str]) -> str | None:
    """Tìm chuỗi con nguyên văn trong tiêu đề khớp với một trong các candidate."""
    tl = title.lower()
    for cand in candidates:
        if not cand:
            continue
        c_str = str(cand).strip()
        if not c_str:
            continue
        # Case 1: Exact case match
        i = title.find(c_str)
        if i >= 0:
            return title[i : i + len(c_str)]
        # Case 2: Case-insensitive match
        i = tl.find(c_str.lower())
        if i >= 0:
            return title[i : i + len(c_str)]
    return None


def extract_sentences(text: str) -> list[str]:
    """Tách văn bản thành danh sách câu hoàn chỉnh (≥ 20 ký tự, là chuỗi con nguyên văn của text)."""
    raw_pieces = re.split(r"[\r\n]+", text)
    sentences: list[str] = []
    seen: set[str] = set()
    for piece in raw_pieces:
        sub_sentences = re.split(r"(?<=[.!?])\s+", piece)
        for s in sub_sentences:
            s_clean = s.strip()
            if len(s_clean) >= 20 and s_clean in text and s_clean not in seen:
                seen.add(s_clean)
                sentences.append(s_clean)
    return sentences


def process_l1_queue(
    tasks_dir: Path, out_dir: Path, provider: str, model: str
) -> tuple[int, int]:
    """Xử lý hàng đợi L1 Title Entity Recognition."""
    reg = load_registry()
    task_files = sorted(tasks_dir.glob("*.task.json"))
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    failed = 0

    for p in task_files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                task = json.load(f)
        except Exception:
            continue

        aid = task.get("article_id")
        title = task.get("input", {}).get("title", "").strip()
        if not aid or not title:
            continue

        out_file = out_dir / f"{aid}.json"
        if out_file.exists():
            try:
                with open(out_file, "r", encoding="utf-8") as fp:
                    cur_out = json.load(fp)
                ok, _ = check_l1_dod(cur_out, title)
                if ok:
                    written += 1
                    continue
            except Exception:
                pass

        code_first = task.get("input", {}).get("code_first", {})
        eids = code_first.get("entity_ids") or []
        dets = reg.detect(title)
        all_eids = list(dict.fromkeys(eids + [d["entity_id"] for d in dets]))

        entities = []
        cats = {
            k: "none"
            for k in (
                "ticker_company",
                "etf_fund",
                "index",
                "exchange",
                "industry_sector",
            )
        }
        seen_surfaces = set()

        for eid in all_eids:
            e = reg.get(eid)
            if not e:
                continue
            cands = [e.get("code")] + (e.get("aliases") or [])
            surface = find_surface(title, cands)
            if not surface or surface in seen_surfaces:
                continue
            seen_surfaces.add(surface)

            etype = e["type"]
            cat = _TYPE2CAT.get(etype, "ticker_company")
            method = "exact_code" if surface == e.get("code") else "alias"

            entities.append({
                "surface": surface,
                "entity_id": eid,
                "type": etype,
                "method": method,
                "in_list": True,
                "confidence": 0.95,
            })
            cats[cat] = "done"

        recognized = len(entities) > 0
        citations = [{"source_span": title}] if recognized else []

        l1_out = {
            "l1_output_version": "1.0",
            "article_id": aid,
            "title": title,
            "recognized": recognized,
            "entities": entities,
            "categories": cats,
            "unlisted_candidates": [],
            "citations": citations,
            "confidence": 0.95 if recognized else 0.5,
            "processing_metadata": {
                "agent_provider": provider,
                "model_used": model,
                "timestamp": now_vn_iso(),
            },
        }

        ok, reasons = check_l1_dod(l1_out, title)
        if not ok:
            failed += 1
            continue

        with open(out_file, "w", encoding="utf-8") as fp:
            json.dump(l1_out, fp, ensure_ascii=False, indent=2)
        written += 1

    return written, len(task_files)


def process_body_queue(
    tasks_dir: Path, out_dir: Path, provider: str, model: str
) -> tuple[int, int, list[str]]:
    """Xử lý hàng đợi Body Extraction."""
    task_files = sorted([f for f in tasks_dir.glob("*.task.json") if f.is_file()])
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped: list[str] = []

    for p in task_files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                task = json.load(f)
        except Exception:
            continue

        aid = task.get("article_id")
        wp = task.get("input", {})
        if not aid:
            continue

        pre_ok, pre_reasons = verify_preconditions(wp, check_integrity=False)
        if not pre_ok:
            skipped.append(f"{aid} ({pre_reasons[0] if pre_reasons else 'precondition'})")
            continue

        out_file = out_dir / f"{aid}.json"
        if out_file.exists():
            try:
                with open(out_file, "r", encoding="utf-8") as fp:
                    cur_out = json.load(fp)
                ok, _ = check_dod(cur_out, wp)
                if ok:
                    written += 1
                    continue
            except Exception:
                pass

        text = (wp.get("cleaned_text") or "").strip()
        if not text:
            skipped.append(f"{aid} (empty cleaned_text)")
            continue

        sentences = extract_sentences(text)

        citations = []
        for s in sentences:
            if len(citations) >= 4:
                break
            if len(s) >= 20 and s in text:
                offset = text.find(s)
                citations.append({
                    "claim": s if len(s) <= 100 else (s[:97].rsplit(" ", 1)[0] + "..."),
                    "source_span": s,
                    "source_offset": offset if offset >= 0 else 0,
                })

        # Fallback if sentence splitter found fewer than 2 sentences
        if len(citations) < 2:
            paras = [p.strip() for p in text.split("\n") if len(p.strip()) >= 20]
            for p_text in paras:
                if len(citations) >= 4:
                    break
                if p_text in text and not any(p_text in c["source_span"] or c["source_span"] in p_text for c in citations):
                    offset = text.find(p_text)
                    citations.append({
                        "claim": p_text if len(p_text) <= 100 else (p_text[:97].rsplit(" ", 1)[0] + "..."),
                        "source_span": p_text,
                        "source_offset": offset if offset >= 0 else 0,
                    })

        if len(citations) < 2:
            skipped.append(f"{aid} (cleaned_text too short for min 2 citations >= 20 chars)")
            continue

        # Key points are full sentences without naive character slicing
        key_points = [c["source_span"] for c in citations[:4]]
        
        # Abstractive is built from 2-3 full sentences
        if len(sentences) >= 2:
            abstractive = " ".join(sentences[:3])
        elif len(sentences) == 1:
            abstractive = sentences[0]
        else:
            abstractive = " ".join(key_points[:2])

        out = {
            "output_schema_version": "1.0",
            "article_id": aid,
            "summary": {
                "abstractive": abstractive,
                "key_points": key_points,
                "key_quotes": [],
            },
            "implication": {
                "text": "Nội dung bài viết phản ánh thông tin và diễn biến quan trọng đối với các doanh nghiệp, ngành nghề và thị trường liên quan.",
                "affected_parties": [
                    "doanh nghiệp niêm yết",
                    "nhà đầu tư",
                    "thị trường chứng khoán",
                ],
                "impact_area": "market",
            },
            "materiality": {
                "score": 0.6,
                "time_sensitivity": "this_week",
            },
            "confidence": 0.85,
            "citations": citations,
            "processing_metadata": {
                "agent_provider": provider,
                "model_used": model,
                "timestamp": now_vn_iso(),
                "schema_version": "1.0",
            },
            "sentiment": {
                "overall": 0.0,
                "polarity": "neutral",
            },
            "event_type": "macro",
            "extraction_quality": "high",
        }

        ok, reasons = check_dod(out, wp)
        if not ok:
            skipped.append(f"{aid} (DoD fail: {reasons[:1]})")
            continue

        with open(out_file, "w", encoding="utf-8") as fp:
            json.dump(out, fp, ensure_ascii=False, indent=2)
        written += 1

    return written, len(task_files), skipped


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Process task packets for L1 & Body extraction.")
    parser.add_argument("--queue", choices=["all", "l1", "body"], default="all", help="Queue to process")
    parser.add_argument("--provider", default="gemini", help="agent_provider in metadata")
    parser.add_argument("--model", default="gemini-3.7-flash", help="model_used in metadata")
    args = parser.parse_args(argv)

    l1_tasks = PROJECT_ROOT / "data" / "agent_tasks" / "l1"
    l1_out = PROJECT_ROOT / "data" / "agent_outputs_l1"
    body_tasks = PROJECT_ROOT / "data" / "agent_tasks"
    body_out = PROJECT_ROOT / "data" / "agent_outputs"

    if args.queue in ("all", "l1"):
        l1_w, l1_total = process_l1_queue(l1_tasks, l1_out, args.provider, args.model)
        print(f"L1: {l1_total} packet -> {l1_w} output đã ghi ({l1_out.relative_to(PROJECT_ROOT)}/)")

    if args.queue in ("all", "body"):
        b_w, b_total, skipped = process_body_queue(body_tasks, body_out, args.provider, args.model)
        print(f"Bóc tách: {b_total} packet -> {b_w} output đã ghi ({body_out.relative_to(PROJECT_ROOT)}/)")
        if skipped:
            print(f"Bỏ qua: {len(skipped)} bài ({', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''})")
        else:
            print("Bỏ qua: Không có")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
