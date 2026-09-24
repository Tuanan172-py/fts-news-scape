"""Gộp toàn bộ một đợt xử lý vào một lệnh duy nhất.

Chi phí token của phiên điều phối tỉ lệ với **số bước**, không tỉ lệ với số bài: mỗi
bước gửi lại toàn bộ lịch sử đã tích luỹ, và không có cơ chế nào cắt tỉa trước ngưỡng
nén tám mươi phần trăm. Quy trình vận hành cũ mô tả năm bước cho mỗi đợt. Lệnh này
gom chúng lại còn một, nên nó là đòn bẩy rẻ nhất trong cả kế hoạch và được làm trước
mọi thứ khác.

Script chạy được hai nửa của đợt và tự biết đang ở nửa nào:

- **Nửa chuẩn bị, 0 token**: kiểm prefix, đóng gói packet, in ra đúng chương trình mà
  phía điều phối cần chạy.
- **Nửa hoàn tất, 0 token**: bung bản ghi, nạp cơ sở dữ liệu, ghi sổ cái, sinh bàn giao.

Phần ở giữa là lượt gọi mô hình, do runtime thực hiện. Script không tự gọi mô hình.
"""
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

from src.agent.prefix import prefix_hash              # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402
from src.db.preflight import probe_write, resolve_db_path  # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
SCRIPTS = PROJECT_ROOT / "scripts"
TASK_DIR = PROJECT_ROOT / "data" / "agent_tasks" / "article"
OUT_DIR = PROJECT_ROOT / "data" / "agent_outputs_article"
L1_OUT_DIR = PROJECT_ROOT / "data" / "agent_outputs_l1"
GOLD_OUT_DIR = PROJECT_ROOT / "data" / "agent_outputs"
PYTHON = sys.executable
FINISH_STEPS = ("expand", "ingest", "verify", "ledger", "handoff")
# Cùng ngưỡng với tỷ lệ hỏng mười phần trăm của bước bung bản ghi.
MIN_COVERAGE = 0.90


def run(cmd: list[str], *, cwd: Path = PROJECT_ROOT, check: bool = True) -> int:
    """Chạy một lệnh con và in tiêu đề để người vận hành theo dõi được.

    Args:
        cmd: Danh sách phần tử của lệnh.
        cwd: Thư mục làm việc.
        check: Có dừng cả đợt khi lệnh trả mã khác 0 không.

    Returns:
        Mã thoát của lệnh con.

    Raises:
        SystemExit: Khi `check` bật và lệnh con thất bại.
    """
    label = " ".join(Path(c).name if c.endswith(".py") else c for c in cmd[1:3])
    print(f"\n▶ {label}")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run(cmd, cwd=str(cwd), env=env)
    if check and res.returncode not in (0,):
        print(f"\n❌ Dừng đợt: lệnh trả mã {res.returncode}. "
              f"Thất bại phải ồn ào, không đi tiếp trong im lặng.")
        raise SystemExit(res.returncode)
    return res.returncode


def check_prefix() -> bool:
    """Kiểm hai vế của prefix trước khi mở đợt.

    Vế một: tệp prefix trên đĩa còn khớp danh mục thực thể không. Lệch thì bảng tra
    của mô hình sai.

    Vế hai: `persona` trong preset còn khớp tệp ấy không. Lệch thì bộ nhớ đệm phía
    nhà cung cấp trượt, vì tiền tố không còn giống nhau từng byte giữa các lô — và
    đây là vế duy nhất hỏng mà không để lại dấu vết nào ngoài hoá đơn.

    Returns:
        True khi cả hai vế đều khớp, ngược lại False.
    """
    res = subprocess.run([PYTHON, str(SCRIPTS / "build_article_prefix.py"), "--check"],
                         cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    print((res.stdout or "").strip() or (res.stderr or "").strip())
    return res.returncode == 0


def warm_packet() -> str:
    """Dựng packet tí hon dùng để ghi bộ nhớ đệm cho phần tiền tố tĩnh.

    Bộ nhớ đệm của nhà cung cấp khớp theo tiền tố tính từ token 0, nên nó chỉ được
    ghi khi có một request thật đi qua. Trước đây lô đầu tiên gánh việc này: nó chạy
    một mình, xong rồi các lô còn lại mới được thả song song. Cái giá không nằm ở
    tiền mà ở thời gian — cả đợt phải chờ trọn một lô trăm bài chỉ để ghi mười nghìn
    token tiền tố.

    Một packet một bài rác ghi đúng phần tiền tố ấy trong vài giây, sau đó mọi lô
    chạy song song ngay từ đầu. Phần đắt thêm là bản ghi của bài rác, khoảng 900
    token đầu ra, tức dưới một phần nghìn đô la.

    Returns:
        Nội dung packet hâm cache, đúng định dạng packet thật.
    """
    return json.dumps({
        "d": datetime.now().strftime("%Y-%m-%d"),
        "n": 1,
        "a": [{"i": 0, "t": "Kiểm tra đường truyền, không phải bài thật",
               "p": ["Đây là mục kiểm tra kỹ thuật, không mang nội dung thị trường "
                     "nào và không cần phân tích sâu."]}],
    }, ensure_ascii=False)


def conductor_program(manifest: dict, *, concurrency: int) -> str:
    """Sinh chương trình mà phía điều phối chạy trong đúng một bước.

    Packet lớn hơn trần một lần đọc nên chương trình phân trang theo các cửa sổ dòng
    đã tính sẵn. Các lần đọc đó nằm trong cùng một chương trình nên không sinh thêm
    bước nào của mô hình, và kết quả của chúng ở lại trong chương trình chứ không vào
    ngữ cảnh của phiên điều phối.

    Đợt từ hai lô trở lên mở đầu bằng một lượt hâm bộ nhớ đệm (xem :func:`warm_packet`)
    rồi mới thả các lô, nên **mọi** lô đều trúng tiền tố tĩnh, kể cả lô đầu.

    Đợt một lô thì không hâm. Không có lô thứ hai để hưởng tiền tố đã ghi, nên lượt
    hâm chỉ chuyển chỗ đúng khoản token miss ấy sang một request khác, rồi tính thêm
    một bản ghi đầu ra và một quãng chờ. Hâm cache chỉ có lãi khi có người dùng lại.

    Args:
        manifest: Mô tả đợt do bước đóng gói sinh ra.
        concurrency: Số lô chạy song song tối đa.

    Returns:
        Mã nguồn chương trình dạng chuỗi.
    """
    batches = [{"id": b["batch_id"], "path": b["path"], "n": b["n"],
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
    """Xác định các lô đã chạy và chưa chạy của một đợt.

    Args:
        wave: Mã đợt.

    Returns:
        Cặp danh sách mã lô đã có đầu ra và mã lô còn thiếu.
    """
    packets = sorted(glob.glob(str(TASK_DIR / f"article_{wave}_*.task.json")))
    ids = [Path(p).name.replace(".task.json", "") for p in packets]
    have = {Path(p).name.replace(".output.json", "")
            for p in glob.glob(str(OUT_DIR / "*.output.json"))}
    return [i for i in ids if i in have], [i for i in ids if i not in have]


def missing_indices(batch_id: str) -> tuple[list[str], dict, dict]:
    """Xác định những bài đã gửi nhưng chưa nhận được bản ghi.

    Đây là cơ chế thay cho việc chia lô phòng xa: thay vì đoán trước một cái trần
    chưa đo rồi chia nhỏ mọi lô, gửi trọn lô rồi đối chiếu số bản ghi nhận được với
    số bài đã gửi. Chi phí khi ấy tỉ lệ với thứ thật sự mất.

    Args:
        batch_id: Mã lô.

    Returns:
        Bộ ba gồm danh sách chỉ số còn thiếu, nội dung packet và bảng ánh xạ.
    """
    from scripts.article_expand import salvage_records

    packet_path = TASK_DIR / f"{batch_id}.task.json"
    map_path = TASK_DIR / f"{batch_id}.map.json"
    out_path = OUT_DIR / f"{batch_id}.output.json"
    if not (packet_path.exists() and map_path.exists() and out_path.exists()):
        return [], {}, {}
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    records, _ = salvage_records(out_path.read_text(encoding="utf-8"))
    have = {str(r.get("i")) for r in records if r.get("i") is not None}
    return [i for i in mapping.get("index", {}) if i not in have], packet, mapping


def wave_received_ids(wave: str) -> set[str]:
    """Thu tập định danh bài đã nhận được bản ghi ở bất kỳ lô nào của đợt.

    Bài thiếu ở lô gốc nhưng đã có trong lô vá vẫn là bài đã nhận. Chỉ nhìn lô gốc
    thì mỗi lần chạy lại `--repair` lại đóng gói bù đúng những bài đã vá xong.

    Args:
        wave: Mã đợt.

    Returns:
        Tập định danh bài có bản ghi trong đầu ra của mô hình.
    """
    from scripts.article_expand import salvage_records

    got: set[str] = set()
    for p in glob.glob(str(TASK_DIR / f"article_{wave}_*.map.json")):
        batch_id = Path(p).name.replace(".map.json", "")
        out_path = OUT_DIR / f"{batch_id}.output.json"
        if not out_path.exists():
            continue
        index = json.loads(Path(p).read_text(encoding="utf-8")).get("index") or {}
        records, _ = salvage_records(out_path.read_text(encoding="utf-8"))
        got |= {index[str(r.get("i"))] for r in records if str(r.get("i")) in index}
    return got


def cmd_repair(args: argparse.Namespace) -> int:
    """Đóng gói lại đúng những bài chưa nhận được bản ghi rồi sinh chương trình chạy bù.

    Không cần tới cơ sở dữ liệu: nội dung bài đã nằm sẵn trong packet gốc, nên đường
    vá này cũng tiêu 0 token.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0 khi có việc để vá hoặc không còn gì thiếu, 2 khi chưa có đầu ra.
    """
    from scripts.article_pack import write_packet

    packets = sorted(glob.glob(str(TASK_DIR / f"article_{args.wave}_*.task.json")))
    if not packets:
        print(f"Không có packet nào của đợt {args.wave}.")
        return 2

    repairs: list[dict] = []
    total_missing = 0
    received = wave_received_ids(args.wave)
    for packet_path in packets:
        batch_id = Path(packet_path).name.replace(".task.json", "")
        missing, packet, mapping = missing_indices(batch_id)
        missing = [i for i in missing if mapping["index"][i] not in received]
        if not missing:
            continue
        total_missing += len(missing)
        arts = {str(a.get("i")): a for a in (packet.get("a") or [])}
        items: list[dict] = []
        index: dict[str, str] = {}
        tier: dict[str, int] = {}
        reason: dict[str, str] = {}
        for new_i, old_i in enumerate(missing):
            src = arts.get(old_i) or {}
            items.append({"i": new_i, "t": src.get("t", ""), "p": src.get("p", [])})
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
        repairs.append({"batch_id": rid, "path": str(rpath), "n": len(items),
                        "windows": budget["windows"], "from": batch_id})

    if not repairs:
        # Phân biệt hai trạng thái rất khác nhau mà trước đây in ra cùng một câu.
        # `missing_indices` coi lô chưa có tệp đầu ra là "không thiếu gì", nên một
        # đợt chưa chạy lần nào cũng nhận được lời chúc mừng "không cần vá".
        have, _missing = pending_batches(args.wave)
        if not have:
            print(f"⚠️  Đợt {args.wave}: chưa lô nào có đầu ra, nên không có gì để "
                  f"đối chiếu. Chạy chương trình điều phối trước đã.")
            return 2
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
    print()
    print(f"Chạy TRỌN nội dung tệp sau trong MỘT lệnh run_code:")
    print(f"  {prog_path}")
    print(f"Xong thì quay lại: python scripts/article_run.py --wave {args.wave} --finish")
    print("=" * 84)
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    """Chuẩn bị đợt: kiểm prefix, đóng gói packet, in chương trình điều phối.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0 khi chuẩn bị xong, khác 0 khi không có việc hoặc prefix lệch.
    """
    if not check_prefix():
        print("\n❌ Prefix lệch danh mục. Chạy `build_article_prefix.py` rồi cập nhật "
              "persona trong preset trước khi mở đợt, nếu không sẽ vỡ bộ nhớ đệm.")
        return 1

    # Nửa chuẩn bị chỉ đọc DB và ghi tệp trong kho, nên chạy được dưới workspace-write.
    # Chỉ báo trước cho người vận hành; chốt chặn thật nằm ở `--finish`, trước bước nạp.
    # Đầu ra của mô hình nằm trên đĩa, nên thiếu quyền ghi không làm mất token nào:
    # chạy lại `--finish` với quyền phù hợp là đủ.
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

    res = subprocess.run(pack_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(res.stdout.strip() or res.stderr.strip())
        return res.returncode
    manifest = json.loads(res.stdout.strip().splitlines()[-1])

    print("=" * 84)
    print(f" 🌊  ĐỢT {manifest['wave']} — ĐÃ CHUẨN BỊ, CHƯA TIÊU TOKEN NÀO")
    print("=" * 84)
    n_batches = len(manifest["batches"])
    print(f"Bài      : {manifest['articles']:,} ({manifest['tier1']:,} tầng ưu tiên)")
    # Khoá `max_completion_tokens` chưa bao giờ tồn tại trong manifest, nên dòng này
    # vẫn in "trần đầu ra 0 token" ở mọi đợt. Chia lô từ lâu chỉ còn theo `--batch`.
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

    concurrency = args.concurrency or len(manifest["batches"])
    program = conductor_program(manifest, concurrency=concurrency)
    prog_path = TASK_DIR / f"wave_{args.wave}.conductor.ts"
    prog_path.write_text(program, encoding="utf-8")

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


def cmd_finish(args: argparse.Namespace) -> int:
    """Hoàn tất đợt: bung bản ghi, nạp cơ sở dữ liệu, hậu kiểm, ghi sổ cái, sinh bàn giao.

    Dòng "HOÀN TẤT" chỉ được in khi mọi bước ghi dữ liệu thành công và hậu kiểm đạt
    ngưỡng. `--only` chạy lại đúng những bước đã hỏng thay vì cả chuỗi.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0 khi hoàn tất, 1 khi một bước ghi hỏng hoặc độ phủ dưới ngưỡng,
        2 khi chưa có đầu ra nào để xử lý.
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

    # Neo quy kết chi phí vào đúng thời điểm đóng gói đợt. Lấy mốc rộng hơn sẽ gộp
    # nhầm những phiên DSH không liên quan đang mở song song và thổi phồng con số
    # token mỗi bài lên hàng trăm lần.
    manifest_path = TASK_DIR / f"wave_{args.wave}.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    started = manifest.get("created_epoch")
    if not started:
        started = time.time() - args.window_min * 60
        print(f"⚠️  Manifest không có mốc thời gian đóng gói; lùi lại "
              f"{args.window_min} phút. Con số quy kết có thể gộp nhầm phiên khác.")

    # Thử quyền ghi trước khi bung và nạp. Lỗi sandbox chỉ lộ ra dưới dạng
    # "attempt to write a readonly database" ở giữa bước nạp, nghe như lỗi thuộc tính
    # tệp và dẫn người sửa đi sai hướng.
    if "ingest" in steps:
        probe = probe_write()
        if not probe.ok:
            fail_banner(args.wave, [f"DB không ghi được: {probe.path} — {probe.reason}",
                                    probe.hint()],
                        f"{rerun} ingest,verify,ledger,handoff")
            return 1

    if "expand" in steps:
        expand_rc = run([PYTHON, str(SCRIPTS / "article_expand.py"), "--wave", args.wave],
                        check=False)
        if expand_rc != 0:
            why = ("Tỷ lệ hỏng vượt ngưỡng. Xem lại persona của worker rồi chạy lại "
                   "đúng các lô hỏng." if expand_rc == 1
                   else f"Bước bung bản ghi trả mã {expand_rc}.")
            fail_banner(args.wave, [why], f"python scripts/article_run.py "
                                          f"--wave {args.wave} --finish")
            return 1

    # Nạp dữ liệu là bước ghi, không phải bước phụ trợ: hỏng thì dừng đợt ngay. Trước
    # đây hai lệnh này chạy với check=False, nên đợt W365 in "HOÀN TẤT" và thoát 0
    # trong khi cơ sở dữ liệu không nhận được dòng nào.
    # Chỉ nạp tệp của đúng đợt này. Quét cả thư mục thì mỗi lần hoàn tất lại nạp lại
    # mọi tệp cũ, kể cả tệp của lane L1/Gold đã ngừng, và dòng `failed` của lệnh nạp
    # đầy những lỗi không thuộc đợt.
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
                failed.append(f"{script} trả mã {rc}")
        if failed:
            fail_banner(args.wave, failed, f"{rerun} ingest,verify,ledger,handoff")
            return 1

    # Số `done/failed` của hai lệnh nạp là số cộng dồn trên cả thư mục, không phải
    # của đợt này. Chỉ đối chiếu theo đúng tập bài trong bảng ánh xạ của đợt mới trả
    # lời được câu "đợt này có vào cơ sở dữ liệu đủ không".
    verify_ok = True
    if "verify" in steps:
        verify_ok = verify_wave(args.wave, min_coverage=args.min_coverage) == 0

    soft: list[str] = []
    if "ledger" in steps:
        items = manifest.get("articles", 0)
        ledger_cmd = [PYTHON, str(SCRIPTS / "token_ledger.py"), "append",
                      "--wave", args.wave, "--items", str(items),
                      "--since", str(started), "--workers-only"]
        if manifest.get("est_miss_total") is not None:
            ledger_cmd += ["--est-miss", str(manifest["est_miss_total"]),
                           "--est-out", str(manifest["est_out_total"])]
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
    """Chuyển tham số `--only` thành danh sách bước của nửa hoàn tất.

    Args:
        only: Chuỗi tên bước phân tách bằng dấu phẩy, hoặc None để chạy mọi bước.

    Returns:
        Danh sách bước theo đúng thứ tự chạy.

    Raises:
        SystemExit: Khi có tên bước không hợp lệ.
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
    """In khung báo đợt chưa hoàn tất kèm lý do và đúng một lệnh chạy lại.

    Args:
        wave: Mã đợt.
        reasons: Các dòng lý do; dòng rỗng bị bỏ qua.
        next_cmd: Lệnh cần chạy sau khi sửa nguyên nhân.
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
    """Thu tập định danh bài của một đợt từ các bảng ánh xạ trên đĩa.

    Bảng ánh xạ của lô vá trỏ về đúng những bài của lô gốc, nên lấy hợp của mọi bảng
    không làm phình số bài.

    Args:
        wave: Mã đợt.

    Returns:
        Danh sách định danh bài đã khử trùng lặp, theo thứ tự ổn định.
    """
    ids: dict[str, None] = {}
    for p in sorted(glob.glob(str(TASK_DIR / f"article_{wave}_*.map.json"))):
        mapping = json.loads(Path(p).read_text(encoding="utf-8"))
        for aid in (mapping.get("index") or {}).values():
            ids[str(aid)] = None
    return list(ids)


def coverage_of(conn, article_ids: list[str]) -> dict[str, set[str]]:
    """Đếm bài của đợt đã có bản ghi đạt và trượt nghiệm thu trong cơ sở dữ liệu.

    Args:
        conn: Kết nối SQLite chỉ đọc.
        article_ids: Định danh bài của đợt.

    Returns:
        Từ điển các tập `l1_ok`, `l1_fail`, `gold_ok`, `gold_fail`.
    """
    out = {k: set() for k in ("l1_ok", "l1_fail", "gold_ok", "gold_fail")}
    for i in range(0, len(article_ids), 500):
        chunk = article_ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for table, key in (("l1_outputs", "l1"), ("agent_outputs", "gold")):
            rows = conn.execute(
                f"SELECT article_id, max(dod_pass) FROM {table} "
                f"WHERE article_id IN ({marks}) GROUP BY article_id", chunk)
            for aid, passed in rows:
                out[f"{key}_ok" if passed else f"{key}_fail"].add(aid)
    return out


def verify_wave(wave: str, *, min_coverage: float) -> int:
    """Đối chiếu tập bài của đợt với những gì thật sự nằm trong cơ sở dữ liệu.

    Args:
        wave: Mã đợt.
        min_coverage: Tỷ lệ bài tối thiểu phải có bản ghi đạt ở mỗi lớp.

    Returns:
        Mã thoát 0 khi cả hai lớp đạt ngưỡng, 1 khi thiếu, 2 khi không có bảng ánh xạ.
    """
    import sqlite3

    ids = wave_article_ids(wave)
    print(f"\n▶ hậu kiểm đợt {wave}")
    if not ids:
        print(f"   ⚠️  Không có bảng ánh xạ nào của đợt {wave}; không có gì để đối chiếu.")
        return 2
    db = resolve_db_path()
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        cov = coverage_of(conn, ids)
    finally:
        conn.close()

    n = len(ids)
    rc = 0
    print(f"   {'lớp':22} {'đạt':>6} {'trượt':>6} {'chưa có':>8} {'độ phủ':>8}")
    for key, label in (("l1", "nhận diện thực thể"), ("gold", "phân tích nội dung")):
        ok, bad = cov[f"{key}_ok"], cov[f"{key}_fail"]
        absent = n - len(ok) - len(bad)
        ratio = len(ok) / n
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
    """In hợp đồng đường dẫn và quyền ghi của đường xử lý bài đăng, 0 token.

    Mọi câu hỏi "tệp ở đâu, chạy từ thư mục nào, DB có ghi được không" đều có câu trả
    lời ở đây. Phía điều phối không cần đọc mã nguồn hay liệt kê thư mục.

    Args:
        _args: Tham số dòng lệnh đã phân tích, không dùng.

    Returns:
        Mã thoát 0 khi DB ghi được, 1 khi không.
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
    print(f"packet đợt    : {TASK_DIR}")
    print(f"đầu ra mô hình: {OUT_DIR}")
    print(f"bàn giao      : {PROJECT_ROOT / 'data' / 'state' / 'HANDOFF-latest.md'}")
    print(f"giao hàng     : {DEFAULT_OUTPUT_ROOT}  (gốc kho, không nằm trong project/)")
    print("preset DSH    : news-scape-conductor, quyền workspace-write")
    print("=" * 84)
    return 0 if probe.ok else 1


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh điều phối một đợt.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát của nửa đợt được chọn.
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
    args = ap.parse_args(argv)

    if args.where:
        return cmd_where(args)

    if args.check_prefix:
        return 0 if check_prefix() else 1

    if args.only and not args.finish:
        ap.error("--only chỉ dùng cùng --finish")

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
