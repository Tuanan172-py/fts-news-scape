"""Define the article-processor output contract: constants, envelope unwrapping and validation shared by all providers."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "article-compact-v2.schema.json"
CONTRACT_VERSION = "article-compact-v2"


def _load_schema() -> dict:
    """Load the compact record schema from the source-of-truth file.

    Returns:
        JSON Schema dict of the compact record.
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

# Standard sampling parameters (ADR 0017 D5). A provider that does not support a
# parameter records `unsupported` in the meta instead of changing the value.
SAMPLING = {"temperature": 0, "seed": 20261005}

MIN_CITATION_CHARS = 20
MAX_SUMMARY_SENTENCES = 3

# Source of `l1_outputs` records written by the deterministic catalog lookup (ADR 0003).
# These records are for comparison only and never count as analyzed (ADR 0010 D4).
CODE_FIRST_SOURCE = "code_first"


def not_code_first_sql(alias: str = "") -> str:
    """Build the SQL condition that excludes code-first rows from `l1_outputs` and keeps DoD failures.

    Args:
        alias: Alias of the `l1_outputs` table in the query; empty when no alias is used.

    Returns:
        SQL expression usable in a WHERE or ON clause.
    """
    p = f"{alias}." if alias else ""
    return f"COALESCE({p}l1_source, 'agent') <> '{CODE_FIRST_SOURCE}'"


def not_code_first_sql_for(conn: Any, alias: str = "") -> str:
    """Build the code-first exclusion condition for the real schema of a connection.

    An old database without the `l1_source` column cannot hold code-first rows, so the
    condition is a constant true. Used for read-only connections that cannot run the
    schema upgrade.

    Args:
        conn: SQLite connection.
        alias: Alias of the `l1_outputs` table in the query; empty when no alias is used.

    Returns:
        SQL expression usable in a WHERE or ON clause.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(l1_outputs)")}
    return not_code_first_sql(alias) if "l1_source" in cols else "1 = 1"


def analyzed_l1_sql(alias: str = "") -> str:
    """Build the SQL condition "article analyzed by the model" on `l1_outputs`.

    The condition requires a record that passed DoD and excludes code-first rows. Every
    query that counts, selects, delivers or exports from `l1_outputs` shares this
    condition so the definition does not diverge between paths.

    Args:
        alias: Alias of the `l1_outputs` table in the query; empty when no alias is used.

    Returns:
        SQL expression usable in a WHERE or ON clause.
    """
    p = f"{alias}." if alias else ""
    return f"{p}dod_pass = 1 AND {not_code_first_sql(alias)}"

SENTIMENT_MAP = {"pos": "positive", "neg": "negative", "neu": "neutral"}
TIME_MAP = {"urg": "urgent", "today": "today", "week": "this_week",
            "month": "this_month", "arch": "archive"}

_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ỸĐ])")
_VIETNAMESE_DIACRITICS_RE = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


def has_vietnamese_diacritics(text: str) -> bool:
    """Check whether a string has at least one accented Vietnamese character.

    Args:
        text: String to check.

    Returns:
        True if an accented character is present.
    """
    return bool(_VIETNAMESE_DIACRITICS_RE.search(text or ""))


def unwrap_tool_envelope(text: str) -> str:
    """Unwrap the DSH tool result envelope to get the text the model returned.

    The DSH agent-call tool returns `{"kind":..., "runId":..., "output":[{"type":
    "text","text":"..."}]}`. If that object is written to disk as is, the record parser
    reads the envelope as a junk record with the two fields `type` and `text`.

    Args:
        text: Raw content of the output file.

    Returns:
        Text returned by the model, or the input unchanged when there is no envelope.
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
    """Strip the transport wrapper: vendor envelope, code fence and prose before the JSON array.

    Args:
        text: Raw content returned by the model.

    Returns:
        String that starts at the first `[` when prose precedes it.
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
    """Count the transport wrapper kinds present in the raw output.

    Args:
        text: Raw content returned by the model.

    Returns:
        Counters `envelope`, `fence` and `prose_prefix`, each 0 or 1.
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
    """Extract records from model output, tolerating damaged output.

    The output can be truncated at the token ceiling or carry prose or a code fence. The
    function salvages element by element instead of parsing once and giving up. It only
    unwraps and splits records and does not validate content.

    Args:
        text: Raw content returned by the model.

    Returns:
        Pair of the records recovered and the count of damaged elements that could not be saved.
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
    """Validation result of one output batch against the contract.

    Attributes:
        records: Valid normalized records keyed by article index.
        errors: Error codes of each rejected article keyed by article index. A rejected
            article has no record and enters the repair round.
        counters: Counters for transport wrappers, damaged elements, mechanical
            normalization and warnings.
    """

    records: dict[int, dict] = field(default_factory=dict)
    errors: dict[int, list[str]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)


def _count_sentences(text: str) -> int:
    """Count the sentences of a summary by sentence-ending marks followed by a capital letter.

    Args:
        text: Summary string.

    Returns:
        Estimated sentence count, at least 1 for a non-empty string.
    """
    return len(_SENTENCE_BREAK.split(text.strip())) if text.strip() else 0


def _is_int(value: Any) -> bool:
    """Check that a value is a real integer, excluding booleans.

    Args:
        value: Value to check.

    Returns:
        True if the value is an `int` and not a `bool`.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def validate_record(rec: dict, paragraphs: list[str],
                    counters: dict[str, int] | None = None,
                    title: str = "") -> tuple[dict | None, list[str]]:
    """Validate a compact record and normalize it to the standard form.

    Only two mechanical normalizations apply: remove duplicate entity pairs and duplicate
    `c` indexes, sort `c` ascending and `e` by (group order, string). Any other deviation
    is rejected with an error code.

    Args:
        rec: Record emitted by the model.
        paragraphs: Paragraphs `p` of the article in the packet.
        counters: Accumulating counters for normalization and warnings.
        title: Article title, used to check that Vietnamese diacritics are preserved.

    Returns:
        Pair of the normalized record (or None) and the list of error codes; the list is empty when valid.
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
    """Unwrap and validate a raw output batch against the contract, for all providers.

    Args:
        text: Raw content returned by the provider.
        packet: Packet that was sent; key `a` is the article list `{"i", "t", "p"}`.

    Returns:
        Result with valid records by article index, error codes by article and counters.
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
    """Unwrap and validate the raw response of one call, for runners that already hold the article list.

    Args:
        text: Raw content returned by the provider.
        packet_items: Articles `{"i", "t", "p"}` that were sent.

    Returns:
        Batch validation result, see :func:`parse_and_validate`.
    """
    return parse_and_validate(text, {"a": packet_items})


def result_meta(result: BatchResult) -> dict[str, Any]:
    """Build the contract part of the meta written to the batch meta file.

    Args:
        result: Batch validation result.

    Returns:
        Dict with the contract version, wrapper and normalization counters, and the rejected articles.
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "transport": result.counters,
        "domain_errors": [f"i={i}: {','.join(codes)}" for i, codes in sorted(result.errors.items())],
    }


def build_user_message(task_text: str) -> str:
    """Build the user message sent to every provider from the packet file content.

    Every provider receives the exact bytes of the packet file, with no added header and
    no repackaging, so the same article always reaches the model in the same form.

    Args:
        task_text: Verbatim content of the `.task.json` file.

    Returns:
        String sent as the user message.
    """
    return task_text


def request_meta(provider: str, model: str, *, sampling: dict[str, Any],
                 prefix_sha256: str = "") -> dict[str, Any]:
    """Build the meta part that describes the call, written to the batch meta file.

    Args:
        provider: Provider name (`agy`, `openrouter`, `opencode-native`, `dsh`).
        model: Model name used.
        sampling: Sampling parameters actually sent, or the value `unsupported`.
        prefix_sha256: SHA256 hash of the system prefix that was sent.

    Returns:
        Dict with the provider, model, sampling parameters and prefix hash.
    """
    return {
        "agent_provider": provider,
        "model_used": model,
        "sampling": sampling,
        "prefix_sha256": prefix_sha256,
    }
