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

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
SCRIPTS = PROJECT_ROOT / "scripts"
TASK_DIR = PROJECT_ROOT / "data" / "agent_tasks" / "article"
OUT_DIR = PROJECT_ROOT / "data" / "agent_outputs_article"
PYTHON = sys.executable


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

// Ghép lại nội dung packet từ các cửa sổ dòng. Công cụ đọc trả về dòng có đánh số
// trong khung <content>, nên phải bóc lại phần văn bản gốc.
async function readPacket(b) {{
  let text = "";
  for (const [offset, limit] of b.windows) {{
    const r = await tools.read({{ file_path: b.path, offset, limit }});
    const body = typeof r === "string" ? r : (r.content ?? r.text ?? JSON.stringify(r));
    for (const line of String(body).split("\\n")) {{
      const m = line.match(/^\\s*(\\d+): ?(.*)$/);
      if (m) text += m[2] + "\\n";
    }}
  }}
  return text;
}}

async function runBatch(b) {{
  const packet = await readPacket(b);
  if (!packet.trim()) return {{ id: b.id, ok: false, why: "packet rỗng" }};
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
  done.push(...await Promise.all(slice.map(runBatch)));
}}

// Chỉ trả về con số. Nội dung packet và đầu ra của lô KHÔNG được vào ngữ cảnh.
return {{ wave: "{manifest['wave']}", batches: done.length,
         failed: done.filter(d => !d.ok).map(d => d.id) }};
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
    for packet_path in packets:
        batch_id = Path(packet_path).name.replace(".task.json", "")
        missing, packet, mapping = missing_indices(batch_id)
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
    print(f"Lượt gọi : {n_batches} (tối đa {manifest.get('per_call', '?')} bài mỗi "
          f"lượt theo --batch; mốc tham chiếu đầu ra "
          f"{manifest.get('reference_completion_tokens', 0):,} token mỗi request)")
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
    """Hoàn tất đợt: bung bản ghi, nạp cơ sở dữ liệu, ghi sổ cái, sinh bàn giao.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0 khi hoàn tất, 2 khi chưa có đầu ra nào để xử lý.
    """
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

    expand_rc = run([PYTHON, str(SCRIPTS / "article_expand.py")], check=False)
    if expand_rc == 1:
        print("\n⚠️  Tỷ lệ hỏng vượt ngưỡng. Dừng đợt trước khi nạp cơ sở dữ liệu.")
        print("   Xem lại persona của worker rồi chạy lại đúng các lô hỏng.")
        return 1

    run([PYTHON, str(SCRIPTS / "l1_ingest.py"), "data/agent_outputs_l1"], check=False)
    run([PYTHON, str(SCRIPTS / "agent_ingest.py"), "data/agent_outputs"], check=False)

    items = manifest.get("articles", 0)
    ledger_cmd = [PYTHON, str(SCRIPTS / "token_ledger.py"), "append",
                  "--wave", args.wave, "--items", str(items),
                  "--since", str(started)]
    if manifest.get("est_miss_total") is not None:
        ledger_cmd += ["--est-miss", str(manifest["est_miss_total"]),
                       "--est-out", str(manifest["est_out_total"])]
    run(ledger_cmd, check=False)

    run([PYTHON, str(SCRIPTS / "handoff.py"),
         "--wave", args.wave, "--prefix-hash", prefix_hash() or ""], check=False)
    run([PYTHON, str(SCRIPTS / "ctx_probe.py")], check=False)

    print("\n" + "=" * 84)
    print(f" ✅  ĐỢT {args.wave} HOÀN TẤT")
    print("=" * 84)
    print("Đọc tệp bàn giao mới nhất rồi ĐÓNG PHIÊN nếu áp suất ngữ cảnh ở mức vàng.")
    print("Mở phiên mới rẻ hơn mang theo ngữ cảnh đã phình: bộ nhớ đệm nằm ở phía nhà")
    print("cung cấp chứ không gắn với phiên.")
    print("=" * 84)
    return 0


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
    ap.add_argument("--batch", type=int, default=100, help="Số bài mỗi lô")
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
    args = ap.parse_args(argv)

    if args.check_prefix:
        return 0 if check_prefix() else 1

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
