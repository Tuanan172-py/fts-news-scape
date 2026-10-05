"""Benchmark va danh gia hieu nang cac mo hinh OpenRouter Free va Stealth cho nghiep vu phan tich tin tuc."""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Dam bao duong dan module luon tim thay cac tep lien quan
_CURRENT_DIR = Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))

import requests

try:
    from openrouter.schemas import validate_structured_output
except ImportError:
    from schemas import validate_structured_output

LOGS_DIR = _CURRENT_DIR / "logs"
JSONL_LOG_PATH = LOGS_DIR / "benchmark_records.jsonl"
CSV_SUMMARY_PATH = LOGS_DIR / "benchmark_summary.csv"

# Mau bai bao tai chinh dung de kiem thu nghiep vu
SAMPLE_ARTICLES = [
    {
        "id": "ART_01_POS",
        "title": "FPT ky hop dong 100 trieu USD tai thi truong My, loi nhuan quy 3 uoc tang 28%",
        "content": (
            "Tap doan FPT cong bo vua ky ket hop dong chuyen doi so tri gia hon 100 trieu USD "
            "voi mot tap doan tai chinh hang dau tai My. Nho khoi cong nghe duy tri da tang truong manh, "
            "loi nhuan truoc thue 9 thang dau nam 2026 uoc dat 8.100 ty dong, tang 28% so voi cung ky "
            "va hoan thanh 82% ke hoach ca nam."
        ),
        "expected_sentiment": "pos",
    },
    {
        "id": "ART_02_NEG",
        "title": "Xy dung Hoa Binh bi truy thu va phat thue hon 15 ty dong do vi pham ke khai",
        "content": (
            "Cuc Thue TP.HCM vua ban hanh quyet dinh xu phat vi pham hanh chinh ve thue doi voi "
            "Cong ty Co phan Tap doan Xay dung Hoa Binh. Tong so tien truy thu, tien phat va tien cham nop "
            "la 15,2 ty dong. Doanh nghiep dang ghi nhan dong tien kinh doanh am va no phai tra den han lon."
        ),
        "expected_sentiment": "neg",
    },
    {
        "id": "ART_03_NEU",
        "title": "Vinamilk thong bao lich chot danh sach co dong tham du DHDCD thuong nien 2026",
        "content": (
            "Cong ty Co phan Sua Viet Nam (Vinamilk - Ma: VNM) thong bao ngay 15/4 la ngay dang ky "
            "cuoi cung de chot danh sach co dong tham du Dai hoi dong co dong thuong nien nam 2026. "
            "Cuoc hop du kien to chuc theo hinh thuc truc tuyen vao ngay 25/4 de thong qua bao cao tai chinh "
            "va ke hoach chia co tuc nam."
        ),
        "expected_sentiment": "neu",
    },
]


def load_env_file() -> None:
    """Doc cac bien moi truong tu tep openrouter/.env neu chua ton tai trong os.environ."""
    env_path = _CURRENT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key not in os.environ:
            os.environ[key] = value


def query_openrouter(
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str,
    timeout: int = 60,
) -> tuple[int, str, dict[str, Any], float]:
    """Gui yeu cau suy luan den OpenRouter va do luong chi so thoi gian.

    Args:
        api_key: Khoa xac thuc OpenRouter.
        model: Dinh danh mo hinh dich vu.
        prompt: Noi dung van ban can xu ly.
        system_prompt: Chi dan dinh dang va vai tro nghiep vu.
        timeout: Thoi gian cho toi da cua yeu cau tinh bang giay.

    Returns:
        Tuple bao gom ma trang thai HTTP, noi dung tra ve tho, thong tin usage token, va do tre giay.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Tuanan172-py/fts-news-scape",
        "X-Title": "News-Scape Article Processing",
    }
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    start = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        elapsed = time.perf_counter() - start
        status_code = resp.status_code
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            return status_code, content, usage, elapsed
        return status_code, resp.text, {}, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return -1, str(exc), {}, elapsed


def run_benchmark(models_to_test: list[str]) -> list[dict[str, Any]]:
    """Thuc thi toan bo quy trinh benchmark tren danh sach mo hinh chi dinh.

    Args:
        models_to_test: Danh sach ten mo hinh can thu nghiem.

    Returns:
        Danh sach ban ghi chi tiet cua tung luot goi API.
    """
    load_env_file()
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print("[LOI] Khong tim thay OPENROUTER_API_KEY trong bien moi truong hoac openrouter/.env")
        sys.exit(1)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    system_instruction = (
        "Ban la chuyen vien phan tich tin tuc tai chinh chung khoan Viet Nam. "
        "Doc ky bai bao va tra ve DUY NHAT 1 JSON object co dung schema sau: "
        "{\n"
        '  "summary": "Tom tat ngan gon trong 1-2 cau",\n'
        '  "sentiment": "pos" | "neg" | "neu",\n'
        '  "materiality_score": so thuc tu 0.0 den 1.0 (do quan trong doi voi co phieu/doanh nghiep),\n'
        '  "key_points": ["Luan diem 1", "Luan diem 2"]\n'
        "}\n"
        "BAT BUOC: sentiment chi duoc la pos, neg, hoac neu. Khong duoc them text ben ngoai JSON."
    )

    print("=" * 80)
    print(f"BAT DAU BENCHMARK OPENROUTER TREN {len(models_to_test)} MO HINH")
    print(f"So bai bao thu nghiem: {len(SAMPLE_ARTICLES)}")
    print(f"Thu muc luu tru logs: {LOGS_DIR}")
    print("=" * 80)

    for model in models_to_test:
        print(f"\n>>> Dang kiem thu mo hinh: [{model}]")
        for article in SAMPLE_ARTICLES:
            art_id = article["id"]
            prompt = f"Tieu de: {article['title']}\nNoi dung: {article['content']}"

            print(f"  -> Gui yeu cau cho bai {art_id}...", end="", flush=True)
            status_code, raw_output, usage, latency = query_openrouter(
                api_key=api_key,
                model=model,
                prompt=prompt,
                system_prompt=system_instruction,
            )

            schema_obj = None
            schema_valid = False
            error_note = ""

            if status_code == 200:
                schema_obj = validate_structured_output(raw_output)
                schema_valid = schema_obj is not None
                if not schema_valid:
                    error_note = "Loi parse JSON hoac vi pham rang buoc schema"
            else:
                error_note = f"HTTP {status_code}: {raw_output[:200]}"

            prompt_tok = usage.get("prompt_tokens", 0)
            comp_tok = usage.get("completion_tokens", 0)
            total_tok = usage.get("total_tokens", prompt_tok + comp_tok)

            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "article_id": art_id,
                "http_status": status_code,
                "latency_sec": round(latency, 3),
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "total_tokens": total_tok,
                "schema_valid": schema_valid,
                "error_note": error_note,
                "sentiment": schema_obj.sentiment if schema_obj else None,
                "expected_sentiment": article["expected_sentiment"],
                "sentiment_match": (schema_obj.sentiment == article["expected_sentiment"]) if schema_obj else False,
                "materiality_score": schema_obj.materiality_score if schema_obj else None,
                "key_points_count": len(schema_obj.key_points) if schema_obj else 0,
                "summary": schema_obj.summary if schema_obj else None,
                "raw_response": raw_output[:300] if not schema_valid else None,
            }
            records.append(record)

            # Ghi ngay tung record vao JSONL
            with open(JSONL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            status_str = f"PASS ({latency:.2f}s)" if schema_valid else f"FAIL ({status_code})"
            print(f" {status_str} | Tok: {total_tok} | Sent: {record['sentiment']}")

            # Nghing ngan giua cac request de tranh burst rate limit
            time.sleep(1.0)

    # Xuat bao cao tong hop ra CSV
    write_summary_csv(records, models_to_test)
    return records


def write_summary_csv(records: list[dict[str, Any]], models: list[str]) -> None:
    """Tong hop so lieu hieu nang va xuat ra tep CSV phan tich so sanh."""
    summary_rows: list[dict[str, Any]] = []

    for model in models:
        m_recs = [r for r in records if r["model"] == model]
        if not m_recs:
            continue
        total_req = len(m_recs)
        success_req = sum(1 for r in m_recs if r["http_status"] == 200)
        schema_passed = sum(1 for r in m_recs if r["schema_valid"])
        sentiment_matched = sum(1 for r in m_recs if r["sentiment_match"])

        latencies = [r["latency_sec"] for r in m_recs if r["http_status"] == 200]
        avg_lat = round(sum(latencies) / len(latencies), 3) if latencies else 0.0
        min_lat = min(latencies) if latencies else 0.0
        max_lat = max(latencies) if latencies else 0.0

        total_p_tok = sum(r["prompt_tokens"] for r in m_recs)
        total_c_tok = sum(r["completion_tokens"] for r in m_recs)

        summary_rows.append({
            "model": model,
            "total_requests": total_req,
            "http_200_rate": f"{(success_req / total_req) * 100:.1f}%",
            "schema_pass_rate": f"{(schema_passed / total_req) * 100:.1f}%",
            "sentiment_acc": f"{(sentiment_matched / total_req) * 100:.1f}%",
            "avg_latency_s": avg_lat,
            "min_latency_s": min_lat,
            "max_latency_s": max_lat,
            "total_prompt_tokens": total_p_tok,
            "total_completion_tokens": total_c_tok,
            "cost_usd": "0.00",
        })

    fieldnames = [
        "model",
        "total_requests",
        "http_200_rate",
        "schema_pass_rate",
        "sentiment_acc",
        "avg_latency_s",
        "min_latency_s",
        "max_latency_s",
        "total_prompt_tokens",
        "total_completion_tokens",
        "cost_usd",
    ]

    with open(CSV_SUMMARY_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print("\n" + "=" * 80)
    print("BANG TONG HOP CHI SO BENCHMARK MO HINH")
    print("=" * 80)
    header_fmt = "{:<32} {:<10} {:<10} {:<10} {:<10} {:<10}"
    print(header_fmt.format("Model", "HTTP 200", "Schema", "Sent Acc", "Avg Lat(s)", "Cost"))
    print("-" * 84)
    for row in summary_rows:
        print(
            header_fmt.format(
                row["model"][:31],
                row["http_200_rate"],
                row["schema_pass_rate"],
                row["sentiment_acc"],
                str(row["avg_latency_s"]),
                row["cost_usd"],
            )
        )
    print("=" * 80)
    print(f"[+] Chi tiet tung request: {JSONL_LOG_PATH}")
    print(f"[+] File CSV tong hop: {CSV_SUMMARY_PATH}")


def main() -> None:
    """Diem vao thuc thi benchmark."""
    # Danh sach mo hinh test: openrouter/free (theo yeu cau), stealth/space-bunny-alpha va model free manh
    models = [
        "openrouter/free",
        "stealth/space-bunny-alpha",
        "google/gemma-4-31b-it:free",
    ]
    if len(sys.argv) > 1:
        models = sys.argv[1:]

    run_benchmark(models)


if __name__ == "__main__":
    main()
