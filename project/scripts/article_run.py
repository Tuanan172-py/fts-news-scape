"""Run a whole processing wave of the article lane with a single command."""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.article_contract import not_code_first_sql_for  # noqa: E402
from src.agent.prefix import prefix_hash              # noqa: E402
from src.core import paths                             # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402
from src.db.preflight import probe_write, resolve_db_path  # noqa: E402
from src.ops import pipeline_spec, trace as tracing      # noqa: E402
from src.core.paths import PROJECT_ROOT  # noqa: E402
from src.db.connect import open_ro  # noqa: E402

force_utf8_stdio()

SCRIPTS = PROJECT_ROOT / "scripts"
TASK_DIR = paths.article_packets_dir()
OUT_DIR = paths.agent_outputs_dir("_article")
L1_OUT_DIR = paths.agent_outputs_dir("_l1")
GOLD_OUT_DIR = paths.agent_outputs_dir()
PYTHON = sys.executable
FINISH_STEPS = pipeline_spec.finish_steps()
# Same threshold as the ten percent failure rate of the expand step.
MIN_COVERAGE = 0.90
LAST_VERIFY: dict = {}


def _span_id(name: str) -> str | None:
    """Build a fixed span ID under the parent span set by the daemon.

    Args:
        name: Span name.

    Returns:
        The span ID, or None for a manual run.
    """
    parent = os.environ.get(tracing.ENV_PARENT)
    return f"{parent}/{name}" if parent else None


def run(cmd: list[str], *, cwd: Path = PROJECT_ROOT, check: bool = True) -> int:
    """Run a child command and print a header so the operator can follow it.

    Args:
        cmd: Command elements.
        cwd: Working directory.
        check: Stop the whole wave when the command returns a non-zero code.

    Returns:
        Exit code of the child command.

    Raises:
        SystemExit: If `check` is set and the child command fails.
    """
    label = " ".join(Path(c).name if c.endswith(".py") else c for c in cmd[1:3])
    print(f"\n▶ {label}")
    script = next((Path(c).name for c in cmd if c.endswith(".py")), label)
    with tracing.span(script, "script", tracing.SCRIPT_ACTORS.get(script),
                      span_id=_span_id(script)) as sp:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", **sp.env()}
        res = subprocess.run(cmd, cwd=str(cwd), env=env)
        sp.set(rc=res.returncode)
        if res.returncode != 0:
            sp.status = "fail"
    if check and res.returncode not in (0,):
        print(f"\n❌ Dừng đợt: lệnh trả mã {res.returncode}. "
              f"Thất bại phải ồn ào, không đi tiếp trong im lặng.")
        raise SystemExit(res.returncode)
    return res.returncode


def check_prefix() -> bool:
    """Check both sides of the prefix before opening a wave.

    Side one: the prefix file on disk still matches the entity catalog. A mismatch
    makes the model lookup table wrong.

    Side two: `persona` in the preset still matches that file. A mismatch misses the
    provider-side cache, because the prefix is no longer byte-identical across
    batches; this is the only side that fails without leaving any trace besides the
    invoice.

    Returns:
        True when both sides match, otherwise False.
    """
    res = subprocess.run([PYTHON, str(SCRIPTS / "build_article_prefix.py"), "--check"],
                         cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    print((res.stdout or "").strip() or (res.stderr or "").strip())
    return res.returncode == 0


def warm_packet() -> str:
    """Build a tiny packet used to write the cache for the static prefix.

    The provider cache matches on the prefix from token 0, so it is written only when
    a real request passes through. The first batch used to carry this: it ran alone and
    the remaining batches were released in parallel afterwards. The cost is time, not
    money: the whole wave waited for a full hundred-article batch only to write ten
    thousand prefix tokens.

    A one-article junk packet writes the same prefix in a few seconds, after which all
    batches run in parallel from the start. The added cost is the junk article record,
    about 900 output tokens, under a thousandth of a dollar.

    Returns:
        Packet content for the cache warm-up, in the exact real packet format.
    """
    return json.dumps({
        "d": datetime.now().strftime("%Y-%m-%d"),
        "n": 1,
        "a": [{"i": 0, "t": "Kiểm tra đường truyền, không phải bài thật",
               "p": ["Đây là mục kiểm tra kỹ thuật, không mang nội dung thị trường "
                     "nào và không cần phân tích sâu."]}],
    }, ensure_ascii=False)


def conductor_program(manifest: dict, *, concurrency: int) -> str:
    """Generate the program the conductor runs in exactly one step.

    A packet larger than the single-read cap is paged through precomputed line
    windows. Those reads live in the same program, so they add no model step, and their
    results stay in the program instead of entering the conductor session context.

    A wave of two or more batches starts with a cache warm-up call (see
    :func:`warm_packet`) before releasing the batches, so every batch, including the
    first, hits the static prefix.

    A one-batch wave is not warmed. No second batch benefits from the written prefix,
    so the warm-up would only move the same token miss to another request and add an
    output record and a wait. Cache warming pays off only when someone reuses it.

    Args:
        manifest: Wave description produced by the packing step.
        concurrency: Maximum number of batches running in parallel.

    Returns:
        Program source code as a string.
    """
    # The program runs in DSH with an arbitrary cwd, so packet paths must be absolute.
    batches = [{"id": b["batch_id"], "path": str(paths.resolve_data_path(b["path"])), "n": b["n"],
                "windows": b["windows"]} for b in manifest["batches"]]
    out_dir = str(OUT_DIR).replace("\\", "\\\\")
    warm_block = "" if len(batches) < 2 else f"""const WARM = {json.dumps(warm_packet(), ensure_ascii=False)};

// Một lượt gọi tí hon đi trước để ghi bộ nhớ đệm cho phần tiền tố tĩnh, rồi MỌI lô
// chạy song song và đều trúng cache. Trước đây lô đầu gánh việc hâm cache, tức cả
// đợt phải chờ trọn một lô trăm bài trước khi có gì khác được chạy.
// Hâm cache là tối ưu, không phải điều kiện chạy: hỏng thì đợt vẫn đi tiếp, chỉ là
// lô đầu tiên trả giá token mới cho phần tiền tố.
try {{
  await tools.agent_article({{ description: "warm {manifest['wave']}", prompt: WARM }});
}} catch (e) {{ /* bỏ qua có chủ ý */ }}

"""

    return f"""// Đợt {manifest['wave']} — {manifest['articles']} bài, {len(batches)} lô.
// Chạy TRỌN chương trình này trong MỘT lệnh run_code. Không tách thành nhiều bước.
const BATCHES = {json.dumps(batches, ensure_ascii=False)};
const OUT = "{out_dir}";
const CONCURRENCY = {concurrency};

// Ghép lại nội dung packet từ các cửa sổ dòng. Công cụ đọc trả về đối tượng
// {{path, offset, lines: [{{number, text}}], totalLines}}. Dạng chuỗi có số dòng đứng
// đầu mỗi dòng vẫn được bóc, để chương trình không vỡ khi runtime đổi định dạng.
// Không bóc được dòng nào thì ném lỗi kèm kiểu dữ liệu nhận được, thay vì trả về
// một packet rỗng không nói lên nguyên nhân.
async function readPacket(b) {{
  let text = "";
  for (const [offset, limit] of b.windows) {{
    const r = await tools.read({{ file_path: b.path, offset, limit }});
    if (Array.isArray(r?.lines)) {{
      for (const l of r.lines) text += (typeof l === "string" ? l : (l?.text ?? "")) + "\\n";
      continue;
    }}
    const body = typeof r === "string" ? r : (r?.content ?? r?.text ?? "");
    let matched = 0;
    for (const line of String(body).split("\\n")) {{
      const m = line.match(/^\\s*(\\d+): ?(.*)$/);
      if (m) {{ text += m[2] + "\\n"; matched++; }}
    }}
    if (!matched) {{
      const keys = r && typeof r === "object" ? Object.keys(r).join(",") : "-";
      throw new Error(`đọc ${{b.id}} tại dòng ${{offset}}: nhận ${{typeof r}} [${{keys}}], không bóc được dòng nào`);
    }}
  }}
  if (!text.trim()) throw new Error(`đọc ${{b.id}}: ghép xong vẫn rỗng`);
  return text;
}}

// Đọc trọn mọi packet TRƯỚC khi gọi mô hình. Đọc hỏng thì dừng cả đợt khi chưa tiêu
// token nào; trước đây lỗi đọc chỉ lộ ra sau khi lượt hâm cache đã chạy.
const PACKETS = {{}};
const readFailed = [];
for (const b of BATCHES) {{
  try {{ PACKETS[b.id] = await readPacket(b); }}
  catch (e) {{ readFailed.push({{ id: b.id, why: String(e?.message ?? e) }}); }}
}}
if (readFailed.length) {{
  return {{ wave: "{manifest['wave']}", batches: 0, failed: readFailed,
           stopped: "đọc packet hỏng, chưa gọi mô hình" }};
}}

async function runBatch(b) {{
  const packet = PACKETS[b.id];
  const res = await tools.agent_article({{
    description: "article " + b.id,
    prompt: packet
  }});
  // Công cụ gọi agent trả về {{kind, runId, output:[{{type:"text", text}}]}}. Ghi thẳng
  // đối tượng ấy ra đĩa thì tệp mang lớp vỏ, và bộ bung bản ghi đọc nhầm lớp vỏ
  // thành một bản ghi rác — đúng thứ đã xảy ra với các tệp _cNN của W1 và W2.
  const parts = Array.isArray(res?.output)
    ? res.output.filter(o => o?.type === "text").map(o => o.text).join("")
    : "";
  const text = typeof res === "string" ? res
             : (parts || res?.text || res?.content || JSON.stringify(res));
  await tools.write({{ file_path: OUT + "\\\\" + b.id + ".output.json", content: text }});
  return {{ id: b.id, ok: true, chars: text.length }};
}}

{warm_block}const done = [];
for (let i = 0; i < BATCHES.length; i += CONCURRENCY) {{
  const slice = BATCHES.slice(i, i + CONCURRENCY);
  // Một lô ném lỗi không được kéo đổ cả `Promise.all`: các lô khác đã ghi xong đầu
  // ra, và người vận hành cần biết đúng lô nào hỏng vì sao.
  done.push(...await Promise.all(slice.map(b => runBatch(b).catch(e => (
    {{ id: b.id, ok: false, why: String(e?.message ?? e).slice(0, 200) }})))));
}}

// Chỉ trả về con số. Nội dung packet và đầu ra của lô KHÔNG được vào ngữ cảnh.
return {{ wave: "{manifest['wave']}", batches: done.length,
         failed: done.filter(d => !d.ok).map(d => ({{ id: d.id, why: d.why }})) }};
"""


def pending_batches(wave: str) -> tuple[list[str], list[str]]:
    """Split the batches of a wave into those with and without output.

    Args:
        wave: Wave ID.

    Returns:
        Pair of lists: IDs of batches that have output and IDs of batches still missing.
    """
    packets = sorted(glob.glob(str(TASK_DIR / f"article_{wave}_*.task.json")))
    ids = [Path(p).name.replace(".task.json", "") for p in packets]
    have = {Path(p).name.replace(".output.json", "")
            for p in glob.glob(str(OUT_DIR / "*.output.json"))}
    return [i for i in ids if i in have], [i for i in ids if i not in have]


def missing_indices(batch_id: str) -> tuple[list[str], dict, dict]:
    """Find articles that were sent but have no record received.

    This replaces defensive batch splitting: instead of guessing an unmeasured cap and
    splitting every batch, send the whole batch and compare the number of records
    received with the number of articles sent. Cost then follows what was actually lost.

    Args:
        batch_id: Batch ID.

    Returns:
        Triple of the missing indices, the packet content, and the mapping table.
    """
    from src.agent.article_contract import parse_and_validate

    packet_path = TASK_DIR / f"{batch_id}.task.json"
    map_path = TASK_DIR / f"{batch_id}.map.json"
    out_path = OUT_DIR / f"{batch_id}.output.json"
    if not (packet_path.exists() and map_path.exists()):
        return [], {}, {}
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    if not out_path.exists():
        return list(mapping.get("index", {}).keys()), packet, mapping
    parsed = parse_and_validate(out_path.read_text(encoding="utf-8"), packet)
    have = {str(i) for i in parsed.records}
    return [i for i in mapping.get("index", {}) if i not in have], packet, mapping


def wave_received_ids(wave: str) -> set[str]:
    """Collect IDs of articles with a valid record in any batch of the wave.

    An article missing from the original batch but present in a repair batch counts as
    received. Looking only at the original batch would make every rerun of `--repair`
    repack the articles that were already patched.

    Args:
        wave: Wave ID.

    Returns:
        Set of article IDs that have a record in the model output.
    """
    from src.agent.article_contract import parse_and_validate

    got: set[str] = set()
    for p in glob.glob(str(TASK_DIR / f"article_{wave}_*.map.json")):
        batch_id = Path(p).name.replace(".map.json", "")
        out_path = OUT_DIR / f"{batch_id}.output.json"
        if not out_path.exists():
            continue
        index = json.loads(Path(p).read_text(encoding="utf-8")).get("index") or {}
        packet_path = TASK_DIR / f"{batch_id}.task.json"
        if not packet_path.exists():
            continue
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        parsed = parse_and_validate(out_path.read_text(encoding="utf-8"), packet)
        got |= {index[str(i)] for i in parsed.records if str(i) in index}
    return got


def cmd_repair(args: argparse.Namespace) -> int:
    """Repack the articles with no record received and generate a catch-up program.

    No database is needed: the article content is already in the original packet, so
    this repair path also spends 0 tokens. Each missing article goes into exactly one
    repair packet per run, even if it is missing from several packet generations. A
    packet built before Silver existed holds a short RSS excerpt, so old citations
    cannot be matched to the new body: those articles are repacked from the full Silver
    (refresh) instead of patched around the old record.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 when there is something to repair or nothing is missing, 2 when no
        output exists yet.
    """
    from scripts.article_pack import fresh_wave_paragraphs, write_packet
    from src.agent.article_contract import MIN_CITATION_CHARS

    def _eligible(paras: list) -> int:
        return sum(1 for p in (paras or []) if len(p or "") >= MIN_CITATION_CHARS)

    packets = sorted(glob.glob(str(TASK_DIR / f"article_{args.wave}_*.task.json")))
    if not packets:
        print(f"Không có packet nào của đợt {args.wave}.")
        return 2

    have, _missing = pending_batches(args.wave)
    if not have:
        print(f"⚠️  Đợt {args.wave}: chưa lô nào có đầu ra, nên không có gì để "
              f"đối chiếu. Chạy chương trình điều phối trước đã.")
        return 2

    repairs: list[dict] = []
    total_missing = 0
    received = wave_received_ids(args.wave)
    # Current article bodies (full Silver) used to repack missing articles and detect
    # stale packets. If unreadable, keep the previous behavior (original packet).
    wave_ids: set[str] = set()
    for packet_path in packets:
        try:
            _mapping = json.loads(Path(packet_path.replace(".task.json", ".map.json"))
                                   .read_text(encoding="utf-8"))
            wave_ids.update(str(v) for v in (_mapping.get("index") or {}).values())
        except (OSError, ValueError):
            continue
    fresh_paras = fresh_wave_paragraphs(wave_ids)
    # Articles that already have passing content in the DB are not rerun even if the
    # packet is stale: their record passed the gate and counts toward wave coverage.
    passing: set[str] = set()
    try:
        _conn = open_ro(resolve_db_path())
        try:
            for _row in _conn.execute(
                    "SELECT article_id, MAX(dod_pass) FROM agent_outputs GROUP BY article_id"):
                if _row[1]:
                    passing.add(_row[0])
        finally:
            _conn.close()
    except Exception:
        passing = set()
    # An article missing across several packet generations (original plus repair
    # batches) is repacked exactly once per run: the earlier packet (older generation,
    # sorted first by name) keeps it and later generations skip it. Without this set, one
    # run emits overlapping repair packets for the same articles (E1), burning duplicate
    # tokens and skewing the expand failure count.
    claimed: set[str] = set()
    for packet_path in packets:
        batch_id = Path(packet_path).name.replace(".task.json", "")
        missing, packet, mapping = missing_indices(batch_id)
        # A refresh packet produces replacement records for the old ones: an article
        # without a record in this packet is repacked even if another packet holds an old record.
        is_refresh = (mapping.get("kind") == "refresh")
        fresh = [i for i in missing
                 if mapping["index"][i] not in claimed
                 and (is_refresh or mapping["index"][i] not in received)]
        if not fresh:
            continue
        for i in fresh:
            claimed.add(mapping["index"][i])
        missing = fresh
        total_missing += len(missing)
        arts = {str(a.get("i")): a for a in (packet.get("a") or [])}
        items: list[dict] = []
        index: dict[str, str] = {}
        tier: dict[str, int] = {}
        reason: dict[str, str] = {}
        for new_i, old_i in enumerate(missing):
            src = arts.get(old_i) or {}
            paras = fresh_paras.get(mapping["index"][old_i]) or src.get("p", [])
            items.append({"i": new_i, "t": src.get("t", ""), "p": paras})
            index[str(new_i)] = mapping["index"][old_i]
            tier[str(new_i)] = (mapping.get("tier") or {}).get(old_i, 2)
            reason[str(new_i)] = (mapping.get("reason") or {}).get(old_i, "")

        seq = 1
        while (TASK_DIR / f"{batch_id}_r{seq:02d}.task.json").exists():
            seq += 1
        rid = f"{batch_id}_r{seq:02d}"
        new_map = {"batch_id": rid, "wave": args.wave,
                   "created_at": datetime.now().isoformat(timespec="seconds"),
                   "index": index, "tier": tier, "reason": reason}
        rpath, _mpath, budget = write_packet(rid, items, new_map, TASK_DIR)
        repairs.append({"batch_id": rid, "path": paths.to_data_relative(rpath), "n": len(items),
                        "windows": budget["windows"], "from": batch_id})

    # Refresh stale packets: articles without passing content in the DB whose current
    # Silver body has clearly more paragraphs than the packet holds (the packet was built
    # before Silver existed and kept only a short RSS excerpt). Old citations cannot be
    # matched to the new body, so patching around the old record only adds failure rounds.
    # Passing articles are left alone to avoid duplicate token spend. Group by original
    # packet; each repair packet holds at most 25 articles to fit the output cap of the
    # free provider.
    stale_by_batch: dict[str, list[tuple[str, dict]]] = {}
    refreshed: set[str] = set()
    for packet_path in packets:
        batch_id = Path(packet_path).name.replace(".task.json", "")
        try:
            packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
            mapping = json.loads(Path(packet_path.replace(".task.json", ".map.json"))
                                 .read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        arts = {str(a.get("i")): a for a in (packet.get("a") or [])}
        for old_i, article_id in (mapping.get("index") or {}).items():
            if article_id in claimed:
                continue
            if article_id in passing or article_id in refreshed:
                continue
            current = fresh_paras.get(article_id)
            if not current or _eligible(current) < 2:
                continue
            src = arts.get(str(old_i)) or {}
            if _eligible(current) <= _eligible(src.get("p", [])):
                continue
            stale_by_batch.setdefault(batch_id, []).append((old_i, src))
            refreshed.add(article_id)
    total_refresh = 0
    for batch_id, stale in sorted(stale_by_batch.items()):
        try:
            origin_map = json.loads((TASK_DIR / f"{batch_id}.map.json")
                                    .read_text(encoding="utf-8"))
        except (OSError, ValueError):
            origin_map = {}
        for chunk_start in range(0, len(stale), 25):
            chunk = stale[chunk_start:chunk_start + 25]
            items, index, tier, reason = [], {}, {}, {}
            for new_i, (old_i, src) in enumerate(chunk):
                items.append({"i": new_i, "t": src.get("t", ""),
                              "p": fresh_paras[(origin_map.get("index") or {}).get(
                                  str(old_i), "")] or src.get("p", [])})
                article_id = (origin_map.get("index") or {}).get(str(old_i), "")
                index[str(new_i)] = article_id
                tier[str(new_i)] = (origin_map.get("tier") or {}).get(str(old_i), 2)
                reason[str(new_i)] = (origin_map.get("reason") or {}).get(str(old_i), "")
                claimed.add(article_id)
            total_refresh += len(items)
            seq = 1
            while (TASK_DIR / f"{batch_id}_r{seq:02d}.task.json").exists():
                seq += 1
            rid = f"{batch_id}_r{seq:02d}"
            new_map = {"batch_id": rid, "wave": args.wave,
                       "created_at": datetime.now().isoformat(timespec="seconds"),
                       "index": index, "tier": tier, "reason": reason,
                       "kind": "refresh"}
            rpath, _mpath, budget = write_packet(rid, items, new_map, TASK_DIR)
            repairs.append({"batch_id": rid, "path": paths.to_data_relative(rpath), "n": len(items),
                            "windows": budget["windows"], "from": batch_id + " (làm mới)"})
    total_missing += total_refresh

    if not repairs:
        print(f"✅  Đợt {args.wave}: không lô nào thiếu bài. Không cần vá.")
        return 0

    print("=" * 84)
    print(f" 🩹  ĐỢT {args.wave} — ĐÓNG GÓI BÙ {total_missing:,} BÀI CÒN THIẾU")
    print("=" * 84)
    for r in repairs:
        print(f"  {r['batch_id']:30} {r['n']:>4} bài  (thiếu từ {r['from']})")

    manifest = {"wave": args.wave, "articles": total_missing, "batches": repairs}
    program = conductor_program(manifest, concurrency=len(repairs))
    prog_path = TASK_DIR / f"wave_{args.wave}.repair.ts"
    prog_path.write_text(program, encoding="utf-8")
    if getattr(args, "runner", "dsh") in ("agy", "openrouter", "opencode"):
        runner_type = getattr(args, "runner", "dsh")
        print()
        print("-" * 84)
        print(f"RUNNER {runner_type.upper()} ĐÃ CHỌN — thực thi tự động gói vá:")
        print("-" * 84)
        if runner_type == "agy":
            from src.agent.agy_runner import AgyRunner
            runner = AgyRunner()
        elif runner_type == "opencode":
            from src.agent.opencode_runner import OpencodeRunner
            runner = OpencodeRunner()
        else:
            from src.agent.openrouter_runner import OpenRouterRunner
            runner = OpenRouterRunner()

        concurrency = min(len(repairs), args.concurrency or 2)
        res = runner.run_wave(manifest, OUT_DIR, concurrency=concurrency)
        print(f"Hoàn tất gói vá: {res['batches_ok']}/{res['batches_total']} lô đạt OK, "
              f"trích xuất {res['items_extracted']} bài, {res['total_tokens']:,} tokens.")
        for r in res.get("results", []):
            status_symbol = "✅" if r["ok"] else "⚠️"
            print(f"  {status_symbol} {r['batch_id']}: {r['status']} ({r['items']} bài) {r['error']}")
        print("=" * 84)
        return 0 if res["batches_ok"] == res["batches_total"] else 1

    print()
    print(f"Chạy TRỌN nội dung tệp sau trong MỘT lệnh run_code:")
    print(f"  {prog_path}")
    print(f"Xong thì quay lại: python scripts/article_run.py --wave {args.wave} --finish")
    print("=" * 84)
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    """Prepare the wave: check the prefix, pack packets, print the conductor program.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 when preparation is done, non-zero when there is no work or the
        prefix is out of date.
    """
    if not check_prefix():
        print("\n❌ Prefix lệch danh mục. Chạy `build_article_prefix.py` rồi cập nhật "
              "persona trong preset trước khi mở đợt, nếu không sẽ vỡ bộ nhớ đệm.")
        return 1

    # The prepare half only reads the DB and writes files in the repository, so it can run
    # under workspace-write. This is an early notice only; the real guard is in `--finish`,
    # before the ingest step. Model output is on disk, so a missing write permission loses
    # no tokens: rerunning `--finish` with suitable permissions is enough.
    probe = probe_write()
    if not probe.ok:
        print(f"\nⓘ  Phiên này không ghi được DB ({probe.reason}). Đợt vẫn mở được; "
              f"bước `--finish` phải chạy với danger-full-access.")

    pack_cmd = [PYTHON, str(SCRIPTS / "article_pack.py"),
                "--wave", args.wave, "--batch", str(args.batch),
                "--limit", str(args.limit), "--json"]
    if args.today:
        pack_cmd.append("--today")
    if args.date:
        pack_cmd += ["--date", args.date]
    if getattr(args, "exclude_file", None):
        pack_cmd += ["--exclude-file", args.exclude_file]

    with tracing.span("article_pack.py", "script", "article-packer",
                      span_id=_span_id("article_pack.py")) as sp:
        res = subprocess.run(pack_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        sp.set(rc=res.returncode)
        if res.returncode == 2:
            sp.status = "skipped"
        elif res.returncode != 0:
            sp.status = "fail"
        else:
            try:
                packed = json.loads(res.stdout.strip().splitlines()[-1])
                sp.set(articles=packed.get("articles"), tier1=packed.get("tier1"),
                       batches=len(packed.get("batches") or []))
            except (ValueError, IndexError):
                pass
    if res.returncode != 0:
        print(res.stdout.strip() or res.stderr.strip())
        return res.returncode
    manifest = json.loads(res.stdout.strip().splitlines()[-1])

    print("=" * 84)
    print(f" 🌊  ĐỢT {manifest['wave']} — ĐÃ CHUẨN BỊ, CHƯA TIÊU TOKEN NÀO")
    print("=" * 84)
    n_batches = len(manifest["batches"])
    print(f"Bài      : {manifest['articles']:,} ({manifest['tier1']:,} tầng ưu tiên)")
    # The key `max_completion_tokens` never existed in the manifest, so this line still
    # prints an output cap of 0 tokens in every wave. Batching follows `--batch` only.
    print(f"Lượt gọi : {n_batches} lô song song, tối đa "
          f"{manifest.get('per_call', '?')} bài mỗi lô (một lệnh run_code)")
    warm_note = (", sau một lượt hâm bộ nhớ đệm tí hon" if n_batches > 1
                 else " (một lô nên không cần hâm bộ nhớ đệm)")
    print(f"Bước     : 1 — cả {n_batches} lượt nằm trong cùng một lệnh run_code"
          f"{warm_note}")
    print(f"Dự toán  : quota {manifest['est_quota_total']:,} token "
          f"(miss {manifest['est_miss_total']:,} · hit {manifest['est_hit_total']:,} · "
          f"out {manifest['est_out_total']:,})")
    pfx_note = ("mọi lô trúng cache" if manifest.get("warmed")
                else "lô duy nhất trả giá token mới")
    print(f"Prefix   : hash {prefix_hash()} · {manifest.get('prefix_tokens', 0):,} "
          f"token tĩnh, {pfx_note}")
    print(f"Manifest : {manifest['manifest']}")

    # Record the wave data date in the manifest. The handoff reads this key to report the
    # right day instead of defaulting to the run date: a catch-up wave for an old day would
    # otherwise always report 0 coverage in the handoff even though verification passed.
    resolved_date = args.date or (datetime.now().strftime("%Y-%m-%d") if args.today else None)
    manifest_path = Path(manifest["manifest"])
    if resolved_date and manifest_path.exists():
        try:
            on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
            on_disk["date"] = resolved_date
            manifest_path.write_text(json.dumps(on_disk, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        except (OSError, ValueError) as exc:
            print(f"   ⚠️  Không ghi được ngày dữ liệu vào manifest: {exc}")

    concurrency = args.concurrency or len(manifest["batches"])
    program = conductor_program(manifest, concurrency=concurrency)
    prog_path = TASK_DIR / f"wave_{args.wave}.conductor.ts"
    prog_path.write_text(program, encoding="utf-8")

    if getattr(args, "runner", "dsh") in ("agy", "openrouter", "opencode"):
        runner_type = getattr(args, "runner", "dsh")
        print()
        print("-" * 84)
        print(f"RUNNER {runner_type.upper()} ĐÃ CHỌN — thực thi tự động:")
        print("-" * 84)
        if args.analyze:
            return cmd_analyze(args)
        print(f"  Để chạy phân tích các lô qua {runner_type}, gõ lệnh:")
        print(f"    python scripts/article_run.py --wave {args.wave} --runner {runner_type} --analyze")
        print()
        print("  Sau khi hoàn tất, nạp CSDL bằng lệnh:")
        print(f"    python scripts/article_run.py --wave {args.wave} --finish")
        print("=" * 84)
        return 0

    print()
    print("-" * 84)
    print("BƯỚC KẾ TIẾP — chạy trong phiên DSH, preset `news-scape-conductor`:")
    print("-" * 84)
    print(f"  Dán trọn nội dung tệp sau vào MỘT lệnh run_code:")
    print(f"    {prog_path}")
    print()
    print("  Sau khi chương trình chạy xong, quay lại đây:")
    print(f"    python scripts/article_run.py --wave {args.wave} --finish")
    print("=" * 84)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Run the cognitive analysis of the wave batches with the agy, openrouter or opencode runner.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 when all batches pass, 1 when a batch fails, 2 when the manifest
        is missing.
    """
    manifest_path = TASK_DIR / f"wave_{args.wave}.json"
    if not manifest_path.exists():
        print(f"❌ Không tìm thấy manifest của đợt: {manifest_path}. Chạy chuẩn bị trước.")
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runner_type = getattr(args, "runner", "dsh")
    if runner_type == "openrouter":
        from src.agent.openrouter_runner import OpenRouterRunner
        runner = OpenRouterRunner()
        title = "OPENROUTER RUNNER (stealth/space-bunny-alpha)"
    elif runner_type == "agy":
        from src.agent.agy_runner import AgyRunner
        runner = AgyRunner()
        title = "AGY RUNNER (gemini-3.8-flash-low)"
    elif runner_type == "opencode":
        from src.agent.opencode_runner import OpencodeRunner
        runner = OpencodeRunner()
        title = "OPENCODE RUNNER (opencode/deepseek-v4.1-flash-free)"
    else:
        print(f"❌ --analyze chỉ chạy với --runner agy, openrouter hoặc opencode, nhận '{runner_type}'. "
              "Runner dsh chạy qua chương trình điều phối wave_<mã>.conductor.ts.")
        return 2

    concurrency = args.concurrency or 2
    print("=" * 84)
    print(f" 🤖  BẮT ĐẦU PHÂN TÍCH {title} (WAVE {args.wave}) — CONCURRENCY {concurrency}")
    print("=" * 84)
    res = runner.run_wave(manifest, OUT_DIR, concurrency=concurrency)
    print(f"Hoàn tất: {res['batches_ok']}/{res['batches_total']} lô đạt OK, "
          f"trích xuất {res['items_extracted']} bài, {res['total_tokens']:,} tokens.")
    for r in res.get("results", []):
        status_symbol = "✅" if r["ok"] else "⚠️"
        print(f"  {status_symbol} {r['batch_id']}: {r['status']} ({r['items']} bài) {r['error']}")
    print("=" * 84)
    return 0 if res["batches_ok"] == res["batches_total"] else 1


def cmd_finish(args: argparse.Namespace) -> int:
    """Finish the wave: expand records, ingest into the database, verify, write the ledger, generate the handoff.

    The completion line is printed only when every write step succeeded and the
    verification reached the threshold. `--only` reruns exactly the failed steps
    instead of the whole chain.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 when finished, 1 when a write step failed or coverage is below the
        threshold, 2 when there is no output to process yet.
    """
    steps = parse_steps(args.only)
    rerun = f"python scripts/article_run.py --wave {args.wave} --finish --only"

    if "expand" in steps:
        have, missing = pending_batches(args.wave)
        if not have:
            print(f"Chưa có đầu ra nào cho đợt {args.wave}. "
                  f"Chạy chương trình điều phối trước, rồi quay lại lệnh này.")
            return 2
        if missing:
            print(f"⚠️  Còn {len(missing)} lô chưa có đầu ra: {', '.join(missing[:5])}"
                  f"{' …' if len(missing) > 5 else ''}")
            print("   Vẫn xử lý phần đã có; chạy lại lệnh này sau khi những lô kia xong.")

    # Anchor cost attribution to the moment the wave was packed. A wider window would
    # merge unrelated DSH sessions open in parallel and inflate the per-article token
    # figure hundredfold.
    manifest_path = TASK_DIR / f"wave_{args.wave}.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    started = manifest.get("created_epoch")
    if not started:
        started = time.time() - args.window_min * 60
        print(f"⚠️  Manifest không có mốc thời gian đóng gói; lùi lại "
              f"{args.window_min} phút. Con số quy kết có thể gộp nhầm phiên khác.")

    # Probe write permission before expand and ingest. A sandbox failure otherwise
    # surfaces only as "attempt to write a readonly database" mid-ingest, which reads like
    # a file-attribute error and sends the fixer in the wrong direction.
    if "ingest" in steps:
        probe = probe_write()
        if not probe.ok:
            fail_banner(args.wave, [f"DB không ghi được: {probe.path} — {probe.reason}",
                                    probe.hint()],
                        f"{rerun} ingest,verify,ledger,handoff")
            return 1

    if "expand" in steps:
        expand_cmd = [PYTHON, str(SCRIPTS / "article_expand.py"), "--wave", args.wave]
        if getattr(args, "runner", "dsh") == "dsh":
            expand_cmd += ["--default-provider", "dsh", "--default-model", "deepseek-flash"]
        expand_rc = run(expand_cmd, check=False)
        if expand_rc != 0:
            # The rerun command must SKIP the step that just failed, not repeat it. Expand
            # wrote its results to disk before returning the code, and the failure rate is a
            # property of the model output, so a rerun yields the same figure. Printing a bare
            # `--finish` here would be a structural infinite loop: the operator reruns, hits this
            # same banner, and has no way out except guessing `--only`.
            why = ("Tỷ lệ hỏng vượt ngưỡng. Xem lại persona của worker rồi chạy lại "
                   "đúng các lô hỏng." if expand_rc == 1
                   else f"Bước bung bản ghi trả mã {expand_rc}.")
            fail_banner(args.wave, [why], f"{rerun} ingest,verify,ledger,handoff")
            return 1

    # Ingest is a write step, not an auxiliary one: on failure stop the wave at once.
    # Ingest only this wave's files. Scanning the whole directory would reload every old
    # file on each finish, including files of the retired L1/Gold lane, and fill the
    # `failed` line of the ingest command with errors unrelated to the wave.
    if "ingest" in steps:
        failed = []
        for script, out_dir in (("l1_ingest.py", L1_OUT_DIR), ("agent_ingest.py", GOLD_OUT_DIR)):
            files = sorted(glob.glob(str(out_dir / f"article_{args.wave}_*.output.json")))
            if not files:
                failed.append(f"không có tệp đầu ra nào của đợt trong {out_dir.name}/ "
                              f"— chạy bước expand trước")
                continue
            rc = run([PYTHON, str(SCRIPTS / script), *files], check=False)
            if rc != 0:
                failed.append(f"{script} trả mã {rc}: có bản ghi bị DoD loại hoặc tệp "
                              f"không đọc được, xem các dòng FAILED phía trên")
        if failed:
            fail_banner(args.wave, failed, f"{rerun} ingest,verify,ledger,handoff")
            return 1

    # The `done/failed` counts of the two ingest commands accumulate over the whole
    # directory, not this wave. Only checking the exact article set in the wave mapping
    # answers whether the wave is fully in the database.
    verify_ok = True
    if "verify" in steps:
        with tracing.span("verify_wave", "gate", "article-expander",
                          span_id=_span_id("verify_wave")) as sp:
            rc_verify = verify_wave(args.wave, min_coverage=args.min_coverage)
            sp.set(rc=rc_verify, min_coverage=args.min_coverage, **LAST_VERIFY)
            if rc_verify != 0:
                sp.status = "fail"
        verify_ok = rc_verify == 0

    soft: list[str] = []
    if "ledger" in steps:
        items = manifest.get("articles", 0)
        ledger_cmd = [PYTHON, str(SCRIPTS / "token_ledger.py"), "append",
                      "--wave", args.wave, "--items", str(items),
                      "--since", str(started), "--workers-only"]
        if manifest.get("est_miss_total") is not None:
            ledger_cmd += ["--est-miss", str(manifest["est_miss_total"]),
                           "--est-out", str(manifest["est_out_total"])]
        # The ledger reads usage and provider from each batch meta; the runner name is only a
        # fallback for old meta without `agent_provider`.
        known = ("agy", "openrouter", "opencode-native")
        runner = getattr(args, "runner", "dsh")
        source = ("opencode-native" if runner == "opencode"
                  else runner if runner in known
                  else manifest.get("runner") if manifest.get("runner") in known
                  else "auto")
        ledger_cmd += ["--source", source]
        if run(ledger_cmd, check=False) != 0:
            soft.append("sổ cái token không ghi được dòng mới")

    if "handoff" in steps:
        if run([PYTHON, str(SCRIPTS / "handoff.py"),
                "--wave", args.wave, "--prefix-hash", prefix_hash() or ""],
               check=False) != 0:
            soft.append("không sinh được tệp bàn giao")
        run([PYTHON, str(SCRIPTS / "ctx_probe.py")], check=False)

    if not verify_ok:
        fail_banner(args.wave, [f"Độ phủ của đợt dưới ngưỡng {args.min_coverage:.0%}. "
                                f"Xem danh sách bài thiếu ở bảng hậu kiểm phía trên."] + soft,
                    f"python scripts/article_run.py --wave {args.wave} --repair")
        return 1

    print("\n" + "=" * 84)
    print(f" ✅  ĐỢT {args.wave} HOÀN TẤT" + (f" — bước: {','.join(steps)}"
                                            if args.only else ""))
    for s in soft:
        print(f"   ⚠️  {s} (không chặn đợt)")
    print("=" * 84)
    print("Đọc tệp bàn giao mới nhất rồi ĐÓNG PHIÊN nếu áp suất ngữ cảnh ở mức vàng.")
    print("Mở phiên mới rẻ hơn mang theo ngữ cảnh đã phình: bộ nhớ đệm nằm ở phía nhà")
    print("cung cấp chứ không gắn với phiên.")
    print("=" * 84)
    return 0


def parse_steps(only: str | None) -> list[str]:
    """Convert the `--only` argument into the list of steps of the finish half.

    Args:
        only: Comma-separated step names, or None to run every step.

    Returns:
        Steps in execution order.

    Raises:
        SystemExit: If a step name is invalid.
    """
    if not only:
        return list(FINISH_STEPS)
    wanted = {s.strip() for s in only.split(",") if s.strip()}
    unknown = wanted - set(FINISH_STEPS)
    if unknown:
        raise SystemExit(f"Bước không hợp lệ: {', '.join(sorted(unknown))}. "
                         f"Chọn trong: {', '.join(FINISH_STEPS)}")
    return [s for s in FINISH_STEPS if s in wanted]


def fail_banner(wave: str, reasons: list[str], next_cmd: str) -> None:
    """Print a banner for an unfinished wave with the reasons and exactly one rerun command.

    Args:
        wave: Wave ID.
        reasons: Reason lines; empty lines are skipped.
        next_cmd: Command to run after fixing the cause.
    """
    print("\n" + "=" * 84)
    print(f" ❌  ĐỢT {wave} CHƯA HOÀN TẤT")
    print("=" * 84)
    for r in reasons:
        if r:
            print(f"   {r}")
    print(f"\n   Sửa xong thì chạy: {next_cmd}")
    print("=" * 84)


def wave_article_ids(wave: str) -> list[str]:
    """Collect the article IDs of a wave from the mapping tables on disk.

    The mapping table of a repair batch points back to the same articles as the
    original batch, so the union of all tables does not inflate the article count.

    Args:
        wave: Wave ID.

    Returns:
        De-duplicated article IDs in stable order.
    """
    ids: dict[str, None] = {}
    for p in sorted(glob.glob(str(TASK_DIR / f"article_{wave}_*.map.json"))):
        mapping = json.loads(Path(p).read_text(encoding="utf-8"))
        for aid in (mapping.get("index") or {}).values():
            ids[str(aid)] = None
    return list(ids)


def coverage_of(conn, article_ids: list[str]) -> dict[str, set[str]]:
    """Count the wave articles with passing and failing records in the database.

    The code-first version in `l1_outputs` is not counted, even when it failed: an
    article that has only that version is treated as having no recognition result, so
    `--repair` repacks it.

    Args:
        conn: Read-only SQLite connection.
        article_ids: Article IDs of the wave.

    Returns:
        Dict of the sets `l1_ok`, `l1_fail`, `gold_ok`, `gold_fail`.
    """
    out = {k: set() for k in ("l1_ok", "l1_fail", "gold_ok", "gold_fail")}
    guard = not_code_first_sql_for(conn)
    for i in range(0, len(article_ids), 500):
        chunk = article_ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for table, key, extra in (("l1_outputs", "l1", f" AND {guard}"),
                                  ("agent_outputs", "gold", "")):
            rows = conn.execute(
                f"SELECT article_id, max(dod_pass) FROM {table} "
                f"WHERE article_id IN ({marks}){extra} GROUP BY article_id", chunk)
            for aid, passed in rows:
                out[f"{key}_ok" if passed else f"{key}_fail"].add(aid)
    return out


def verify_wave(wave: str, *, min_coverage: float) -> int:
    """Compare the wave article set with what is actually in the database.

    Args:
        wave: Wave ID.
        min_coverage: Minimum share of articles that must have a passing record in each layer.

    Returns:
        Exit code 0 when both layers reach the threshold, 1 when below, 2 when there is
        no mapping table.
    """

    ids = wave_article_ids(wave)
    print(f"\n▶ hậu kiểm đợt {wave}")
    if not ids:
        print(f"   ⚠️  Không có bảng ánh xạ nào của đợt {wave}; không có gì để đối chiếu.")
        return 2
    db = resolve_db_path()
    conn = open_ro(db)
    try:
        cov = coverage_of(conn, ids)
    finally:
        conn.close()

    n = len(ids)
    rc = 0
    LAST_VERIFY.clear()
    LAST_VERIFY["articles"] = n
    print(f"   {'lớp':22} {'đạt':>6} {'trượt':>6} {'chưa có':>8} {'độ phủ':>8}")
    for key, label in (("l1", "nhận diện thực thể"), ("gold", "phân tích nội dung")):
        ok, bad = cov[f"{key}_ok"], cov[f"{key}_fail"]
        absent = n - len(ok) - len(bad)
        ratio = len(ok) / n
        LAST_VERIFY.update({f"{key}_ok": len(ok), f"{key}_fail": len(bad),
                            f"{key}_absent": absent, f"{key}_coverage": round(ratio, 4)})
        flag = "✅" if ratio >= min_coverage else "❌"
        if ratio < min_coverage:
            rc = 1
        print(f"   {label:22} {len(ok):>6} {len(bad):>6} {absent:>8} {ratio:>7.1%} {flag}")
        lacking = [a for a in ids if a not in ok][:5]
        if lacking:
            print(f"      thiếu, ví dụ: {', '.join(a[:12] for a in lacking)}")
    print(f"   tổng bài của đợt: {n} · ngưỡng {min_coverage:.0%}")
    return rc


def cmd_where(_args: argparse.Namespace) -> int:
    """Print the path contract and write permission of the article lane, at 0 tokens.

    Every question of the form "where is the file, which directory to run from, is the
    DB writable" is answered here, so the conductor needs neither to read source code
    nor to list directories.

    Args:
        _args: Parsed command-line arguments, unused.

    Returns:
        Exit code 0 when the DB is writable, 1 otherwise.
    """
    from src.users.compile import DEFAULT_OUTPUT_ROOT

    probe = probe_write()
    print("=" * 84)
    print(" 📍  HỢP ĐỒNG ĐƯỜNG DẪN — ARTICLE LANE")
    print("=" * 84)
    print(f"python        : {PYTHON}")
    print(f"cwd chuẩn     : {PROJECT_ROOT}")
    print("                mọi lệnh `scripts/...` chạy từ đây, không chạy từ gốc kho")
    print(f"DB            : {probe.path}")
    print(f"DB ghi        : {'✅ ' if probe.ok else '❌ '}{probe.reason}")
    if not probe.ok:
        print(f"                {probe.hint()}")
    print(f"data_root     : {paths.data_root()}  (MONOCLE_DATA_DIR)")
    print(f"Bronze        : {paths.bronze_dir()}")
    print(f"Silver        : {paths.silver_dir()}")
    print(f"work_packages : {paths.work_packages_dir()}")
    print(f"packet đợt    : {TASK_DIR}")
    print(f"đầu ra mô hình: {OUT_DIR}")
    print(f"đầu ra L1/Gold: {L1_OUT_DIR} | {GOLD_OUT_DIR}")
    print(f"mentions      : {paths.article_mentions_dir()}")
    print(f"thực thể      : {paths.entities_dir()}")
    print(f"logs          : {paths.logs_dir()}")
    print(f"bàn giao      : {paths.state_dir() / 'HANDOFF-latest.md'}")
    print(f"đăng ký       : {paths.subscriptions_dir()}")
    print(f"giao hàng     : {DEFAULT_OUTPUT_ROOT}")
    print("preset DSH    : news-scape-conductor, quyền workspace-write")
    print("=" * 84)
    return 0 if probe.ok else 1


def main(argv=None) -> int:
    """Run the command-line interface that conducts a wave.

    Args:
        argv: Command-line arguments. Defaults to `sys.argv`.

    Returns:
        Exit code of the selected wave half.
    """
    ap = argparse.ArgumentParser(description="Chạy trọn một đợt xử lý bài đăng")
    ap.add_argument("--wave", default=datetime.now().strftime("%Y%m%dT%H%M"),
                    help="Mã đợt")
    ap.add_argument("--batch", type=int, default=0,
                    help="Số bài mỗi lô; 0 = tự chọn theo số bài để gọn trong một sóng")
    ap.add_argument("--limit", type=int, default=100,
                    help="Tổng số bài của đợt — đây là đơn vị bạn quản lý")
    ap.add_argument("--concurrency", type=int, default=0,
                    help="Số lô chạy song song; 0 nghĩa là chạy hết cùng lúc. "
                         "Lượt hâm bộ nhớ đệm nằm riêng ở đầu chương trình nên "
                         "không lô nào phải chờ lô khác nữa")
    ap.add_argument("--date", help="Chỉ lấy bài xuất bản ngày YYYY-MM-DD")
    ap.add_argument("--today", action="store_true", help="Chỉ lấy bài hôm nay")
    ap.add_argument("--finish", action="store_true",
                    help="Chạy nửa hoàn tất thay vì nửa chuẩn bị")
    ap.add_argument("--repair", action="store_true",
                    help="Đóng gói lại đúng những bài lô đã gửi mà chưa nhận được "
                         "bản ghi, rồi sinh chương trình chạy bù")
    ap.add_argument("--resume", action="store_true",
                    help="Tự chọn nửa phù hợp dựa trên trạng thái đợt")
    ap.add_argument("--window-min", type=int, default=60,
                    help="Khoảng thời gian lùi lại khi gộp số đo token")
    ap.add_argument("--check-prefix", action="store_true",
                    help="Chỉ kiểm prefix rồi thoát")
    ap.add_argument("--where", action="store_true",
                    help="In hợp đồng đường dẫn, cwd chuẩn và quyền ghi DB rồi thoát")
    ap.add_argument("--only",
                    help="Chỉ chạy các bước hoàn tất đã nêu, phân tách bằng dấu phẩy: "
                         + ",".join(FINISH_STEPS))
    ap.add_argument("--min-coverage", type=float, default=MIN_COVERAGE,
                    help="Tỷ lệ bài tối thiểu của đợt phải vào DB ở mỗi lớp")
    ap.add_argument("--runner", choices=["dsh", "agy", "openrouter", "opencode"], default="dsh",
                    help="Runner nhận thức: 'dsh' (DeepSeek Flash), 'agy' (Gemini 3.8 Flash Low), "
                         "'openrouter' (stealth/space-bunny-alpha), hoặc 'opencode' (opencode/deepseek-v4.1-flash-free)")
    ap.add_argument("--exclude-file",
                    help="Tệp định danh bài không được đóng gói (ops_daemon giữ chỗ)")
    ap.add_argument("--analyze", action="store_true",
                    help="Chạy phân tích trực tiếp cho các lô của wave (dùng cho --runner agy/openrouter/opencode)")
    ap.add_argument("--mode", choices=["backlog", "bench", "adhoc"],
                    help="Chế độ chạy tay: backlog (dọn bài tồn, nạp DB), bench (thử agent, "
                         "không nạp DB, đầu ra ở data/agent_bench/<đợt>), adhoc. Daemon phát "
                         "lệnh thì bỏ qua")
    ap.add_argument("--force", action="store_true",
                    help="Bỏ qua kiểm va chạm với đợt daemon đang chạy và khoá provider")
    args = ap.parse_args(argv)

    if args.where:
        return cmd_where(args)

    if args.check_prefix:
        return 0 if check_prefix() else 1

    if args.only and not args.finish:
        ap.error("--only chỉ dùng cùng --finish")

    from src.ops import manual

    manifest_exists = (TASK_DIR / f"wave_{args.wave}.json").exists()
    phase = ("finish" if args.finish else "repair" if args.repair else
             "analyze" if args.analyze and manifest_exists else "prepare")
    gate = manual.begin(args.wave, args.mode, phase, args.runner, force=args.force,
                        target_date=args.date)
    if gate.refusal:
        print(f"❌ {gate.refusal}")
        return 3
    if gate.store is not None and gate.mode == "bench":
        global OUT_DIR
        OUT_DIR = gate.bench_dir
        OUT_DIR.mkdir(parents=True, exist_ok=True)
    if gate.store is not None and phase == "prepare" and not args.exclude_file:
        held = gate.exclude_ids()
        if held:
            excl = TASK_DIR / f"exclude_{args.wave}.txt"
            excl.write_text("\n".join(sorted(held)), encoding="utf-8")
            args.exclude_file = str(excl)
    rc = 1
    try:
        rc = _dispatch(args)
        return rc
    finally:
        ids = None
        if phase == "prepare":
            ids = lambda: sorted(wave_article_ids(args.wave))  # noqa: E731
        elif phase == "repair":
            ids = lambda: sorted(set(wave_article_ids(args.wave)) - wave_received_ids(args.wave))  # noqa: E731
        gate.finish(rc, ids)


def _dispatch(args: argparse.Namespace) -> int:
    """Run the wave half selected by the command-line flags.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code of the half that ran.
    """
    if args.analyze and not args.finish and not args.repair and not args.resume:
        manifest_path = TASK_DIR / f"wave_{args.wave}.json"
        if not manifest_path.exists():
            return cmd_prepare(args)
        return cmd_analyze(args)

    if args.repair:
        return cmd_repair(args)

    if args.resume:
        have, missing = pending_batches(args.wave)
        if have and not missing:
            return cmd_finish(args)
        if have and missing:
            print(f"Đợt {args.wave} còn dở: {len(have)} lô xong, {len(missing)} lô chưa.")
            print("Chạy lại chương trình điều phối cho các lô còn thiếu, hoặc dùng "
                  "--finish để xử lý phần đã có.")
            return 2
        return cmd_prepare(args)

    return cmd_finish(args) if args.finish else cmd_prepare(args)


if __name__ == "__main__":
    raise SystemExit(main())
