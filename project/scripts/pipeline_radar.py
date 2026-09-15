"""Bộ công cụ CLI trinh sát, quan sát và kiểm soát trạng thái vận hành News-Scape."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
AGENT_TASKS_DIR = DATA_ROOT / "agent_tasks"
AGENT_OUTPUTS_DIR = DATA_ROOT / "agent_outputs"
L1_TASKS_DIR = AGENT_TASKS_DIR / "l1"
L1_OUTPUTS_DIR = DATA_ROOT / "agent_outputs_l1"
USER_OUTPUT_DIR = PROJECT_ROOT.parent / "users" / "output"
MANIFEST_YAML = PROJECT_ROOT / "config" / "entities" / "manifest.yaml"
DB_PATH = Path("C:/data/news-scape/monocle.db")


def get_db_connection() -> sqlite3.Connection:
    """Khởi tạo kết nối SQLite ở chế độ Read-Only an toàn."""
    db_file = DB_PATH if DB_PATH.exists() else (DATA_ROOT / "monocle.db")
    uri = f"file:{db_file.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def cmd_status(args: argparse.Namespace) -> None:
    """Truy vấn toàn diện điểm chạm hiện tại của pipeline và đề xuất hành động."""
    target_date = args.date or f"{datetime.now():%Y-%m-%d}"
    print(f"================================================================================")
    print(f" 🛰️  NEWS-SCAPE PIPELINE OBSERVABILITY & STATUS REPORT — [{target_date}]")
    print(f"================================================================================")

    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Thống kê bài viết cào về
    cur.execute("SELECT count(*) FROM articles WHERE date(published_at) = ?", (target_date,))
    crawled_count = cur.fetchone()[0]

    # 2. Thống kê L1
    cur.execute("""
        SELECT count(distinct article_id)
        FROM l1_outputs
        WHERE date(created_at) = ?
    """, (target_date,))
    l1_done_count = cur.fetchone()[0]

    # 3. Thống kê Gold
    cur.execute("""
        SELECT count(distinct article_id)
        FROM agent_outputs
        WHERE date(created_at) = ?
    """, (target_date,))
    gold_done_count = cur.fetchone()[0]

    # 3b. Thống kê trạng thái hàng đợi L1 trong DB
    cur.execute("""
        SELECT count(1)
        FROM articles a
        WHERE date(a.published_at) = ?
        AND NOT EXISTS (SELECT 1 FROM l1_tasks lt WHERE lt.article_id = a.url_title_hash)
    """, (target_date,))
    l1_unrouted_count = cur.fetchone()[0]

    cur.execute("""
        SELECT count(1)
        FROM l1_tasks lt
        JOIN articles a ON lt.article_id = a.url_title_hash
        WHERE date(a.published_at) = ? AND lt.route = 'resolved' AND lt.status = 'pending'
    """, (target_date,))
    l1_resolved_pending = cur.fetchone()[0]

    # 4. Thống kê Task files đang treo trên đĩa
    l1_tasks_pending = len(glob.glob(str(L1_TASKS_DIR / "*.task.json")))
    gold_tasks_pending = len(glob.glob(str(AGENT_TASKS_DIR / "batch_*.task.json"))) + \
                         len([f for f in glob.glob(str(AGENT_TASKS_DIR / "*.task.json")) if not os.path.basename(f).startswith("batch_")])

    # 5. Thống kê Output files có bài chưa Ingest vào DB
    l1_outputs_waiting = 0
    for lf in glob.glob(str(L1_OUTPUTS_DIR / "*.output.json")):
        try:
            with open(lf, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data if isinstance(data, list) else data.get("outputs", [])
                for it in items:
                    cur.execute("SELECT 1 FROM l1_outputs WHERE article_id = ?", (it.get("article_id"),))
                    if not cur.fetchone():
                        l1_outputs_waiting += 1
        except Exception:
            pass

    gold_outputs_waiting = 0
    for gf in glob.glob(str(AGENT_OUTPUTS_DIR / "*.output.json")):
        try:
            with open(gf, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data if isinstance(data, list) else data.get("outputs", [])
                for it in items:
                    cur.execute("SELECT 1 FROM agent_outputs WHERE article_id = ?", (it.get("article_id"),))
                    if not cur.fetchone():
                        gold_outputs_waiting += 1
        except Exception:
            pass

    conn.close()

    print(f"1. DỮ LIỆU TẠI KHO (DATABASE & BRONZE/SILVER):")
    print(f"   • Số bài cào xuất bản trong ngày : {crawled_count:,} bài")
    print(f"   • Số bài đã hoàn tất tầng L1     : {l1_done_count:,} bài")
    print(f"   • Số bài đã hoàn tất tầng Gold   : {gold_done_count:,} bài")
    print()

    print(f"2. TRẠNG THÁI HÀNG ĐỢI FILE (TASK PACKETS & BATCHES):")
    print(f"   • Tác vụ L1 đang chờ Subagents   : {l1_tasks_pending} files/batches")
    print(f"   • Tác vụ Gold đang chờ Subagents : {gold_tasks_pending} files/batches")
    print(f"   • Bài L1 đã xuất chưa Ingest DB  : {l1_outputs_waiting} bài")
    print(f"   • Bài Gold đã xuất chưa Ingest DB: {gold_outputs_waiting} bài")
    print()

    # 6. Xác định điểm chạm và Đề xuất hành động tiếp theo
    print(f"3. ĐIỂM CHẠM VẬN HÀNH & ĐỀ XUẤT HÀNH ĐỘNG CỤ THỂ:")
    recommendations = []

    if l1_outputs_waiting > 0:
        recommendations.append((
            "HIGH",
            f"Có {l1_outputs_waiting} bài L1 trong output files chưa Ingest vào DB.",
            f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/l1_ingest.py data/agent_outputs_l1'
        ))

    if gold_outputs_waiting > 0:
        recommendations.append((
            "HIGH",
            f"Có {gold_outputs_waiting} bài Gold trong output files chưa nạp DB.",
            f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/agent_ingest.py data/agent_outputs'
        ))

    if l1_tasks_pending > 0:
        recommendations.append((
            "MEDIUM",
            f"Có {l1_tasks_pending} task/batch L1 cần khởi động Subagent `l1_entity_matcher`.",
            f'Gọi Subagents Flash xử lý các batch trong data/agent_tasks/l1/'
        ))

    if gold_tasks_pending > 0:
        recommendations.append((
            "MEDIUM",
            f"Có {gold_tasks_pending} task/batch Gold cần khởi động Subagent `gold_financial_analyst`.",
            f'Gọi Subagents Flash xử lý các batch trong data/agent_tasks/'
        ))

    if not recommendations:
        if l1_unrouted_count > 0:
            recommendations.append((
                "HIGH",
                f"Có {l1_unrouted_count} bài viết đã cào về nhưng chưa định tuyến L1.",
                f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/l1_route.py --from-db --date {target_date} --mini-batch 25'
            ))
        elif l1_resolved_pending > 0:
            recommendations.append((
                "HIGH",
                f"Có {l1_resolved_pending} bài L1 resolved đang chờ vật chất hóa Code-First.",
                f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/l1_ingest.py --code-first'
            ))
        elif gold_done_count > 0 and not any(glob.glob(str(USER_OUTPUT_DIR / "*" / f"{target_date}.xlsx"))):
            recommendations.append((
                "HIGH",
                "Đã có bài phân tích Gold nhưng chưa xuất bản Deliverable Excel cho người dùng.",
                f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/write_user_output.py --date {target_date}'
            ))
        else:
            recommendations.append((
                "INFO",
                "Toàn bộ chuỗi vận hành ngày này đã hoàn tất 100% sạch sẽ. Deliverable đã sẵn sàng.",
                "Không cần thao tác thêm. Hệ thống ở trạng thái ổn định."
            ))

    for priority, desc, cmd in recommendations:
        icon = "🔴" if priority == "HIGH" else ("🟡" if priority == "MEDIUM" else "🟢")
        print(f"   {icon} [{priority}] {desc}")
        print(f"      👉 Hành động: {cmd}")
    print(f"================================================================================\n")


def cmd_token(args: argparse.Namespace) -> None:
    """Quản lý, đo lường và dự toán mức tiêu thụ Token Burn thực tế."""
    target_date = args.date or f"{datetime.now():%Y-%m-%d}"
    print(f"================================================================================")
    print(f" 🪙  NEWS-SCAPE TOKEN METRICS & BUDGET AUDITOR — [{target_date}]")
    print(f"================================================================================")

    conn = get_db_connection()
    cur = conn.cursor()

    # Đếm số bài L1 do Agent xử lý (có in_list hoặc semantic)
    cur.execute("""
        SELECT count(*)
        FROM l1_outputs
        WHERE date(created_at) = ? AND agent_provider = 'antigravity'
    """, (target_date,))
    l1_agent_count = cur.fetchone()[0]

    # Đếm số bài L1 do Code-First xử lý (0 token)
    cur.execute("""
        SELECT count(*)
        FROM l1_outputs
        WHERE date(created_at) = ? AND (agent_provider IS NULL OR agent_provider = 'code_first')
    """, (target_date,))
    l1_codefirst_count = cur.fetchone()[0]

    # Đếm số bài Gold hoàn tất
    cur.execute("""
        SELECT count(*)
        FROM agent_outputs
        WHERE date(created_at) = ?
    """, (target_date,))
    gold_agent_count = cur.fetchone()[0]

    conn.close()

    # Định mức token thực nghiệm (Benchmark Flash v2-lean)
    L1_TOKEN_PER_ARTICLE = 450      # ~350 input + 100 output
    GOLD_TOKEN_PER_ARTICLE = 1470   # ~860 input + 610 output

    l1_token_burned = l1_agent_count * L1_TOKEN_PER_ARTICLE
    l1_token_saved = l1_codefirst_count * L1_TOKEN_PER_ARTICLE
    gold_token_burned = gold_agent_count * GOLD_TOKEN_PER_ARTICLE

    total_burned = l1_token_burned + gold_token_burned

    print(f"1. THỰC NGHIỆM TIÊU THỤ TOKEN (TIÊU CHUẨN FLASH / LEAN SCHEMA):")
    print(f"   • Tầng L1 (Subagents) : {l1_agent_count:,} bài × ~{L1_TOKEN_PER_ARTICLE} tokens = ~{l1_token_burned:,.0f} tokens")
    print(f"   • Tầng L1 (Code-First): {l1_codefirst_count:,} bài (TIẾT KIỆM 100%) = ~{l1_token_saved:,.0f} tokens tiết kiệm")
    print(f"   • Tầng Gold (Subagents): {gold_agent_count:,} bài × ~{GOLD_TOKEN_PER_ARTICLE} tokens = ~{gold_token_burned:,.0f} tokens")
    print(f"   ────────────────────────────────────────────────────────────────────────")
    print(f"   🔥 TỔNG TOKEN TIÊU THỤ THỰC TẾ  : ~{total_burned:,.0f} tokens (~{total_burned/1_000_000:.3f}M tokens)")
    print(f"   💡 TỔNG TOKEN ĐÃ TIẾT KIỆM ĐƯỢC : ~{l1_token_saved + (l1_codefirst_count + l1_agent_count - gold_agent_count) * GOLD_TOKEN_PER_ARTICLE:,.0f} tokens")
    print()

    print(f"2. ĐÁNH GIÁ HIỆU QUẢ SUBSCRIBER-GATING & CLEAN SCHEMA:")
    if l1_agent_count + l1_codefirst_count > 0:
        gating_ratio = (gold_agent_count / (l1_agent_count + l1_codefirst_count)) * 100
        print(f"   • Tỷ lệ chọn lọc Gold qua Watchlist : {gating_ratio:.1f}% ({gold_agent_count}/{l1_agent_count + l1_codefirst_count} bài)")
        print(f"   • Tỷ lệ cắt giảm Token vô ích       : {100 - gating_ratio:.1f}% chi phí tránh lãng phí")
        print(f"   • Chi phí ước tính (Google Flash)    : ~${(total_burned / 1_000_000) * 0.15:.4f} USD (Cực kỳ tối ưu)")
    print(f"================================================================================\n")


def cmd_users(args: argparse.Namespace) -> None:
    """Quan sát và phát hiện các thay đổi đăng ký người dùng mới / thiếu hụt thực thể."""
    print(f"================================================================================")
    print(f" 👥  NEWS-SCAPE USER WATCHLIST & ENTITY MONITOR")
    print(f"================================================================================")

    if not MANIFEST_YAML.exists():
        print(f"❌ Không tìm thấy tệp manifest tại: {MANIFEST_YAML}")
        return

    import yaml
    with open(MANIFEST_YAML, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f) or {}

    users = manifest.get("users", {})
    active_users = [u for u, is_active in users.items() if is_active]
    inactive_users = [u for u, is_active in users.items() if not is_active]

    print(f"1. DANH SÁCH NGƯỜI DÙNG TRONG HỆ THỐNG:")
    print(f"   • Đang kích hoạt (Active) : {len(active_users)} ({', '.join(active_users)})")
    print(f"   • Đang tạm dừng (Inactive): {len(inactive_users)} ({', '.join(inactive_users) if inactive_users else 'Không có'})")
    print()

    # Kiểm tra xem có file subscription excel mới nào chưa được kích hoạt không
    subs_dir = PROJECT_ROOT.parent / "users" / "subscriptions"
    if subs_dir.exists():
        excel_files = glob.glob(str(subs_dir / "*_news.xlsx"))
        unregistered = []
        for ef in excel_files:
            uname = os.path.basename(ef).replace("_news.xlsx", "")
            if uname.startswith("_") or uname.lower() in ("template", "_template"):
                continue
            if uname not in users:
                unregistered.append(uname)

        print(f"2. PHÁT HIỆN TẬP TIN ĐĂNG KÝ MỚI (SUBSCRIPTION DISCOVERY):")
        if unregistered:
            print(f"   ⚠️  Phát hiện {len(unregistered)} người dùng có file đăng ký nhưng CHƯA khai báo trong manifest.yaml:")
            for u in unregistered:
                print(f"      👉 User: '{u}' -> Cần thêm vào config/entities/manifest.yaml")
        else:
            print(f"   ✅ Toàn bộ file đăng ký đã được đồng bộ chuẩn với manifest.yaml.")
    print(f"================================================================================\n")


def main() -> None:
    """Điểm nhập lệnh điều phối CLI."""
    parser = argparse.ArgumentParser(description="Hệ thống Công cụ Giám sát & Quản trị Tự động News-Scape.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Lệnh status
    p_status = subparsers.add_parser("status", help="Truy vấn toàn diện điểm chạm hiện tại và đề xuất hành động.")
    p_status.add_argument("--date", help="Ngày cần quan sát (YYYY-MM-DD), mặc định là hôm nay.")

    # Lệnh token
    p_token = subparsers.add_parser("token", help="Đo lường token burn và đánh giá tiết kiệm chi phí.")
    p_token.add_argument("--date", help="Ngày cần đo lường (YYYY-MM-DD), mặc định là hôm nay.")

    # Lệnh users
    subparsers.add_parser("users", help="Quan sát và tra soát trạng thái người dùng & danh mục theo dõi.")

    args = parser.parse_args()
    if args.command == "status":
        cmd_status(args)
    elif args.command == "token":
        cmd_token(args)
    elif args.command == "users":
        cmd_users(args)


if __name__ == "__main__":
    main()
