"""Golden snapshots of Article Lane artifacts that module moves must not change (ADR-0027)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import pytest

from src.article_lane import expand as article_expand
from src.article_lane import pack as article_pack
from src.ops.wave import article_run
from src.agent.catalog.entities import load_registry
from src.agent.catalog.intent_resolve import IntentResolver, ResolveReport
from src.core import paths

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"

ITEMS = [
    {"i": 0, "t": "Hòa Phát báo lãi quý 3 tăng 25%",
     "p": ["Tập đoàn Hòa Phát công bố lợi nhuận sau thuế quý 3 đạt 3.200 tỷ đồng, tăng 25% so với cùng kỳ.",
           "Sản lượng thép cuộn cán nóng HRC tăng 32%, biên lợi nhuận gộp mở rộng lên 14,1%."]},
    {"i": 1, "t": "VNDirect công bố báo cáo quản trị",
     "p": ["Công ty chứng khoán VNDirect công bố báo cáo quản trị sáu tháng đầu năm theo quy định."]},
]
MAPPING = {"batch_id": "G1", "index": {"0": "art-a", "1": "art-b"}}
MODEL_OUT = json.dumps([
    {"i": 0, "e": [["Hòa Phát", "COM"], ["HPG", "TIC"]], "s": "Hòa Phát báo lãi quý 3 tăng 25% nhờ sản lượng thép.",
     "k": ["Lợi nhuận tăng 25%", "Biên gộp mở rộng"],
     "im": "Kết quả vượt kỳ vọng củng cố định giá cổ phiếu thép trong ngắn hạn tới quý sau.",
     "sn": "pos", "ts": "today", "c": [0, 1]},
    {"i": 1, "e": [["VNDirect", "COM"]], "s": "VNDirect công bố báo cáo quản trị định kỳ.",
     "k": ["Báo cáo quản trị định kỳ", "Không có số liệu mới"],
     "im": "Thông tin định kỳ, ít tác động tới giá cổ phiếu ngành chứng khoán trong tuần.",
     "sn": "neu", "ts": "arch", "c": [0]},
], ensure_ascii=False)


def _normalize(text: str) -> str:
    """Replace machine- and time-dependent parts of a snapshot.

    Args:
        text: Raw artifact text.

    Returns:
        Text with the data root, ISO timestamps and today's date masked.
    """
    root = str(paths.data_root())
    for variant in (root, root.replace("\\", "/"), json.dumps(root)[1:-1]):
        text = text.replace(variant, "<DATA_ROOT>")
    text = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)?", "<TS>", text)
    return text.replace(datetime.now().strftime("%Y-%m-%d"), "<DATE>")


def _assert_golden(name: str, actual: str) -> None:
    """Compare an artifact with its stored snapshot, or write it in update mode.

    Args:
        name: Snapshot file name under the golden directory.
        actual: Artifact text.
    """
    path = GOLDEN_DIR / name
    actual = _normalize(actual)
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"missing golden {name}; run with UPDATE_GOLDEN=1 once")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert actual == path.read_text(encoding="utf-8"), f"golden {name} changed"


def test_packet_and_map_are_unchanged(tmp_path):
    packet_path, map_path, budget = article_pack.write_packet("G1", ITEMS, MAPPING, tmp_path)
    _assert_golden("packet.task.json", packet_path.read_text(encoding="utf-8"))
    _assert_golden("packet.map.json", map_path.read_text(encoding="utf-8"))
    _assert_golden("packet.budget.json", json.dumps(budget, ensure_ascii=False, indent=1, sort_keys=True))


def test_conductor_program_is_unchanged():
    manifest = {"wave": "G", "articles": 3, "batches": [
        {"batch_id": "G1", "path": "G1.task.json", "n": 2, "windows": [[1, 40]]},
        {"batch_id": "G2", "path": "G2.task.json", "n": 1, "windows": [[1, 20], [21, 30]]}]}
    _assert_golden("conductor.one.ts", article_run.conductor_program({**manifest, "batches": manifest["batches"][:1]},
                                                                     concurrency=1))
    _assert_golden("conductor.two.ts", article_run.conductor_program(manifest, concurrency=2))


def test_expand_outputs_are_unchanged(tmp_path, monkeypatch):
    for name in ("L1_OUT_DIR", "GOLD_OUT_DIR", "MENTIONS_DIR", "IN_DIR"):
        monkeypatch.setattr(article_expand, name, tmp_path / name)
    reg = load_registry()
    packet = {"d": "2026-10-22", "n": len(ITEMS), "a": ITEMS}
    stats = article_expand.process_batch("G1", MODEL_OUT, packet, MAPPING, IntentResolver(reg), reg,
                                         ResolveReport(), default_provenance=("agy", "golden-model"))
    _assert_golden("expand.stats.json", json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
    for name in ("L1_OUT_DIR", "GOLD_OUT_DIR", "MENTIONS_DIR"):
        for f in sorted((tmp_path / name).glob("*.json")):
            _assert_golden(f"expand.{name.lower()}.{f.name}", f.read_text(encoding="utf-8"))
