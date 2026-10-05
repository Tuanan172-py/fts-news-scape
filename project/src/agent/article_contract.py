"""Hợp đồng đầu ra của article-processor: nguồn hằng số, bộ bóc vỏ và bộ kiểm dùng chung mọi provider."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "article-compact-v2.schema.json"
CONTRACT_VERSION = "article-compact-v2"


def _load_schema() -> dict:
    """Nạp lược đồ bản ghi gọn từ tệp nguồn chân lý.

    Returns:
        Từ điển JSON Schema của bản ghi gọn.
    """
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


SCHEMA = _load_schema()
_REC = SCHEMA["$defs"]["record"]["properties"]

REQUIRED_KEYS = tuple(SCHEMA["$defs"]["record"]["required"])
GROUP_CODES = tuple(_REC["e"]["items"]["prefixItems"][1]["enum"])
SENTIMENT_CODES = tuple(_REC["sn"]["enum"])
TIME_CODES = tuple(_REC["ts"]["enum"])
K_MIN, K_MAX = _REC["k"]["minItems"], _REC["k"]["maxItems"]
C_MIN, C_MAX = _REC["c"]["minItems"], _REC["c"]["maxItems"]
IM_MIN_CHARS = _REC["im"]["minLength"]

# Tham số lấy mẫu chuẩn (ADR 0017 D5). Provider không hỗ trợ tham số nào thì ghi
# `unsupported` vào meta thay vì tự đổi giá trị.
SAMPLING = {"temperature": 0, "seed": 20261005}

MIN_CITATION_CHARS = 20
MAX_SUMMARY_SENTENCES = 3

SENTIMENT_MAP = {"pos": "positive", "neg": "negative", "neu": "neutral"}
TIME_MAP = {"urg": "urgent", "today": "today", "week": "this_week",
            "month": "this_month", "arch": "archive"}

_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ỸĐ])")
_VIETNAMESE_DIACRITICS_RE = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


def has_vietnamese_diacritics(text: str) -> bool:
    """Kiểm chuỗi có chứa ít nhất một ký tự tiếng Việt có dấu.

    Args:
        text: Chuỗi cần kiểm.

    Returns:
        True khi có ký tự có dấu.
    """
    return bool(_VIETNAMESE_DIACRITICS_RE.search(text or ""))


def unwrap_tool_envelope(text: str) -> str:
    """Bóc lớp vỏ kết quả công cụ của DSH để lấy đúng phần văn bản mô hình trả về.

    Công cụ gọi agent của DSH trả về `{"kind":..., "runId":..., "output":[{"type":
    "text","text":"..."}]}`. Ghi nguyên đối tượng ấy ra đĩa thì bộ bóc bản ghi đọc
    nhầm lớp vỏ thành một bản ghi rác có hai trường `type` và `text`.

    Args:
        text: Nội dung thô của tệp đầu ra.

    Returns:
        Phần văn bản mô hình trả về, hoặc nguyên chuỗi vào khi không có lớp vỏ.
    """
    stripped = (text or "").strip()
    if not stripped.startswith("{"):
        return text
    try:
        env = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    if not isinstance(env, dict):
        return text
    out = env.get("output")
    if isinstance(out, list):
        parts = [str(o.get("text", "")) for o in out
                 if isinstance(o, dict) and o.get("type") == "text"]
        if parts:
            return "".join(parts)
    for key in ("text", "content"):
        if isinstance(env.get(key), str):
            return env[key]
    return text


def _strip_transport(text: str) -> str:
    """Bỏ vỏ truyền tải: envelope vendor, rào mã và lời dẫn trước mảng JSON.

    Args:
        text: Nội dung thô do mô hình trả về.

    Returns:
        Chuỗi bắt đầu tại dấu `[` đầu tiên khi có lời dẫn phía trước.
    """
    cleaned = unwrap_tool_envelope(text).strip()
    if cleaned.startswith("```"):
        lines = [ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("[")
    if start > 0:
        cleaned = cleaned[start:]
    return cleaned


def transport_flags(text: str) -> dict[str, int]:
    """Đếm các dạng vỏ truyền tải có trong đầu ra thô.

    Args:
        text: Nội dung thô do mô hình trả về.

    Returns:
        Bộ đếm `envelope`, `fence`, `prose_prefix`, mỗi khoá bằng 0 hoặc 1.
    """
    raw = (text or "").strip()
    unwrapped = unwrap_tool_envelope(text or "").strip()
    flags = {"envelope": int(unwrapped != raw), "fence": 0, "prose_prefix": 0}
    if unwrapped.startswith("```"):
        flags["fence"] = 1
        unwrapped = "\n".join(ln for ln in unwrapped.splitlines()
                              if not ln.strip().startswith("```")).strip()
    if unwrapped.find("[") > 0:
        flags["prose_prefix"] = 1
    return flags


def salvage_records(text: str) -> tuple[list[dict], int]:
    """Bóc các bản ghi khỏi đầu ra của mô hình, chịu được đầu ra hỏng.

    Đầu ra có thể cụt vì chạm trần token, có thể kèm lời dẫn hoặc rào mã. Hàm cứu
    từng phần tử thay vì phân tích cú pháp một lần rồi bỏ cuộc. Hàm chỉ bóc vỏ và
    tách bản ghi, không kiểm nội dung.

    Args:
        text: Nội dung thô do mô hình trả về.

    Returns:
        Cặp gồm danh sách bản ghi lấy được và số phần tử hỏng không cứu được.
    """
    if not text:
        return [], 0
    cleaned = _strip_transport(text)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict)], 0
        if isinstance(parsed, dict):
            return [parsed], 0
    except json.JSONDecodeError:
        pass

    records: list[dict] = []
    broken = 0
    depth = 0
    buf: list[str] = []
    in_str = False
    escape = False
    for ch in cleaned:
        if depth:
            buf.append(ch)
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                buf = ["{"]
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads("".join(buf))
                    if isinstance(obj, dict):
                        records.append(obj)
                    else:
                        broken += 1
                except json.JSONDecodeError:
                    broken += 1
                buf = []
    if depth > 0:
        broken += 1
    return records, broken


@dataclass
class BatchResult:
    """Kết quả kiểm một lô đầu ra theo hợp đồng.

    Attributes:
        records: Bản ghi hợp lệ đã chuẩn hoá, khoá là chỉ số bài.
        errors: Mã lỗi của từng bài bị từ chối, khoá là chỉ số bài. Bài bị từ chối
            không có bản ghi và đi vào vòng vá.
        counters: Bộ đếm vỏ truyền tải, phần tử hỏng, chuẩn hoá cơ học và cảnh báo.
    """

    records: dict[int, dict] = field(default_factory=dict)
    errors: dict[int, list[str]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)


def _count_sentences(text: str) -> int:
    """Đếm số câu của một đoạn tóm tắt theo dấu kết câu đứng trước chữ hoa.

    Args:
        text: Chuỗi tóm tắt.

    Returns:
        Số câu ước lượng, tối thiểu 1 khi chuỗi không rỗng.
    """
    return len(_SENTENCE_BREAK.split(text.strip())) if text.strip() else 0


def _is_int(value: Any) -> bool:
    """Kiểm giá trị là số nguyên thật, loại trừ kiểu logic.

    Args:
        value: Giá trị cần kiểm.

    Returns:
        True khi là `int` và không phải `bool`.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def validate_record(rec: dict, paragraphs: list[str],
                    counters: dict[str, int] | None = None,
                    title: str = "") -> tuple[dict | None, list[str]]:
    """Kiểm một bản ghi gọn và chuẩn hoá về dạng chuẩn.

    Chỉ có hai phép chuẩn hoá cơ học: bỏ cặp thực thể và chỉ số `c` trùng, sắp `c`
    tăng dần và `e` theo (thứ tự nhóm, chuỗi). Mọi sai lệch khác bị từ chối kèm mã lỗi.

    Args:
        rec: Bản ghi do mô hình phát.
        paragraphs: Các đoạn `p` của bài trong packet.
        counters: Bộ đếm cộng dồn cho chuẩn hoá và cảnh báo.
        title: Tiêu đề bài, dùng kiểm bảo toàn dấu tiếng Việt.

    Returns:
        Cặp (bản ghi chuẩn hoá hoặc None, danh sách mã lỗi). Danh sách rỗng khi hợp lệ.
    """
    cnt = counters if counters is not None else {}
    errs: list[str] = []

    for key in rec:
        if key not in REQUIRED_KEYS:
            errs.append(f"unknown_key:{key}")
    for key in REQUIRED_KEYS:
        if key not in rec:
            errs.append(f"missing:{key}")
    if errs:
        return None, errs

    entities: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    if not isinstance(rec["e"], list):
        errs.append("type:e")
    else:
        for pair in rec["e"]:
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or not all(isinstance(x, str) for x in pair) or not pair[0].strip()):
                errs.append("shape:e")
                break
            surface, group = pair[0].strip(), pair[1].strip().upper()
            if pair[1] != group or group not in GROUP_CODES:
                errs.append(f"enum:e.group:{pair[1]}")
                break
            key = (surface.lower(), group)
            if key in seen:
                cnt["dedup_entity"] = cnt.get("dedup_entity", 0) + 1
                continue
            seen.add(key)
            entities.append([surface, group])
        entities.sort(key=lambda p: (GROUP_CODES.index(p[1]), p[0]))

    summary = rec["s"]
    if not isinstance(summary, str) or not summary.strip():
        errs.append("type:s")
    elif _count_sentences(summary) > MAX_SUMMARY_SENTENCES:
        cnt["warn_summary_sentences"] = cnt.get("warn_summary_sentences", 0) + 1

    points = rec["k"]
    if not isinstance(points, list) or not all(isinstance(x, str) and x.strip() for x in points):
        errs.append("type:k")
    elif not K_MIN <= len(points) <= K_MAX:
        errs.append(f"count:k:{len(points)}")

    implication = rec["im"]
    if not isinstance(implication, str):
        errs.append("type:im")
    elif len(implication.strip()) < IM_MIN_CHARS:
        errs.append("short:im")

    if rec["sn"] not in SENTIMENT_CODES:
        errs.append(f"enum:sn:{rec['sn']!r}")
    if rec["ts"] not in TIME_CODES:
        errs.append(f"enum:ts:{rec['ts']!r}")

    cited: list[int] = []
    raw_c = rec["c"]
    if not isinstance(raw_c, list) or not all(_is_int(x) for x in raw_c):
        errs.append("type:c")
    else:
        eligible = [n for n, p in enumerate(paragraphs) if len(p) >= MIN_CITATION_CHARS]
        for idx in raw_c:
            if idx not in eligible:
                errs.append(f"range:c:{idx}")
                break
        else:
            cited = sorted(set(raw_c))
            if len(cited) != len(raw_c):
                cnt["dedup_c"] = cnt.get("dedup_c", 0) + 1
            need = min(C_MIN, len(eligible))
            if not need <= len(cited) <= C_MAX:
                errs.append(f"count:c:{len(cited)}")

    if not errs and (has_vietnamese_diacritics(title)
                     or any(has_vietnamese_diacritics(p) for p in paragraphs[:3])):
        if not has_vietnamese_diacritics(summary) and not has_vietnamese_diacritics(implication):
            errs.append("lost_diacritics")

    if errs:
        return None, errs
    return {
        "i": rec["i"],
        "e": entities,
        "s": summary.strip(),
        "k": [x.strip() for x in points],
        "im": implication.strip(),
        "sn": rec["sn"],
        "ts": rec["ts"],
        "c": cited,
    }, []


def parse_and_validate(text: str, packet: dict) -> BatchResult:
    """Bóc và kiểm một lô đầu ra thô theo hợp đồng, dùng chung cho mọi provider.

    Args:
        text: Nội dung thô do provider trả về.
        packet: Packet đã gửi, có khoá `a` là danh sách bài `{"i", "t", "p"}`.

    Returns:
        Kết quả gồm bản ghi hợp lệ theo chỉ số bài, mã lỗi theo bài và bộ đếm.
    """
    result = BatchResult()
    cnt = result.counters
    cnt.update(transport_flags(text))
    raw_records, broken = salvage_records(text)
    cnt["broken"] = broken
    cnt["raw_records"] = len(raw_records)

    articles = {a["i"]: a for a in (packet.get("a") or []) if _is_int(a.get("i"))}
    seen_ids: set[int] = set()
    duplicated: set[int] = set()
    last_i = -1
    for rec in raw_records:
        rid = rec.get("i")
        if not _is_int(rid):
            cnt["no_i"] = cnt.get("no_i", 0) + 1
            continue
        if rid not in articles:
            cnt["unknown_i"] = cnt.get("unknown_i", 0) + 1
            continue
        if rid < last_i:
            cnt["unordered_i"] = cnt.get("unordered_i", 0) + 1
        last_i = max(last_i, rid)
        if rid in seen_ids:
            duplicated.add(rid)
            continue
        seen_ids.add(rid)
        clean, errs = validate_record(rec, articles[rid].get("p") or [], cnt,
                                     articles[rid].get("t") or "")
        if errs:
            result.errors[rid] = errs
        else:
            result.records[rid] = clean

    for rid in duplicated:
        result.records.pop(rid, None)
        result.errors[rid] = ["dup_i"]
    result.records = dict(sorted(result.records.items()))
    return result


def validate_response(text: str, packet_items: list[dict]) -> BatchResult:
    """Bóc và kiểm phản hồi thô của một lượt gọi, cho các runner có sẵn danh sách bài.

    Args:
        text: Nội dung thô do provider trả về.
        packet_items: Danh sách bài `{"i", "t", "p"}` đã gửi.

    Returns:
        Kết quả kiểm lô, xem :func:`parse_and_validate`.
    """
    return parse_and_validate(text, {"a": packet_items})


def result_meta(result: BatchResult) -> dict[str, Any]:
    """Dựng phần meta của hợp đồng để ghi vào tệp meta của lô.

    Args:
        result: Kết quả kiểm lô.

    Returns:
        Từ điển gồm phiên bản hợp đồng, bộ đếm vỏ và chuẩn hoá, danh sách bài bị từ chối.
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "transport": result.counters,
        "domain_errors": [f"i={i}: {','.join(codes)}" for i, codes in sorted(result.errors.items())],
    }


def build_user_message(task_text: str) -> str:
    """Dựng tin nhắn người dùng gửi cho mọi provider từ nội dung tệp packet.

    Mọi provider nhận đúng byte của tệp packet, không thêm tiêu đề và không đóng
    gói lại, để cùng một bài luôn đi vào mô hình theo cùng một dạng.

    Args:
        task_text: Nội dung nguyên văn của tệp `.task.json`.

    Returns:
        Chuỗi gửi làm tin nhắn người dùng.
    """
    return task_text


def request_meta(provider: str, model: str, *, sampling: dict[str, Any],
                 prefix_sha256: str = "") -> dict[str, Any]:
    """Dựng phần meta mô tả lượt gọi để ghi vào tệp meta của lô.

    Args:
        provider: Tên provider (`agy`, `openrouter`, `opencode-native`, `dsh`).
        model: Tên mô hình đã dùng.
        sampling: Tham số lấy mẫu thực tế đã gửi, hoặc giá trị `unsupported`.
        prefix_sha256: Băm SHA256 của prefix hệ thống đã gửi.

    Returns:
        Từ điển các khoá nhà cung cấp, mô hình, tham số và băm prefix.
    """
    return {
        "agent_provider": provider,
        "model_used": model,
        "sampling": sampling,
        "prefix_sha256": prefix_sha256,
    }
