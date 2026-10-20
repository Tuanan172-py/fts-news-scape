"""Bộ cài đặt tự động gói plugin fpts-market-intel cho AGY và Gemini IDE (ADR-0025)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def log(msg: str, prefix: str = "->") -> None:
    """In thông báo ra màn hình với định dạng chuẩn."""
    print(f"  {prefix} {msg}")


def main() -> int:
    """Điểm vào thực thi tiến trình cài đặt plugin."""
    if sys.platform == "win32" and sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("==========================================================")
    print("   FPTS MARKET INTEL — BỘ CÀI ĐẶT UNIFIED PLUGIN (ADR-0025)")
    print("==========================================================")

    # 1. Kiểm tra môi trường DuckDB
    print("\n[1/4] Kiem tra moi truong DuckDB...")
    try:
        import duckdb
        log(f"DuckDB version {duckdb.__version__} da san sang.")
    except ImportError:
        log("Chua cai dat duckdb. Dang tien hanh cai dat qua pip...", prefix="!")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "duckdb", "--quiet"], check=False)
        if res.returncode != 0:
            print("Loi: Khong the cai dat duckdb qua pip.", file=sys.stderr)
            return 1
        log("Cai dat duckdb thanh cong.")

    # 2. Kiem tra thu muc du lieu Lakehouse (SharePoint Shortcut)
    print("\n[2/4] Kiem tra ket noi ho du lieu Lakehouse...")
    home = Path.home()
    default_candidates = [
        home / "OneDrive - fpts.com.vn" / "Shortcuts" / "FRA_DataIngestion - news-data",
        home / "OneDrive - fpts.com.vn" / "FRA_DataIngestion - news-data",
        home / "OneDrive" / "Shortcuts" / "FRA_DataIngestion - news-data",
        home / "OneDrive" / "FRA_DataIngestion - news-data",
    ]

    lakehouse_root = None
    env_root = os.environ.get("NEWS_DATA_ROOT")
    if env_root and (Path(env_root) / "_manifest" / "latest.json").exists():
        lakehouse_root = Path(env_root).resolve()
    else:
        for cand in default_candidates:
            if (cand / "_manifest" / "latest.json").exists():
                lakehouse_root = cand.resolve()
                break

    if lakehouse_root:
        log(f"Tim thay ho du lieu tai: {lakehouse_root}")
        # Dam bao ghim tep ngoai tuyen (attrib +P)
        if sys.platform == "win32":
            articles_dir = lakehouse_root / "parquet" / "articles"
            if articles_dir.exists():
                subprocess.run(f'attrib -U +P /s /d "{articles_dir}\\*"', shell=True, capture_output=True)
                log("Da dam bao ghim tep ngoai tuyen (attrib -U +P).")
    else:
        log("[CANH BAO] Chua tim thay shortcut 'FRA_DataIngestion - news-data'.", prefix="!")
        log("De co day du du lieu, vui long truy cap SharePoint:")
        log("https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion")
        log("va bam nut 'Add shortcut to OneDrive'.")

    # 3. Sao chep plugin vao ~/.gemini/config/plugins/fpts-market-intel
    print("\n[3/4] Cai dat plugin vao ~/.gemini/config/plugins/fpts-market-intel...")
    repo_root = Path(__file__).resolve().parents[1]
    source_plugin = repo_root / "plugins" / "fpts-market-intel"
    target_plugin = home / ".gemini" / "config" / "plugins" / "fpts-market-intel"

    if not source_plugin.exists():
        print(f"Loi: Khong tim thay thu muc plugin tai {source_plugin}", file=sys.stderr)
        return 1

    target_plugin.mkdir(parents=True, exist_ok=True)

    # Chep de toan bo thu muc
    for item in source_plugin.iterdir():
        dst = target_plugin / item.name
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)

    log(f"Da dong bo toan bo Manifest, Rules, Skills va Tools vao: {target_plugin}")

    # 4. Kiem tra Self-Test
    print("\n[4/4] Chay kiem tra tich hop (Self-Test)...")
    client_script = target_plugin / "tools" / "lakehouse_client.py"
    res = subprocess.run([sys.executable, str(client_script), "status"], capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0:
        log("Self-Test THANH CONG!")
        print(res.stdout)
    else:
        log(f"Self-Test bao loi: {res.stderr}", prefix="!")

    print("==========================================================")
    print("   CAI DAT HOAN TAT! KHOI DONG AGY HOAC GEMINI DE BAT DAU ")
    print("==========================================================")
    print("Cac cau lenh goi y co the thu ngay trong chat:")
    print("  * 'Soi tin tuc ma HPG trong 3 ngay gan nhat'")
    print("  * 'Tong hop Morning Brief cho danh muc hom nay'")
    print("  * 'Quet nhip dap va sac thai nganh Ngan hang tuan qua'")
    print("  * 'Kiem tra do tuoi du lieu Lakehouse hom nay'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
