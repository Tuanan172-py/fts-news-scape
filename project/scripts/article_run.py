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

from src.core.stdio import force_utf8_stdio            # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
SCRIPTS = PROJECT_ROOT / "scripts"
TASK_DIR = PROJECT_ROOT / "data" / "agent_tasks" / "article"
OUT_DIR = PROJECT_ROOT / "data" / "agent_outputs_article"
PREFIX_META = PROJECT_ROOT / "data" / "prefix" / "ARTICLE_SYSTEM_CORE.meta.json"
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


def prefix_hash() -> str | None:
    """Đọc giá trị băm của prefix đang dùng.

    Returns:
        Chuỗi băm, hoặc None khi chưa sinh prefix.
    """
    try:
        return json.loads(PREFIX_META.read_text(encoding="utf-8")).get("hash")
    except (OSError, json.JSONDecodeError):
        return None


def check_prefix() -> bool:
    """Kiểm prefix trên đĩa còn khớp danh mục thực thể không.

    Prefix lệch danh mục vừa làm sai bảng tra của mô hình, vừa phá bộ nhớ đệm phía
    nhà cung cấp vì tiền tố không còn giống nhau từng byte giữa các lô.

    Returns:
        True khi prefix còn khớp, ngược lại False.
    """
    res = subprocess.run([PYTHON, str(SCRIPTS / "build_article_prefix.py"), "--check"],
                         cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    print((res.stdout or "").strip() or (res.stderr or "").strip())
    return res.returncode == 0


def conductor_program(manifest: dict, *, concurrency: int) -> str:
    """Sinh chương trình mà phía điều phối chạy trong đúng một bước.

    Packet lớn hơn trần một lần đọc nên chương trình phân trang theo các cửa sổ dòng
    đã tính sẵn. Các lần đọc đó nằm trong cùng một chương trình nên không sinh thêm
    bước nào của mô hình, và kết quả của chúng ở lại trong chương trình chứ không vào
    ngữ cảnh của phiên điều phối.

    Args:
        manifest: Mô tả đợt do bước đóng gói sinh ra.
        concurrency: Số lô chạy song song tối đa.

    Returns:
        Mã nguồn chương trình dạng chuỗi.
    """
    batches = [{"id": b["batch_id"], "path": b["path"], "n": b["n"],
                "windows": b["windows"]} for b in manifest["batches"]]
    out_dir = str(OUT_DIR).replace("\\", "\\\\")

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
  const text = typeof res === "string" ? res : (res.text ?? res.content ?? JSON.stringify(res));
  await tools.write({{ file_path: OUT + "\\\\" + b.id + ".output.json", content: text }});
  return {{ id: b.id, ok: true, chars: text.length }};
}}

// Lô đầu chạy một mình để ghi bộ nhớ đệm cho phần tiền tố tĩnh; các lô sau mới
// chạy song song và khi đó chúng đều trúng cache.
const done = [];
done.push(await runBatch(BATCHES[0]));
for (let i = 1; i < BATCHES.length; i += CONCURRENCY) {{
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
    print(f"Bài      : {manifest['articles']:,} ({manifest['tier1']:,} tầng ưu tiên)")
    print(f"Lô       : {len(manifest['batches'])}")
    print(f"Dự toán  : quota {manifest['est_quota_total']:,} token "
          f"(miss {manifest['est_miss_total']:,} · hit {manifest['est_hit_total']:,} · "
          f"out {manifest['est_out_total']:,})")
    print(f"Prefix   : hash {prefix_hash()}")
    print(f"Manifest : {manifest['manifest']}")

    program = conductor_program(manifest, concurrency=args.concurrency)
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
    ap.add_argument("--limit", type=int, default=300, help="Tổng số bài của đợt")
    ap.add_argument("--concurrency", type=int, default=3,
                    help="Số lô chạy song song sau lô khởi động bộ nhớ đệm")
    ap.add_argument("--date", help="Chỉ lấy bài xuất bản ngày YYYY-MM-DD")
    ap.add_argument("--today", action="store_true", help="Chỉ lấy bài hôm nay")
    ap.add_argument("--finish", action="store_true",
                    help="Chạy nửa hoàn tất thay vì nửa chuẩn bị")
    ap.add_argument("--resume", action="store_true",
                    help="Tự chọn nửa phù hợp dựa trên trạng thái đợt")
    ap.add_argument("--window-min", type=int, default=60,
                    help="Khoảng thời gian lùi lại khi gộp số đo token")
    ap.add_argument("--check-prefix", action="store_true",
                    help="Chỉ kiểm prefix rồi thoát")
    args = ap.parse_args(argv)

    if args.check_prefix:
        return 0 if check_prefix() else 1

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
