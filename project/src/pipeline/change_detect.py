"""Detect article content and DOM structure changes by fingerprinting (SimHash64, DOM path signature) and classifying states NEW, UNCHANGED, CONTENT_CHANGED, TEMPLATE_DRIFT and SELECTOR_BROKEN."""

from __future__ import annotations

import hashlib
import re

_MASK64 = (1 << 64) - 1
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _token_hash64(token: str) -> int:
    """Hash a keyword token into a 64-bit integer with Blake2b."""
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(),
                          "big")


def simhash64(text: str) -> int:
    """Compute the 64-bit SimHash signature of a text.

    Args:
        text: Text content to hash for similarity.

    Returns:
        64-bit integer fingerprint of the content (0 for empty text).
    """
    if not text:
        return 0
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return 0
    vote = [0] * 64
    for tok in tokens:
        h = _token_hash64(tok)
        for i in range(64):
            vote[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if vote[i] > 0:
            out |= (1 << i)
    return out & _MASK64


def hamming64(a: int, b: int) -> int:
    """Compute the Hamming distance (number of differing bits) between two 64-bit signatures.

    Args:
        a: First 64-bit integer.
        b: Second 64-bit integer.

    Returns:
        Number of bits that differ between a and b.
    """
    return bin((a ^ b) & _MASK64).count("1")


def dom_path_sig(structure: dict) -> str:
    """Build an order-independent DOM structure signature from Silver structure metadata.

    Args:
        structure: Dict of structure components (headings, paragraphs, tables, links).

    Returns:
        12-character SHA-1 digest of the DOM structure, or an empty string when there is
        no structure.
    """
    if not structure:
        return ""
    headings = structure.get("headings", [])
    paragraphs = structure.get("paragraphs", [])
    tables = structure.get("tables", [])
    links = structure.get("links", [])
    if not headings and not paragraphs and not tables:
        return ""
    heads = sorted(f"h{h.get('level')}" for h in headings)

    def bucket(n: int) -> int:
        return n.bit_length()

    parts = [
        "H:" + ",".join(heads),
        f"P:{bucket(len(paragraphs))}",
        f"T:{bucket(len(tables))}",
        f"L:{bucket(len(links))}",
    ]
    joined = "|".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def fingerprint(cleaned_text: str, structure: dict, *,
                content_sha256: str, capture_status: str, missing: list | None) -> dict:
    """Assemble the content fingerprint set and selector status for one capture.

    Args:
        cleaned_text: Clean text after extraction.
        structure: DOM component structure of the article.
        content_sha256: SHA-256 hash of the raw Bronze content.
        capture_status: Capture status ('ok', 'partial', 'failed').
        missing: Components missing from the capture.

    Returns:
        Dict of fingerprint values and the selector check flag.
    """
    missing = missing or []
    selector_ok = capture_status in ("ok", "partial") \
        and "main_content_node" not in missing \
        and "incomplete_render" not in missing
    return {
        "content_sha256": content_sha256,
        "simhash64": format(simhash64(cleaned_text), "016x"),
        "dom_path_sig": dom_path_sig(structure),
        "capture_status": capture_status,
        "selector_ok": selector_ok,
    }


def classify(prev: dict | None, cur: dict, *,
             t_content: int = 6, t_template: int = 12) -> tuple[str, str]:
    """Classify the change state by comparing two consecutive fingerprints.

    Args:
        prev: Fingerprint of the previous version, or None for a new article.
        cur: Fingerprint of the current version.
        t_content: Content distance threshold (reserved parameter).
        t_template: Layout structure distance threshold (reserved parameter).

    Returns:
        Tuple of the state code ('NEW', 'UNCHANGED', 'CONTENT_CHANGED',
        'TEMPLATE_DRIFT', 'SELECTOR_BROKEN') and the recommended action ('skip',
        're_extract', 'manual_review').
    """
    if not cur.get("selector_ok", True):
        return "SELECTOR_BROKEN", "manual_review"

    if prev is None:
        return "NEW", "re_extract"

    if prev.get("content_sha256") and prev["content_sha256"] == cur["content_sha256"]:
        return "UNCHANGED", "skip"

    dom_changed = bool(prev.get("dom_path_sig")) and bool(cur.get("dom_path_sig")) \
        and prev["dom_path_sig"] != cur["dom_path_sig"]
    if dom_changed:
        return "TEMPLATE_DRIFT", "manual_review"
    return "CONTENT_CHANGED", "re_extract"
