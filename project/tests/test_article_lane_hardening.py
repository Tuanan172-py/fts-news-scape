"""Kiểm các chốt chặn được thêm sau đợt W365: nạp hỏng phải ồn ào, radar chỉ chỉ Article Lane."""
from __future__ import annotations

import argparse
import json
import sqlite3
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest


# --------------------------------------------------------------------------
# Chương trình điều phối: đọc packet
# --------------------------------------------------------------------------
def _run_program(program: str, read_result: str) -> dict:
    """Chạy chương trình điều phối trên Node với bộ công cụ giả.

    Args:
        program: Mã nguồn chương trình do `conductor_program` sinh.
        read_result: Biểu thức JavaScript cho giá trị mà `tools.read` trả về.

    Returns:
        Kết quả chương trình kèm số lượt gọi agent và nội dung prompt đã gửi.
    """
    harness = f"""
const calls = {{ agent: 0, prompts: [] }};
const tools = {{
  read: async (_a) => ({read_result}),
  agent_article: async (a) => {{ calls.agent++; calls.prompts.push(a.prompt);
                                 return {{ output: [{{ type: "text", text: "[]" }}] }}; }},
  write: async (_a) => ({{}}),
}};
async function __main() {{
{program}
}}
__main().then(r => console.log(JSON.stringify({{ r, calls }})));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as f:
        f.write(harness)
        path = f.name
    try:
        res = subprocess.run(["node", path], capture_output=True, text=True,
                             encoding="utf-8")
    except FileNotFoundError:
        pytest.skip("không có Node trên máy này")
    finally:
        Path(path).unlink(missing_ok=True)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def _manifest(n_batches: int) -> dict:
    """Dựng mô tả đợt tối giản gồm `n_batches` lô một bài."""
    return {"wave": "T", "articles": n_batches, "batches": [
        {"batch_id": f"b{i}", "path": f"p{i}.json", "n": 1, "windows": [[1, 10]]}
        for i in range(1, n_batches + 1)]}


def test_doc_packet_dang_doi_tuong_lines_cua_cong_cu_doc():
    """Công cụ đọc trả {lines:[{number,text}]}; đợt W365 chết vì template chỉ hiểu chuỗi."""
    from scripts.article_run import conductor_program

    out = _run_program(conductor_program(_manifest(1), concurrency=1),
                       '{ path: "p", offset: 1, lines: [{ number: 1, text: "{\\"a\\":1}" }],'
                       ' totalLines: 1 }')
    assert out["r"]["failed"] == []
    assert out["calls"]["prompts"] == ['{"a":1}\n']


def test_doc_packet_hong_thi_dung_truoc_khi_goi_mo_hinh():
    """Đọc hỏng phải dừng khi chưa tiêu token nào, kể cả lượt hâm cache."""
    from scripts.article_run import conductor_program

    out = _run_program(conductor_program(_manifest(2), concurrency=2), "{ weird: 1 }")
    assert out["calls"]["agent"] == 0, "không được gọi mô hình, kể cả lượt hâm"
    assert out["r"]["stopped"]
    why = out["r"]["failed"][0]["why"]
    assert "object" in why and "weird" in why, "phải nói rõ công cụ đọc trả về kiểu gì"


# --------------------------------------------------------------------------
# Nửa hoàn tất
# --------------------------------------------------------------------------
def _finish_args(**kw) -> argparse.Namespace:
    """Dựng tham số của nửa hoàn tất, cho phép ghi đè từng khoá."""
    base = {"wave": "W", "only": None, "window_min": 60, "min_coverage": 0.9}
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def finish_env(tmp_path, monkeypatch):
    """Dựng môi trường nửa hoàn tất với lệnh con và DB giả."""
    from scripts import article_run
    from src.db.preflight import WriteProbe

    for attr in ("TASK_DIR", "OUT_DIR", "L1_OUT_DIR", "GOLD_OUT_DIR"):
        monkeypatch.setattr(article_run, attr, tmp_path)
    (tmp_path / "article_W_01.output.json").write_text("[]", encoding="utf-8")
    (tmp_path / "article_OLD_01.output.json").write_text("[]", encoding="utf-8")
    (tmp_path / "l1_batch_cu.output.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(article_run, "pending_batches", lambda w: (["article_W_01"], []))
    monkeypatch.setattr(article_run, "prefix_hash", lambda: "h")
    monkeypatch.setattr(article_run, "probe_write",
                        lambda: WriteProbe(tmp_path / "db", True, "ghi được"))
    monkeypatch.setattr(article_run, "verify_wave", lambda w, min_coverage: 0)
    calls: list[str] = []
    rcs: dict[str, int] = {}
    argv: dict[str, list[str]] = {}

    def fake_run(cmd, *, cwd=None, check=True):
        name = Path(cmd[1]).name
        calls.append(name)
        argv[name] = [Path(c).name for c in cmd[2:]]
        return rcs.get(name, 0)

    monkeypatch.setattr(article_run, "run", fake_run)
    article_run._argv = argv
    return article_run, calls, rcs


def test_bung_ban_ghi_hong_thi_lenh_chay_lai_bo_qua_buoc_hong(finish_env, capsys):
    """Khung ❌ ở bước bung phải bỏ qua chính bước ấy, không lặp lại nó.

    Bung bản ghi đã ghi kết quả ra đĩa trước khi trả mã, và tỷ lệ hỏng là thuộc tính
    của đầu ra mô hình nên chạy lại cho ra đúng con số cũ. In `--finish` trần là một
    vòng lặp vô hạn theo cấu trúc: người vận hành chạy lại, gặp đúng khung này, và
    không có lối ra nào ngoài tự đoán ra `--only`.
    """
    article_run, calls, rcs = finish_env
    rcs["article_expand.py"] = 1

    assert article_run.cmd_finish(_finish_args()) == 1
    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out
    assert "--only ingest,verify,ledger,handoff" in out, "phải bỏ qua bước vừa hỏng"
    assert "l1_ingest.py" not in calls, "không nạp khi bung còn hỏng"


def test_nap_hong_thi_dot_khong_duoc_bao_hoan_tat(finish_env, capsys):
    """Đợt W365 in HOÀN TẤT và thoát 0 dù hai lệnh nạp chết; nay phải thoát 1."""
    article_run, calls, rcs = finish_env
    rcs["l1_ingest.py"] = 1

    assert article_run.cmd_finish(_finish_args()) == 1
    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out
    assert "✅  ĐỢT" not in out
    assert "token_ledger.py" not in calls, "không đi tiếp sau khi nạp hỏng"
    assert "--only ingest" in out, "phải in đúng lệnh chạy lại bước hỏng"


def test_db_khong_ghi_duoc_thi_dung_truoc_khi_nap(finish_env, monkeypatch, capsys):
    """Lỗi quyền ghi phải lộ ra trước bước nạp, kèm nguyên nhân thật."""
    from src.db.preflight import WriteProbe

    article_run, calls, _ = finish_env
    monkeypatch.setattr(article_run, "probe_write", lambda: WriteProbe(
        Path("C:/ngoai/kho/monocle.db"), False, "attempt to write a readonly database"))

    assert article_run.cmd_finish(_finish_args()) == 1
    assert not any(c.endswith("_ingest.py") for c in calls)
    out = capsys.readouterr().out
    assert "danger-full-access" in out, "phải chỉ đúng cơ chế cấp quyền thật"
    assert "writable roots" not in out, "writable roots là lối cấu hình không tồn tại"


def test_do_phu_duoi_nguong_thi_dot_that_bai(finish_env, monkeypatch, capsys):
    """Nạp chạy xong nhưng thiếu bài của đợt vẫn là thất bại, không phải HOÀN TẤT."""
    article_run, calls, _ = finish_env
    monkeypatch.setattr(article_run, "verify_wave", lambda w, min_coverage: 1)

    assert article_run.cmd_finish(_finish_args()) == 1
    assert "token_ledger.py" in calls, "sổ cái vẫn ghi để không mất số đo token"
    assert "CHƯA HOÀN TẤT" in capsys.readouterr().out


def test_only_chi_chay_dung_buoc_da_chon(finish_env):
    """`--only ingest` không bung lại bản ghi và không ghi thêm dòng sổ cái."""
    article_run, calls, _ = finish_env

    assert article_run.cmd_finish(_finish_args(only="ingest")) == 0
    assert calls == ["l1_ingest.py", "agent_ingest.py"]


def test_chi_nap_tep_cua_dung_dot(finish_env):
    """Tệp của đợt khác và tệp lane cũ trong cùng thư mục không được nạp lại."""
    article_run, _calls, _ = finish_env

    assert article_run.cmd_finish(_finish_args(only="expand,ingest")) == 0
    assert article_run._argv["l1_ingest.py"] == ["article_W_01.output.json"]
    assert article_run._argv["agent_ingest.py"] == ["article_W_01.output.json"]
    assert article_run._argv["article_expand.py"] == ["--wave", "W"]


def test_ten_buoc_sai_bi_tu_choi():
    """Tên bước gõ sai phải bị từ chối, còn thứ tự bước luôn theo vòng đời."""
    from scripts.article_run import parse_steps

    with pytest.raises(SystemExit):
        parse_steps("ingest,nap")
    assert parse_steps("verify,ingest") == ["ingest", "verify"]


def test_hau_kiem_dem_theo_tap_bai_cua_dot(tmp_path, monkeypatch):
    """Hậu kiểm đếm đúng bài của đợt, không dùng số cộng dồn của cả thư mục."""
    from scripts import article_run

    monkeypatch.setattr(article_run, "TASK_DIR", tmp_path)
    (tmp_path / "article_W_01.map.json").write_text(
        json.dumps({"index": {str(i): f"id{i}" for i in range(10)}}), encoding="utf-8")
    db = tmp_path / "m.db"
    conn = sqlite3.connect(db)
    for table in ("l1_outputs", "agent_outputs"):
        conn.execute(f"CREATE TABLE {table} (article_id TEXT, dod_pass INTEGER)")
    conn.executemany("INSERT INTO agent_outputs VALUES (?, 1)", [(f"id{i}",) for i in range(10)])
    conn.executemany("INSERT INTO l1_outputs VALUES (?, 1)", [(f"id{i}",) for i in range(8)])
    conn.execute("INSERT INTO l1_outputs VALUES ('id_dot_khac', 1)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(article_run, "resolve_db_path", lambda: db)

    assert article_run.verify_wave("W", min_coverage=0.9) == 1, "8/10 dưới ngưỡng 90%"
    assert article_run.verify_wave("W", min_coverage=0.8) == 0


def test_va_lai_khong_dong_goi_bai_da_co_trong_lo_va(tmp_path, monkeypatch):
    """Chạy lại `--repair` sau một lần vá thành công không được đẻ lô vá thứ hai."""
    from scripts import article_run

    monkeypatch.setattr(article_run, "TASK_DIR", tmp_path)
    monkeypatch.setattr(article_run, "OUT_DIR", tmp_path)
    packet = {"a": [{"i": i, "t": f"Bài {i}", "p": ["Nội dung."]} for i in range(5)]}
    (tmp_path / "article_W_01.task.json").write_text(json.dumps(packet), encoding="utf-8")
    (tmp_path / "article_W_01.map.json").write_text(
        json.dumps({"index": {str(i): f"id{i}" for i in range(5)}}), encoding="utf-8")
    (tmp_path / "article_W_01.output.json").write_text(
        json.dumps([{"i": i} for i in range(3)]), encoding="utf-8")
    (tmp_path / "article_W_01_r01.task.json").write_text(json.dumps({"a": []}),
                                                        encoding="utf-8")
    (tmp_path / "article_W_01_r01.map.json").write_text(
        json.dumps({"index": {"0": "id3", "1": "id4"}}), encoding="utf-8")
    (tmp_path / "article_W_01_r01.output.json").write_text(
        json.dumps([{"i": 0}, {"i": 1}]), encoding="utf-8")

    assert article_run.cmd_repair(argparse.Namespace(wave="W")) == 0
    assert not (tmp_path / "article_W_01_r02.task.json").exists()


# --------------------------------------------------------------------------
# Thử quyền ghi DB
# --------------------------------------------------------------------------
def test_thu_quyen_ghi_phan_biet_ghi_duoc_va_chi_doc(tmp_path):
    """Tệp chỉ đọc phải trượt phép ghi thử, dù `BEGIN IMMEDIATE` vẫn thành công."""
    from src.db.preflight import probe_write

    db = tmp_path / "m.db"
    sqlite3.connect(db).execute("CREATE TABLE t (x)").connection.close()
    assert probe_write(db).ok

    db.chmod(stat.S_IREAD)
    try:
        ro = probe_write(db)
        assert not ro.ok
    finally:
        db.chmod(stat.S_IREAD | stat.S_IWRITE)

    assert not probe_write(tmp_path / "khong_co.db").ok


def test_goi_y_neu_dung_nguyen_nhan_sandbox_khi_db_ngoai_kho():
    """DB ngoài kho mà không ghi được thì gợi ý phải chỉ thẳng vào sandbox."""
    from src.db.preflight import WriteProbe

    outside = WriteProbe(Path("C:/data/news-scape/monocle.db"), False, "readonly")
    assert outside.outside_workspace
    hint = outside.hint()
    assert "workspace-write" in hint
    assert "danger-full-access" in hint
    assert "writable roots" not in hint, "đừng chỉ cách cấu hình không tồn tại"


# --------------------------------------------------------------------------
# Sổ cái: chỉ tính worker của đợt
# --------------------------------------------------------------------------
def test_chi_tinh_phien_worker_tao_sau_moc_dong_goi(monkeypatch):
    """Phiên điều phối mở từ ba ngày trước không được gộp vào token mỗi bài."""
    from src.telemetry import dsh_usage
    from src.telemetry.dsh_usage import SessionUsage

    since = 1_000.0
    sessions = [
        SessionUsage("session-cha-cu", uncached_input=9_000_000, created_at=10.0),
        SessionUsage("session-cha-moi", uncached_input=500, created_at=1_500.0),
        SessionUsage("uuid-worker-cu", uncached_input=700, created_at=10.0),
        SessionUsage("uuid-worker-1", uncached_input=100, created_at=1_200.0),
        SessionUsage("uuid-worker-2", uncached_input=200, created_at=1_300.0),
    ]
    monkeypatch.setattr(dsh_usage, "iter_sessions", lambda cwd, since: sessions)

    wave = dsh_usage.wave_usage(since, with_reasoning=False, workers_only=True)
    assert [s.session_id for s in wave.sessions] == ["uuid-worker-1", "uuid-worker-2"]
    assert wave.uncached_input == 300


# --------------------------------------------------------------------------
# Radar chỉ chỉ Article Lane
# --------------------------------------------------------------------------
def test_radar_khong_con_khuyen_nghi_lane_cu():
    """Radar từng bảo phía điều phối gọi `l1_entity_matcher`; lệnh ấy dẫn sai lane."""
    src = (Path(__file__).resolve().parents[1] / "scripts" / "pipeline_radar.py").read_text(
        encoding="utf-8")
    for legacy in ("l1_entity_matcher", "gold_financial_analyst", "requeue.py --state",
                   "data/agent_tasks/l1", "Gọi Subagents Flash", "l1_route.py --from-db"):
        assert legacy not in src, legacy


@pytest.mark.parametrize("have,missing,received,l1,gold,expect", [
    (["a1"], ["article_W_02"], 1, 0, 0, "wave_W.conductor.ts"),
    (["article_W_01", "article_W_02"], ["article_W_02_r01"], 9, 0, 0, "wave_W.repair.ts"),
    (["a1", "a2"], [], 9, 0, 0, "--repair"),
    (["a1", "a2"], [], 10, 5, 10, "--finish"),
    (["a1", "a2"], [], 10, 10, 10, ""),
])
def test_radar_chon_dung_lenh_theo_vong_doi_dot(monkeypatch, have, missing, received,
                                                l1, gold, expect):
    """Mỗi trạng thái của đợt phải dẫn tới đúng một lệnh kế tiếp."""
    from scripts import article_run, pipeline_radar

    ids = [f"id{i}" for i in range(10)]
    monkeypatch.setattr(article_run, "pending_batches", lambda w: (have, missing))
    monkeypatch.setattr(article_run, "wave_article_ids", lambda w: ids)
    monkeypatch.setattr(article_run, "wave_received_ids", lambda w: set(ids[:received]))
    monkeypatch.setattr(article_run, "coverage_of", lambda c, i: {
        "l1_ok": set(ids[:l1]), "gold_ok": set(ids[:gold])})

    st = pipeline_radar.wave_state(None, {"wave": "W"})
    if expect:
        assert expect in st["next"]
    else:
        assert st["next"] == "" and st["phase"] == "đã xong"


# --------------------------------------------------------------------------
# Nạp nhận diện cho bài chưa qua định tuyến L1
# --------------------------------------------------------------------------
class _FakeStore:
    """Kho giả ghi lại mọi thao tác trên `l1_tasks` và `l1_outputs`."""

    def __init__(self, article):
        self.article = article
        self.tasks: dict[str, dict] = {}
        self.outputs: list[dict] = []

    def get_l1_task(self, aid):
        return self.tasks.get(aid)

    def get_by_hash(self, aid):
        return self.article if self.article and aid == "aid" else None

    def upsert_l1_task(self, row):
        self.tasks[row["article_id"]] = {**row, "status": "pending"}

    def get_l1_output(self, aid):
        return None

    def insert_l1_output(self, row):
        self.outputs.append(row)

    def set_l1_status(self, aid, status, **kw):
        self.tasks[aid]["status"] = status


def test_nap_nhan_dien_cho_bai_article_lane_chua_co_l1_task(monkeypatch):
    """Bài đi thẳng từ Article Lane không còn bị loại với lý do "no l1_task"."""
    from types import SimpleNamespace

    from src.agent import l1_runner

    seen_titles = []
    monkeypatch.setattr(l1_runner, "check_l1_dod",
                        lambda out, title, reg: (seen_titles.append(title) or True, []))
    store = _FakeStore(SimpleNamespace(title="Tiêu đề gốc", source_domain="cafef.vn"))
    runner = l1_runner.L1Runner(store, registry=object())

    res = runner.ingest_output({"article_id": "aid", "title": "tiêu đề mô hình tự viết"})
    assert res["dod_pass"]
    assert store.tasks["aid"]["route"] == "article_lane"
    assert seen_titles == ["Tiêu đề gốc"], "cổng nghiệm thu đối chiếu tiêu đề nguồn"
    assert len(store.outputs) == 1


def test_bai_khong_ton_tai_van_bi_loai(monkeypatch):
    """Định danh không có trong `articles` vẫn bị loại, không tự sinh dòng rác."""
    from src.agent import l1_runner

    runner = l1_runner.L1Runner(_FakeStore(None), registry=object())
    res = runner.ingest_output({"article_id": "khong_co"})
    assert res == {"ok": False, "article_id": "khong_co", "reason": "no l1_task"}


# --------------------------------------------------------------------------
# Bộ chọn bài: bản code-first không phải là phân tích
# --------------------------------------------------------------------------
def test_bai_chi_co_ban_code_first_van_duoc_chon_de_phan_tich():
    """2.915 bài 10–17/09 kẹt vì bộ chọn bài coi bản tra bảng code-first là đã xong."""
    from scripts.article_pack import load_candidates

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE articles (url_title_hash TEXT, title TEXT, published_at TEXT,
                               source_domain TEXT);
        CREATE TABLE work_items (article_id TEXT, package_path TEXT);
        CREATE TABLE l1_outputs (article_id TEXT, dod_pass INTEGER, l1_source TEXT);
    """)
    for aid in ("chi_code_first", "da_phan_tich", "chua_co_gi"):
        conn.execute("INSERT INTO articles VALUES (?, 't', '2026-09-15T08:00', 'x')", (aid,))
        conn.execute("INSERT INTO work_items VALUES (?, 'p')", (aid,))
    conn.execute("INSERT INTO l1_outputs VALUES ('chi_code_first', 1, 'code_first')")
    conn.execute("INSERT INTO l1_outputs VALUES ('da_phan_tich', 1, 'agent')")

    picked = {r[0] for r in load_candidates(conn, date="2026-09-15", limit=10,
                                            only_pending=True)}
    assert picked == {"chi_code_first", "chua_co_gi"}


def test_chuan_bi_dot_khong_bi_chan_khi_phien_khong_ghi_duoc_db(monkeypatch, capsys):
    """Dưới workspace-write DB luôn không ghi được; chặn ở đây là chặn mọi đợt trên DSH."""
    from types import SimpleNamespace

    from scripts import article_run
    from src.db.preflight import WriteProbe

    monkeypatch.setattr(article_run, "check_prefix", lambda: True)
    monkeypatch.setattr(article_run, "probe_write", lambda: WriteProbe(
        Path("C:/data/news-scape/monocle.db"), False, "attempt to write a readonly database"))
    monkeypatch.setattr(article_run.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=3, stdout="đã tới bước đóng gói",
                                                        stderr=""))
    args = argparse.Namespace(wave="W", batch=100, limit=10, today=False, date=None,
                              concurrency=0)

    assert article_run.cmd_prepare(args) == 3, "phải đi tiếp tới bước đóng gói"
    assert "danger-full-access" in capsys.readouterr().out
