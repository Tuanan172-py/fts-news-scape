"""Define the size and integrity checks of the static prefix sent to workers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from src.core.paths import PROJECT_ROOT, REPO_ROOT

# The generator, packer, ledger and radar share the definitions below:
#   persona_tokens: the part the project generates and pastes into the preset.
#   SYSTEM_OVERHEAD_TOKENS: the part the harness always adds around the persona. It is
#   static and byte-identical between turns, so it is cached and must be in the estimate.
# Invariant: the `persona` in the preset must equal the generated prefix file byte for
# byte. A single whitespace difference makes every following token miss the cache with
# no visible signal, and the bill grows about 50 times on the part that should be cheap.

PREFIX_DIR = PROJECT_ROOT / "assets" / "prefix"
PREFIX_PATH = PREFIX_DIR / "ARTICLE_SYSTEM_CORE.md"
PREFIX_META = PREFIX_DIR / "ARTICLE_SYSTEM_CORE.meta.json"

PRESET_PATH = (REPO_ROOT / ".agents" / "dsh" / "presets" / "news-scape-conductor"
               / "agent.cordis.yml")
WORKER_ROW_ID = "tool-subagent-article"

# Characters-to-tokens ratio, shared with `src/agent/packet/distill.py`.
CHARS_PER_TOKEN = 3

# Fallback used before a prefix is generated. It is not a quota; it only keeps the
# estimate above zero before the first generation.
DEFAULT_PERSONA_TOKENS = 6400

# Static part that the harness adds to every worker request and the project cannot remove:
#
#   AGENTS.md reloaded for every agent, children included   ~4,069 tokens   (plan §4.2 R2)
#   sections `tools:ptc-only` + `tools:sdk`                   ~640 tokens   (plan §4.2 R3)
#   harness identity + persona suffix                          ~90 tokens
#
# All three precede the packet and do not change between turns, so they hit the cache like
# the persona. They are included in the estimate so `est_hit` is comparable with the real
# `cacheReadTokens`.
SYSTEM_OVERHEAD_TOKENS = 4_800


class _LenientLoader(yaml.SafeLoader):
    """YAML loader that ignores composition-specific tags instead of raising.

    DSH presets use the `!!js` tag for some conditional fields. `yaml.safe_load` rejects
    them, and only the `persona` string is needed here, so every unknown tag loads as `None`.
    """


_LenientLoader.add_multi_constructor(
    None, lambda loader, suffix, node: None)


def read_meta() -> dict:
    """Read the metadata of the prefix currently on disk.

    Returns:
        Metadata dict, or an empty dict if no prefix is generated or the file is corrupt.
    """
    try:
        with open(PREFIX_META, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def prefix_hash() -> str | None:
    """Return the hash of the prefix in use.

    Returns:
        Hash string, or None if no prefix is generated.
    """
    return read_meta().get("hash")


def prefix_variants() -> dict:
    """Return the variants enabled when the prefix on disk was generated.

    Variants are recorded so the check mode rebuilds exactly that content. Without them,
    a prefix generated with the ticker digest is reported as a catalog mismatch on every
    check even though it is correct.

    Returns:
        Variant dict, empty when the prefix has the default form.
    """
    variants = read_meta().get("variants")
    return variants if isinstance(variants, dict) else {}


def persona_tokens() -> int:
    """Return the size of the persona part of the prefix.

    Returns:
        Estimated persona token count, or the default when no prefix is generated.
    """
    try:
        return int(read_meta().get("approx_tokens") or DEFAULT_PERSONA_TOKENS)
    except (TypeError, ValueError):
        return DEFAULT_PERSONA_TOKENS


def cached_prefix_tokens() -> int:
    """Return the total static tokens that precede the packet in each worker request.

    Compare this figure with the real `cacheReadTokens`: from the second call on, each
    call should read about this many tokens at the cache-hit price.

    Returns:
        Persona tokens plus the harness overhead.
    """
    return persona_tokens() + SYSTEM_OVERHEAD_TOKENS


def persona_from_preset(path: str | Path | None = None,
                        row_id: str = WORKER_ROW_ID) -> str | None:
    """Extract the `persona` string of a subagent row from the preset.

    Args:
        path: Preset file path; defaults to the project preset.
        row_id: Identifier of the row to extract.

    Returns:
        Persona text, or None if the file or row is missing or the row declares no persona.
    """
    p = Path(path) if path else PRESET_PATH
    try:
        doc = yaml.load(p.read_text(encoding="utf-8"), Loader=_LenientLoader)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(doc, list):
        return None
    for row in doc:
        if isinstance(row, dict) and row.get("id") == row_id:
            persona = (row.get("config") or {}).get("persona")
            return persona if isinstance(persona, str) else None
    return None


def digest(content: str) -> str:
    """Compute the short hash of a prefix content.

    Args:
        content: Full prefix text.

    Returns:
        First sixteen characters of the SHA256 hex digest.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def compare_persona(content: str, path: str | Path | None = None) -> tuple[bool, str]:
    """Compare the persona in the preset with the canonical prefix content.

    The comparison strips leading and trailing whitespace because the YAML loader always
    normalizes the trailing newline of a block. Any inner difference counts as a mismatch.

    Args:
        content: Canonical prefix content, usually freshly generated from the catalog.
        path: Preset path; defaults to the project preset.

    Returns:
        Pair of the match result and a description line to print for the operator.
    """
    persona = persona_from_preset(path)
    if persona is None:
        return False, (f"không đọc được `persona` của row `{WORKER_ROW_ID}` trong "
                       f"{Path(path) if path else PRESET_PATH}")
    if persona.strip() == content.strip():
        return True, f"persona khớp prefix ({len(persona):,} ký tự)"

    a = persona.strip().splitlines()
    b = content.strip().splitlines()
    if len(a) != len(b):
        return False, (f"persona {len(a)} dòng so với prefix {len(b)} dòng "
                       f"({len(persona):,} so với {len(content):,} ký tự)")
    for i, (x, y) in enumerate(zip(a, b), start=1):
        if x != y:
            return False, (f"lệch từ dòng {i}:\n"
                           f"    preset : {x[:90]}\n"
                           f"    prefix : {y[:90]}")
    return False, "lệch ở khoảng trắng đầu hoặc cuối khối"
