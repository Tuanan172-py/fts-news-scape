"""Kiểm thử runner OpenRouter theo hợp đồng đầu ra thống nhất (ADR 0017)."""

from __future__ import annotations

import json

from src.agent import openrouter_runner as orr
from src.agent.article_contract import SAMPLING

PARAS = ["VN-Index tăng hơn 15 điểm trong phiên.", "Dòng tiền lan tỏa sang nhóm bluechip."]
GOOD = {"i": 0, "e": [["VN-Index", "IDX"]], "s": "Chỉ số tăng mạnh.",
        "k": ["Chỉ số tăng điểm", "Dòng tiền lan rộng"],
        "im": "Dòng tiền lan tỏa báo hiệu xu hướng tích cực cho thị trường.",
        "sn": "pos", "ts": "today", "c": [0, 1]}


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, content):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}], "usage": {"total_tokens": 5}}


def _run(tmp_path, monkeypatch, reply):
    task = tmp_path / "article_W_01.task.json"
    packet_text = json.dumps({"d": "2026-10-05", "n": 1,
                              "a": [{"i": 0, "t": "Thị trường tăng", "p": PARAS}]}, ensure_ascii=False)
    task.write_text(packet_text, encoding="utf-8")
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent["payload"] = json
        return _Resp(reply)

    monkeypatch.setattr(orr.requests, "post", fake_post)
    runner = orr.OpenRouterRunner(api_key="k")
    res = runner.run_batch("article_W_01", task, tmp_path / "out", force=True)
    return res, sent["payload"], packet_text


def test_tin_nhan_la_nguyen_van_packet_va_tham_so_chuan(tmp_path, monkeypatch):
    res, payload, packet_text = _run(tmp_path, monkeypatch, json.dumps([GOOD]))
    assert payload["messages"][1]["content"] == packet_text
    assert payload["temperature"] == SAMPLING["temperature"] and payload["seed"] == SAMPLING["seed"]
    assert res.status == "OK"
    meta = json.loads((tmp_path / "out" / "article_W_01.meta.json").read_text(encoding="utf-8"))
    assert meta["contract_version"] == "article-compact-v2"
    assert meta["sampling"]["max_tokens"] == orr.DEFAULT_MAX_TOKENS and len(meta["prefix_sha256"]) == 64


def test_ban_ghi_sai_khong_bi_sua_ngam(tmp_path, monkeypatch):
    bad = {**GOOD, "im": "Ngắn", "sn": "positive"}
    res, _, _ = _run(tmp_path, monkeypatch, json.dumps([bad]))
    assert res.status == "FATAL" and "short:im" in res.error_message
