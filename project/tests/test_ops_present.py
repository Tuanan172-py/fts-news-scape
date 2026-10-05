"""Kiểm thử định dạng dùng chung (S-03): Python, nhãn và khối JavaScript của Phòng điều khiển."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from src.ops import breakers as br
from src.ops import present
from src.ops.present import (alert_card, clip_lines, fmt_date, fmt_datetime, fmt_duration,
                             fmt_int, fmt_pct, fmt_time, label, success_rate)
from src.ops.store import ACTIVE_WAVE_STATUSES
from src.ops.supervisor import CaptureSupervisor  # noqa: F401  (đảm bảo mô-đun nạp được)

HTML = Path(__file__).resolve().parents[1] / "src" / "ops" / "web" / "control_room.html"


@pytest.mark.parametrize("value,expected", [
    (None, "–"), (0, "0"), (7, "7"), (999, "999"), (1000, "1.000"), (1234, "1.234"),
    (1234567, "1.234.567"), (2.5, "3"), (3.5, "4"), (204062, "204.062"),
])
def test_fmt_int_vi_style_and_round_half_up(value, expected):
    assert fmt_int(value) == expected


@pytest.mark.parametrize("ratio,expected", [
    (None, "–"), (0, "0%"), (0.125, "13%"), (0.56, "56%"), (0.5, "50%"), (1, "100%"),
])
def test_fmt_pct(ratio, expected):
    assert fmt_pct(ratio) == expected


@pytest.mark.parametrize("seconds,expected", [
    (None, "–"), (0.0005, "1 ms"), (0.066, "66 ms"), (0.5, "500 ms"), (0.9996, "1,0 s"),
    (1, "1,0 s"), (5.43, "5,4 s"), (9.96, "10 s"), (10, "10 s"), (54, "54 s"),
    (59.7, "1 ph 0 s"), (60, "1 ph 0 s"), (114, "1 ph 54 s"), (3725, "62 ph 5 s"),
])
def test_fmt_duration_edges(seconds, expected):
    assert fmt_duration(seconds) == expected


def test_fmt_datetime_date_time():
    iso = "2026-10-01T14:34:45+07:00"
    assert fmt_datetime(iso) == "01/10 14:34" and fmt_time(iso) == "14:34"
    assert fmt_date(iso) == "01/10/2026" and fmt_date("2026-10-01") == "01/10/2026"
    assert fmt_datetime(None) == fmt_time("") == fmt_date(None) == "–"
    assert fmt_datetime("không phải ngày") == fmt_time("không phải ngày") == "không phải ngày"
    assert fmt_datetime("2026-10-01") == "01/10" and fmt_time("2026-10-01") == "–"


def test_success_rate_is_one_definition():
    assert success_rate(0, 0) is None
    assert success_rate(3, 1) == 0.75
    assert success_rate(2, 0, 2) == 0.5          # lô một phần có trong mẫu số, không là thành công
    assert success_rate(0, 0, 1) == 0.0


def test_alert_card_has_four_lines_and_no_emoji():
    t = alert_card("critical", "agy mất phiên đăng nhập", "đợt mới không chạy được",
                   "đăng nhập lại agy rồi bấm Reset", "http://127.0.0.1:8787/#incidents")
    lines = t.split("\n")
    assert len(lines) == 4 and lines[0].startswith("[KHẨN]")
    assert lines[1].startswith("Ảnh hưởng:") and lines[2].startswith("Việc cần làm:")
    assert lines[3].startswith("Xem:")
    assert len(alert_card("warn", "a", "b", "c").split("\n")) == 3


def test_clip_lines_cuts_on_line_boundary():
    text = "\n".join(f"dòng {i:03d} " + "x" * 60 for i in range(100))
    out = clip_lines(text, 500)
    assert len(out) <= 500 and out.splitlines()[-1].startswith("... còn")
    assert all(ln.startswith("dòng") or ln.startswith("...") for ln in out.splitlines())
    assert clip_lines("ngắn", 500) == "ngắn"


def test_label_fallback():
    assert label(present.WAVE_STATUS, "DONE") == "Xong"
    assert label(present.WAVE_STATUS, "LẠ") == "LẠ" and label(present.WAVE_STATUS, None) == "–"


# ── mọi trạng thái trong mã đều có nhãn ──────────────────────────────────────
def test_every_status_used_in_code_has_a_label():
    waves = set(ACTIVE_WAVE_STATUSES) | {"DONE", "FAILED", "PARKED", "CANCELLED"}
    assert waves <= set(present.WAVE_STATUS)
    spans = {"ok", "running", "fail", "timeout", "partial", "skipped", "parked", "cancelled",
             "interrupted"}
    assert spans <= set(present.SPAN_STATUS)
    assert {"CLOSED", "OPEN", "HALF_OPEN"} <= set(present.BREAKER_STATE)
    assert {br.OK, br.TIMEOUT, br.NETWORK, br.QUOTA, br.AUTH, br.EMPTY, br.FATAL} \
        <= set(present.FAILURE_CLASS)
    assert {"ok", "run", "fail", "idle", "draft"} <= set(present.NODE_STATE)
    assert {"child", "external", "backoff", "gave_up", "disabled"} <= set(present.CAPTURE_MODE)
    assert {"critical", "error", "warn", "info", "digest"} <= set(present.LEVEL_LABEL)
    assert {"open", "story_opened", "deferred", "rejected"} <= set(present.PROPOSAL_STATUS)
    assert {"workflow", "step", "script", "agent", "gate"} <= set(present.SPAN_KIND)


def test_no_label_contains_emoji():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿⏸⏹▫◐]")
    for table in present.LABELS.values():
        for v in table.values():
            assert not emoji.search(v), v


# ── JavaScript trong trang cho đúng cùng kết quả với Python ───────────────────
@pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để kiểm khối JavaScript")
def test_page_formatters_match_python_exactly():
    html = HTML.read_text(encoding="utf-8")
    block = html.split("// FMT:BEGIN", 1)[1].split("// FMT:END", 1)[0].partition("\n")[2]
    ints = [None, 0, 7, 999, 1000, 1234, 1234567, 2.5, 3.5, 204062]
    pcts = [None, 0, 0.125, 0.56, 0.5, 1]
    durs = [None, 0.0005, 0.066, 0.5, 0.9996, 1, 5.43, 9.96, 10, 54, 59.7, 60, 114, 3725]
    isos = [None, "", "2026-10-01T14:34:45+07:00", "2026-10-01", "2026-10-01T14:34",
            "không phải ngày"]
    script = block + """
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
console.log(JSON.stringify({
  int: cases.ints.map(fmtInt), pct: cases.pcts.map(fmtPct), dur: cases.durs.map(fmtDuration),
  dt: cases.isos.map(fmtDateTime), time: cases.isos.map(fmtTime), date: cases.isos.map(fmtDate)}));
"""
    res = subprocess.run(["node", "-e", script], input=json.dumps(
        {"ints": ints, "pcts": pcts, "durs": durs, "isos": isos}), capture_output=True,
        text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    js = json.loads(res.stdout)
    assert js["int"] == [fmt_int(v) for v in ints]
    assert js["pct"] == [fmt_pct(v) for v in pcts]
    assert js["dur"] == [fmt_duration(v) for v in durs]
    assert js["dt"] == [fmt_datetime(v) for v in isos]
    assert js["time"] == [fmt_time(v) for v in isos]
    assert js["date"] == [fmt_date(v) for v in isos]


def test_labels_endpoint_serves_the_same_tables(tmp_path):
    import http.client

    from src.ops.breakers import Breakers
    from src.ops.config import load_config, resolve_paths
    from src.ops.control_room import ControlRoom
    from src.ops.store import OpsStore

    cfg = load_config()
    paths = resolve_paths(tmp_path / "data")
    store = OpsStore(paths.ops_db)
    cr = ControlRoom(store, cfg, paths, Breakers(store, cfg["breaker"]), port=0)
    assert cr.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", cr.port, timeout=10)
        conn.request("GET", "/api/labels")
        body = json.loads(conn.getresponse().read().decode("utf-8"))
    finally:
        cr.stop()
    assert body == present.LABELS and body["span_status"]["ok"] == "Xong"
