"""Extract and normalize the financial entity catalog from source data."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path


try:
    import pandas as pd
except ImportError:
    pd = None

from src.agent.catalog.entities import GENERIC_ALIAS_STOPLIST, _fold
from src.core import paths
from src.core.stdio import force_utf8_stdio
from src.core.paths import PROJECT_ROOT, REPO_ROOT
force_utf8_stdio()


# ----------------------------------------------------------------------------
# Default path configuration
# ----------------------------------------------------------------------------
# Priority order: the FRA_DATA_ROOT environment variable, the current user's
# synced SharePoint folder, then the folder next to the repository.
_POSSIBLE_DATA_ROOTS = [
    *([Path(os.environ["FRA_DATA_ROOT"])] if os.environ.get("FRA_DATA_ROOT") else []),
    Path.home() / "OneDrive - fpts.com.vn" / "FRA - Data",
    REPO_ROOT / "FRA - Data",
]
DEFAULT_DATA_ROOT = next((p for p in _POSSIBLE_DATA_ROOTS if p.exists()), _POSSIBLE_DATA_ROOTS[0])
DEFAULT_OUT = paths.entities_dir()
ALIASES_DIR = PROJECT_ROOT / "config" / "entities" / "aliases"
USERS_DIR = PROJECT_ROOT / "config" / "entities" / "users"

SCHEMA_VERSION = "1.2.0"



# ----------------------------------------------------------------------------
# Data reading (parquet on OneDrive must be read through BytesIO to avoid Errno 22)
# ----------------------------------------------------------------------------
def read_parquet(path: Path) -> pd.DataFrame:
    """Read a parquet file through an in-memory buffer.

    Args:
        path: Parquet file path.

    Returns:
        The loaded DataFrame.
    """
    with open(path, "rb") as f:
        return pd.read_parquet(io.BytesIO(f.read()))


def read_excel(path: Path, **kw) -> pd.DataFrame:
    """Read an Excel workbook.

    Args:
        path: Workbook path.
        **kw: Keyword arguments forwarded to `pandas.read_excel`.

    Returns:
        The loaded DataFrame.
    """
    return pd.read_excel(path, **kw)


def _load_user_watchlist_tickers(users_dir: Path) -> set[str]:
    """Load the set of tickers users registered in config/entities/users/."""
    out: set[str] = set()
    if not users_dir.exists():
        return out
    try:
        import yaml
        for f in users_dir.glob("*.yaml"):
            cfg = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            out.update(str(x).strip().upper() for x in cfg.get("tickers", []))
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------
# Name normalization and alias generation (surface forms for recognition in news)
# ----------------------------------------------------------------------------
# Common legal prefixes at the start of Vietnamese company names, stripped to get the short name.
_LEGAL_PREFIXES = [
    r"Tổng\s+Công\s+ty\s+Cổ\s+phần",
    r"Tổng\s+CTCP",
    r"Tổng\s+Công\s+ty",
    r"Ngân\s+hàng\s+Thương\s+mại\s+Cổ\s+phần",
    r"Ngân\s+hàng\s+TMCP",
    r"Công\s+ty\s+Cổ\s+phần",
    r"CTCP",
    r"Công\s+ty\s+TNHH\s+MTV",
    r"Công\s+ty\s+TNHH\s+Một\s+Thành\s+Viên",
    r"Công\s+ty\s+TNHH",
    r"Chứng\s+chỉ\s+Quỹ\s+ETF",
    r"Chứng\s+chỉ\s+Quỹ",
    r"Quỹ\s+Đầu\s+tư",
    r"Quỹ\s+ETF",
    r"Quỹ",
]
_PREFIX_RE = re.compile(r"^(?:%s)\b[\s:.-]*" % "|".join(_LEGAL_PREFIXES), re.IGNORECASE)
# Legal suffix: "... - CTCP", "... - Công ty Cổ phần"
_SUFFIX_RE = re.compile(r"[\s]*[-–]\s*(?:CTCP|Công\s+ty\s+Cổ\s+phần)\s*$", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(([^)]+)\)")
_WS_RE = re.compile(r"\s+")


def clean_name(name: str) -> str:
    """Trim a name and collapse internal whitespace.

    Args:
        name: Raw name.

    Returns:
        The name with single spaces only.
    """
    return _WS_RE.sub(" ", str(name).strip())


def short_name(name: str) -> str:
    """Extract the brand core by dropping parentheses, legal prefix and legal suffix.

    Example: `Tập đoàn X - CTCP` becomes `X`.

    Args:
        name: Full company name.

    Returns:
        The short brand name, or the cleaned full name when nothing remains.
    """
    s = _WS_RE.sub(" ", _PAREN_RE.sub("", clean_name(name))).strip()
    for _ in range(2):
        new = _PREFIX_RE.sub("", s).strip()
        if new == s:
            break
        s = new
    s = re.sub(r"^Tập\s+đoàn\b[\s:.-]*", "", s, flags=re.IGNORECASE).strip()
    s = _SUFFIX_RE.sub("", s).strip()
    s = re.sub(r"[\s\-–]+$", "", s).strip()
    return s or clean_name(name)


def make_aliases(canonical: str, code: str, brand_map: dict | None = None) -> list[str]:
    """Build the ordered, unique surface forms of an entity.

    Order: full name, short name, parenthesized brand, then manually maintained brand
    aliases (brand_aliases.yaml).

    Auto-generated aliases (short name and parenthesized strings) are filtered through
    GENERIC_ALIAS_STOPLIST: Vietnamese legal names often contain place names or generic
    suffixes, and "(Việt Nam)" was once injected as an alias of TICKER:IVS, which made
    that ticker match 164 articles, the worst false top-1 in the system. The full name
    and editor-supplied aliases (brand_map) are deliberately not filtered.

    Args:
        canonical: Canonical full name.
        code: Entity code, used to look up manual brand aliases.
        brand_map: Mapping from code to manual brand aliases.

    Returns:
        Aliases in order, without duplicates.
    """
    out: list[str] = []

    def add(x: str, *, filtered: bool = False) -> None:
        x = clean_name(x)
        if not x or x in out or x.isdigit() or len(x) < 2:
            return
        if filtered and _fold(x) in GENERIC_ALIAS_STOPLIST:
            return
        out.append(x)

    add(clean_name(canonical))
    add(short_name(canonical), filtered=True)
    for m in _PAREN_RE.findall(str(canonical)):   # parenthesized brand, e.g. (CHOLIMEX)
        add(m, filtered=True)
    for b in (brand_map or {}).get(code, []):     # manual brands, e.g. (Vietcombank), (BIDV)
        add(b)
    return out


# ----------------------------------------------------------------------------
# Code classification: STOCK / ETF / FUND-OTHER
# ----------------------------------------------------------------------------
def classify_code(code: str, etf_codes: set[str]) -> str:
    """Classify a security code as ETF, STOCK or OTHER.

    Args:
        code: Security code.
        etf_codes: Codes known to be ETFs.

    Returns:
        One of `ETF`, `STOCK`, `OTHER`.
    """
    if code in etf_codes or code.startswith(("E1", "FUE", "FUC")):
        return "ETF"
    # Vietnamese stock code = 3 chars [A-Z0-9] starting with a letter (e.g. HPG, A32, C32, L14).
    if re.fullmatch(r"[A-Z][A-Z0-9]{2}", code):
        return "STOCK"
    # Everything else (closed-end funds, bonds, warrants) is OTHER.
    return "OTHER"


# ----------------------------------------------------------------------------
# Static mappings: exchanges and indices
# ----------------------------------------------------------------------------
EXCHANGES = [
    {"code": "HOSE", "name": "Sở Giao dịch Chứng khoán TP. Hồ Chí Minh",
     "aliases": ["HOSE", "HSX", "Sở GDCK TP.HCM", "sàn HOSE", "sàn TP.HCM"]},
    {"code": "HNX", "name": "Sở Giao dịch Chứng khoán Hà Nội",
     "aliases": ["HNX", "Sở GDCK Hà Nội", "sàn Hà Nội"]},
    {"code": "UPCOM", "name": "Thị trường giao dịch cổ phiếu công ty đại chúng chưa niêm yết",
     "aliases": ["UPCOM", "UPCoM", "sàn UPCoM"]},
]

INDEX_META = {
    "VNINDEX":  {"name": "VN-Index",       "aliases": ["VN-Index", "VNINDEX", "VN Index"], "exchange": "HOSE"},
    "VN30":     {"name": "VN30-Index",     "aliases": ["VN30", "VN30-Index", "rổ VN30"],   "exchange": "HOSE"},
    "VNXALL":   {"name": "VNX Allshare",   "aliases": ["VNXALL", "VNX Allshare", "VNX-Allshare"], "exchange": "HOSE"},
    "HNXINDEX": {"name": "HNX-Index",      "aliases": ["HNX-Index", "HNXINDEX", "HNX Index"], "exchange": "HNX"},
    "HNX30":    {"name": "HNX30-Index",    "aliases": ["HNX30", "HNX30-Index", "rổ HNX30"], "exchange": "HNX"},
    "UPINDEX":  {"name": "UPCoM-Index",    "aliases": ["UPCoM-Index", "UPINDEX", "UPCOM-Index"], "exchange": "UPCOM"},
}

def _fold_diacritics(s: str) -> str:
    """Strip Vietnamese diacritics, e.g. `Bất động sản` becomes `Bat dong san`."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def slug(s: str) -> str:
    """Convert text to an upper-case ASCII slug joined by underscores.

    Args:
        s: Input text.

    Returns:
        The slug, e.g. `BAT_DONG_SAN`.
    """
    s = _fold_diacritics(str(s))
    s = re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_")
    return s.upper()


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_all_domain_aliases() -> dict:
    """Load all aliases from config/entities/aliases/ (falling back to brand_aliases.yaml)."""
    aliases_dir = ALIASES_DIR
    res = {
        "tickers": {},
        "industries": {},
        "nations": {},
        "themes": {},
        "assets": {},
        "institutions": {},
    }
    # Tickers
    t_path = aliases_dir / "tickers.yaml"
    if not t_path.exists():
        t_path = aliases_dir.parent / "brand_aliases.yaml"
    raw_tickers = _load_yaml(t_path)
    res["tickers"] = {str(k).strip(): list(v or []) for k, v in raw_tickers.items()}

    # Industries
    raw_ind = _load_yaml(aliases_dir / "industries.yaml")
    res["industries"] = {str(k).strip(): list(v or []) for k, v in raw_ind.items()}

    # Nations (geopolitics / countries)
    raw_nations = _load_yaml(aliases_dir / "nations.yaml")
    if not raw_nations:
        # Fallback macro_geo
        raw_macro = _load_yaml(aliases_dir / "macro_geo.yaml")
        macro_themes = {"LAI_SUAT", "TY_GIA", "LAM_PHAT", "THUE_THUONG_MAI"}
        raw_nations = {k: v for k, v in raw_macro.items() if k not in macro_themes}
    res["nations"] = raw_nations

    # Themes (macro themes)
    raw_themes = _load_yaml(aliases_dir / "themes.yaml")
    if not raw_themes:
        # Fallback macro_geo
        raw_macro = _load_yaml(aliases_dir / "macro_geo.yaml")
        macro_themes = {"LAI_SUAT", "TY_GIA", "LAM_PHAT", "THUE_THUONG_MAI"}
        raw_themes = {k: v for k, v in raw_macro.items() if k in macro_themes}
    res["themes"] = raw_themes

    # Assets
    res["assets"] = _load_yaml(aliases_dir / "assets.yaml")

    # Institutions
    res["institutions"] = _load_yaml(aliases_dir / "institutions.yaml")

    return res



# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------
def build(data_root: Path, out_dir: Path) -> dict:
    """Build the entity catalog and write all output files.

    Args:
        data_root: Root of the FRA data folder.
        out_dir: Directory that receives the generated files.

    Returns:
        The statistics dict also written to `stats.json`.
    """
    td = data_root / "trading_data"
    cd = data_root / "company_data"
    ic = data_root / "industry_classification"

    all_domain_aliases = _load_all_domain_aliases()
    brand_map = all_domain_aliases["tickers"]
    ind_aliases = all_domain_aliases["industries"]

    comp = read_excel(cd / "company_name.xlsx")
    etf = read_excel(cd / "etf_name.xlsx")
    mc = read_parquet(td / "market_caps.parquet")
    osx = read_excel(td / "os.xlsx")
    idx = read_parquet(td / "indices.parquet")
    ind = read_excel(ic / "industry_classification.xlsx")

    comp_name = {str(r.Code).strip(): clean_name(r.Name) for r in comp.itertuples()}
    etf_name = {str(r.Code).strip(): clean_name(r.Name) for r in etf.itertuples()}
    etf_codes = set(etf_name)

    mc_codes = set(mc.Ticker.astype(str).str.strip())
    os_codes = set(osx.Ticker.astype(str).str.strip())
    ind_codes = set(ind.ticker.astype(str).str.strip())

    # Latest GICS per ticker
    ind = ind.copy()
    ind["date"] = pd.to_datetime(ind["date"])
    latest = ind.sort_values("date").groupby("ticker").tail(1)
    gics = {
        str(r.ticker).strip(): (
            clean_name(r.GICS1_name), clean_name(r.GICS2_name), clean_name(r.GICS3_name)
        )
        for r in latest.itertuples()
    }

    # Latest OS (shares outstanding) per ticker
    osx = osx.copy()
    osx["Date"] = pd.to_datetime(osx["Date"])
    os_latest = osx.sort_values("Date").groupby("Ticker").tail(1)
    os_map = {str(r.Ticker).strip(): int(r.OS) for r in os_latest.itertuples() if pd.notna(r.OS)}

    # Latest market cap and activity date per ticker (from market_caps.parquet)
    mc_copy = mc.copy()
    mc_copy["Date"] = pd.to_datetime(mc_copy["Date"])
    mc_latest = mc_copy.sort_values("Date").groupby("Ticker").tail(1)
    mc_meta: dict[str, dict] = {}
    for r in mc_latest.itertuples():
        ticker_str = str(r.Ticker).strip()
        cap_val = float(r.Market_caps) if pd.notna(r.Market_caps) else 0.0
        date_str = str(r.Date)[:10]
        year_val = int(r.Date.year)
        mc_meta[ticker_str] = {
            "year": year_val,
            "market_cap_bil": round(cap_val / 1e9, 2),
            "latest_date": date_str,
        }

    user_tickers = _load_user_watchlist_tickers(USERS_DIR)

    entities: list[dict] = []

    # --- 1) SECURITIES: stocks / ETFs / other (union of every source with a code) ---
    all_codes = set(comp_name) | mc_codes | os_codes | ind_codes | etf_codes
    for code in sorted(all_codes):
        kind = classify_code(code, etf_codes)
        name = etf_name.get(code) or comp_name.get(code)
        if kind == "ETF":
            etype = "ETF"
            canonical = name or code
        elif kind == "STOCK":
            etype = "TICKER"
            canonical = name or code
        else:
            etype = "SECURITY_OTHER"
            canonical = name or code

        g = gics.get(code)
        attrs: dict = {}
        if g:
            attrs["gics1"], attrs["gics2"], attrs["gics3"] = g
        if code in os_map:
            attrs["shares_outstanding"] = os_map[code]
        attrs["has_market_cap"] = code in mc_codes
        attrs["listed_universe"] = True

        if etype == "TICKER":
            meta = mc_meta.get(code, {})
            mc_year = meta.get("year", 0)
            mc_bil = meta.get("market_cap_bil", 0.0)
            latest_date = meta.get("latest_date")
            is_active = (mc_year >= 2025)
            in_user = (code in user_tickers)

            if in_user or (is_active and mc_bil >= 300.0):
                tier = 1
            elif is_active and mc_bil >= 100.0:
                tier = 2
            else:
                tier = 3

            attrs["tier"] = tier
            attrs["is_active"] = is_active
            attrs["market_cap_bil"] = mc_bil
            if latest_date:
                attrs["latest_date"] = latest_date
            if in_user:
                attrs["in_user_watchlist"] = True
        else:
            attrs["tier"] = 1
            attrs["is_active"] = True

        ent = {
            "entity_id": f"{etype}:{code}",
            "type": etype,
            "code": code,
            "canonical_name": canonical,
            "aliases": make_aliases(canonical, code, brand_map) if (name or code in brand_map) else [],
            "attributes": attrs,
            "sources": _sources_for(code, comp_name, etf_codes, mc_codes, os_codes, gics),
        }
        entities.append(ent)

    # --- 2) INDEX ------------------------------------------------------------
    for code in sorted(set(idx.Ticker.astype(str).str.strip())):
        meta = INDEX_META.get(code, {"name": code, "aliases": [code], "exchange": None})
        entities.append({
            "entity_id": f"INDEX:{code}",
            "type": "INDEX",
            "code": code,
            "canonical_name": meta["name"],
            "aliases": meta["aliases"],
            "attributes": {"exchange": meta["exchange"]},
            "sources": ["trading_data/indices.parquet"],
        })

    # --- 3) EXCHANGE ---------------------------------------------------------
    for ex in EXCHANGES:
        entities.append({
            "entity_id": f"EXCHANGE:{ex['code']}",
            "type": "EXCHANGE",
            "code": ex["code"],
            "canonical_name": ex["name"],
            "aliases": ex["aliases"],
            "attributes": {},
            "sources": ["static/derived"],
        })

    # --- 4) INDUSTRY: three GICS levels -------------------------------------
    g1 = latest.groupby("GICS1_name").ticker.nunique()
    for name, n in g1.items():
        entities.append(_industry("GICS1", name, None, int(n), ind_aliases))
    g2 = latest.groupby(["GICS1_name", "GICS2_name"]).ticker.nunique()
    for (p1, name), n in g2.items():
        entities.append(_industry("GICS2", name, clean_name(p1), int(n), ind_aliases))
    g3 = latest.groupby(["GICS2_name", "GICS3_name"]).ticker.nunique()
    for (p2, name), n in g3.items():
        entities.append(_industry("GICS3", name, clean_name(p2), int(n), ind_aliases))

    # --- 5) MACRO_GEO (Nations / Geopolitics) --------------------------------
    for code, info in all_domain_aliases["nations"].items():
        canonical = info.get("canonical_name", code)
        aliases = list(info.get("aliases", [canonical]))
        entities.append({
            "entity_id": f"MACRO_GEO:{code}",
            "type": "MACRO_GEO",
            "code": code,
            "canonical_name": canonical,
            "aliases": aliases,
            "attributes": {"category": "macro_geo"},
            "sources": ["config/entities/aliases/nations.yaml"],
        })

    # --- 6) MACRO_THEME (macro and economic themes) -------------------------
    for code, info in all_domain_aliases["themes"].items():
        canonical = info.get("canonical_name", code)
        aliases = list(info.get("aliases", [canonical]))
        entities.append({
            "entity_id": f"MACRO_THEME:{code}",
            "type": "MACRO_THEME",
            "code": code,
            "canonical_name": canonical,
            "aliases": aliases,
            "attributes": {"category": "macro_theme"},
            "sources": ["config/entities/aliases/themes.yaml"],
        })

    # --- 7) ASSET_CLASS -----------------------------------------------------
    for code, info in all_domain_aliases["assets"].items():
        canonical = info.get("canonical_name", code)
        aliases = list(info.get("aliases", [canonical]))
        entities.append({
            "entity_id": f"ASSET_CLASS:{code}",
            "type": "ASSET_CLASS",
            "code": code,
            "canonical_name": canonical,
            "aliases": aliases,
            "attributes": {"category": "asset"},
            "sources": ["config/entities/aliases/assets.yaml"],
        })

    # --- 8) INSTITUTION -----------------------------------------------------
    for code, info in all_domain_aliases["institutions"].items():
        canonical = info.get("canonical_name", code)
        aliases = list(info.get("aliases", [canonical]))
        entities.append({
            "entity_id": f"INSTITUTION:{code}",
            "type": "INSTITUTION",
            "code": code,
            "canonical_name": canonical,
            "aliases": aliases,
            "attributes": {"category": "institution"},
            "sources": ["config/entities/aliases/institutions.yaml"],
        })


    # ----- outputs ----------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    active_entities = [e for e in entities if e.get("attributes", {}).get("tier", 1) in (1, 2)]
    archived_entities = [e for e in entities if e.get("attributes", {}).get("tier", 1) == 3]

    _write_json(out_dir / "entities.json", {
        "schema_version": SCHEMA_VERSION,
        "entity_count": len(active_entities),
        "entities": active_entities,
    })
    _write_json(out_dir / "entities_archive.json", {
        "schema_version": SCHEMA_VERSION,
        "entity_count": len(archived_entities),
        "entities": archived_entities,
    })
    _write_csv(out_dir / "entities.csv", active_entities)
    _write_xlsx(out_dir / "entities.xlsx", active_entities, archived_entities)
    _write_taxonomy(out_dir / "taxonomy.json", active_entities, latest)

    stats = _stats(active_entities, archived_entities, all_codes, comp_name, gics)
    _write_json(out_dir / "stats.json", stats)
    return stats


def _sources_for(code, comp_name, etf_codes, mc_codes, os_codes, gics):
    """List the source files that contain the given code."""
    s = []
    if code in etf_codes: s.append("company_data/etf_name.xlsx")
    if code in comp_name: s.append("company_data/company_name.xlsx")
    if code in mc_codes: s.append("trading_data/market_caps.parquet")
    if code in os_codes: s.append("trading_data/os.xlsx")
    if code in gics: s.append("industry_classification/industry_classification.xlsx")
    return s


def _industry(level: str, name: str, parent: str | None, n_tickers: int, ind_aliases_map: dict | None = None) -> dict:
    name = clean_name(name)
    ind_code = slug(name)
    aliases = [name]
    if ind_aliases_map and ind_code in ind_aliases_map:
        for a in ind_aliases_map[ind_code]:
            if a not in aliases:
                aliases.append(a)
    return {
        "entity_id": f"IND_{level}:{ind_code}",
        "type": f"INDUSTRY_{level}",
        "code": ind_code,
        "canonical_name": name,
        "aliases": aliases,
        "attributes": {"parent": parent, "ticker_count": n_tickers},
        "sources": ["industry_classification/industry_classification.xlsx"],
    }


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, entities: list[dict]) -> None:
    cols = ["entity_id", "type", "code", "canonical_name", "tier", "market_cap_bil",
            "aliases", "parent", "gics1", "gics2", "gics3", "sources"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for e in entities:
            a = e["attributes"]
            w.writerow([
                e["entity_id"], e["type"], e["code"], e["canonical_name"],
                a.get("tier", 1), a.get("market_cap_bil", ""),
                " | ".join(e["aliases"]), a.get("parent", ""),
                a.get("gics1", ""), a.get("gics2", ""), a.get("gics3", ""),
                " ; ".join(e["sources"]),
            ])


def _write_xlsx(path: Path, entities: list[dict], archived_entities: list[dict] | None = None) -> None:
    """Write a multi-sheet workbook grouped by entity type for lookup and registration."""

    def alias2(e):
        a = e.get("aliases") or []
        return a[1] if len(a) > 1 else (a[0] if a else "")

    sec_types = ("TICKER", "ETF", "SECURITY_OTHER")
    securities = [{
        "entity_id": e["entity_id"], "type": e["type"], "code": e["code"],
        "canonical_name": e["canonical_name"], "short_name": alias2(e),
        "tier": e["attributes"].get("tier", 1),
        "market_cap_bil": e["attributes"].get("market_cap_bil", ""),
        "latest_date": e["attributes"].get("latest_date", ""),
        "gics1": e["attributes"].get("gics1", ""),
        "gics2": e["attributes"].get("gics2", ""),
        "gics3": e["attributes"].get("gics3", ""),
        "shares_outstanding": e["attributes"].get("shares_outstanding", ""),
        "has_market_cap": e["attributes"].get("has_market_cap", ""),
        "sources": " ; ".join(e["sources"]),
    } for e in entities if e["type"] in sec_types]

    archived_securities = [{
        "entity_id": e["entity_id"], "type": e["type"], "code": e["code"],
        "canonical_name": e["canonical_name"], "short_name": alias2(e),
        "tier": e["attributes"].get("tier", 3),
        "market_cap_bil": e["attributes"].get("market_cap_bil", ""),
        "latest_date": e["attributes"].get("latest_date", ""),
        "gics1": e["attributes"].get("gics1", ""),
        "gics2": e["attributes"].get("gics2", ""),
        "gics3": e["attributes"].get("gics3", ""),
        "sources": " ; ".join(e["sources"]),
    } for e in (archived_entities or []) if e["type"] in sec_types]

    industries = [{
        "entity_id": e["entity_id"], "level": e["type"].replace("INDUSTRY_", ""),
        "code": e["code"], "name": e["canonical_name"],
        "aliases": " | ".join(e["aliases"]),
        "parent": e["attributes"].get("parent", ""),
        "ticker_count": e["attributes"].get("ticker_count", ""),
    } for e in entities if e["type"].startswith("INDUSTRY_")]

    indices = [{
        "entity_id": e["entity_id"], "code": e["code"], "name": e["canonical_name"],
        "aliases": " | ".join(e["aliases"]), "exchange": e["attributes"].get("exchange", ""),
    } for e in entities if e["type"] == "INDEX"]

    exchanges = [{
        "entity_id": e["entity_id"], "code": e["code"], "name": e["canonical_name"],
        "aliases": " | ".join(e["aliases"]),
    } for e in entities if e["type"] == "EXCHANGE"]

    nations = [{
        "entity_id": e["entity_id"], "code": e["code"], "name": e["canonical_name"],
        "aliases": " | ".join(e["aliases"]),
    } for e in entities if e["type"] == "MACRO_GEO"]

    themes = [{
        "entity_id": e["entity_id"], "code": e["code"], "name": e["canonical_name"],
        "aliases": " | ".join(e["aliases"]),
    } for e in entities if e["type"] == "MACRO_THEME"]

    assets = [{
        "entity_id": e["entity_id"], "code": e["code"], "name": e["canonical_name"],
        "aliases": " | ".join(e["aliases"]),
    } for e in entities if e["type"] == "ASSET_CLASS"]

    institutions = [{
        "entity_id": e["entity_id"], "code": e["code"], "name": e["canonical_name"],
        "aliases": " | ".join(e["aliases"]),
    } for e in entities if e["type"] == "INSTITUTION"]

    counts = Counter(e["type"] for e in entities)
    desc = {
        "TICKER": "Cổ phiếu niêm yết (mã 3 ký tự)",
        "ETF": "Quỹ ETF / quỹ mở",
        "SECURITY_OTHER": "Quỹ đóng, trái phiếu, mã phi chuẩn",
        "INDEX": "Chỉ số thị trường",
        "EXCHANGE": "Sàn giao dịch",
        "INDUSTRY_GICS1": "Ngành GICS cấp 1", "INDUSTRY_GICS2": "Ngành GICS cấp 2",
        "INDUSTRY_GICS3": "Ngành GICS cấp 3",
        "MACRO_GEO": "Địa chính trị & Quốc gia",
        "MACRO_THEME": "Chủ đề Vĩ mô",
        "ASSET_CLASS": "Loại tài sản & Công cụ tài chính",
        "INSTITUTION": "Định chế & Cơ quan quản lý",
    }
    index_rows = [{"type": t, "count": counts[t], "description": desc.get(t, ""),
                   "sheet": _SHEET_OF.get(t, "")} for t in counts]
    index_rows.append({"type": "TỔNG", "count": sum(counts.values()), "description": "", "sheet": ""})

    # Guide sheet: end users register entities by the value of the `code` column.
    guide = pd.DataFrame([
        {"Khoá trong file đăng ký": "tickers", "Loại thực thể": "Cổ phiếu / ETF / khác",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Securities", "Ví dụ": "HPG"},
        {"Khoá trong file đăng ký": "etfs", "Loại thực thể": "Quỹ ETF",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Securities", "Ví dụ": "E1VFVN30"},
        {"Khoá trong file đăng ký": "indices", "Loại thực thể": "Chỉ số",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Indices", "Ví dụ": "VNINDEX"},
        {"Khoá trong file đăng ký": "exchanges", "Loại thực thể": "Sàn",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Exchanges", "Ví dụ": "HOSE"},
        {"Khoá trong file đăng ký": "industries", "Loại thực thể": "Ngành GICS (1/2/3)",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Industries", "Ví dụ": "THEP, QUY"},
        {"Khoá trong file đăng ký": "nations", "Loại thực thể": "Địa chính trị / Quốc gia",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Nations", "Ví dụ": "MY, TRUNG_QUOC"},
        {"Khoá trong file đăng ký": "themes", "Loại thực thể": "Chủ đề Vĩ mô",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Themes", "Ví dụ": "LAI_SUAT, TY_GIA"},
        {"Khoá trong file đăng ký": "assets", "Loại thực thể": "Loại tài sản",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Assets", "Ví dụ": "TRAI_PHIEU, VANG"},
        {"Khoá trong file đăng ký": "institutions", "Loại thực thể": "Định chế / Quản lý",
         "Nhập giá trị ở CỘT": "code", "Sheet tra cứu": "Institutions", "Ví dụ": "NHNN, FED"},
    ], columns=["Khoá trong file đăng ký", "Loại thực thể", "Nhập giá trị ở CỘT",
                "Sheet tra cứu", "Ví dụ"])

    sheets = {
        "_Huong_dan": guide,
        "_Index": pd.DataFrame(index_rows, columns=["type", "count", "sheet", "description"]),
        "Securities": pd.DataFrame(securities),
        "Industries": pd.DataFrame(industries),
        "Indices": pd.DataFrame(indices),
        "Exchanges": pd.DataFrame(exchanges),
        "Nations": pd.DataFrame(nations),
        "Themes": pd.DataFrame(themes),
        "Assets": pd.DataFrame(assets),
        "Institutions": pd.DataFrame(institutions),
    }
    if archived_securities:
        sheets["Archived_Securities"] = pd.DataFrame(archived_securities)

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    _format_workbook(path, sheets)


_SHEET_OF = {
    "TICKER": "Securities", "ETF": "Securities", "SECURITY_OTHER": "Securities",
    "INDUSTRY_GICS1": "Industries", "INDUSTRY_GICS2": "Industries",
    "INDUSTRY_GICS3": "Industries",
    "INDEX": "Indices", "EXCHANGE": "Exchanges",
    "MACRO_GEO": "Nations", "MACRO_THEME": "Themes",
    "ASSET_CLASS": "Assets", "INSTITUTION": "Institutions",
}




def _format_workbook(path: Path, sheets: dict) -> None:
    """Freeze the header row, add an auto filter and set column widths."""
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for name, df in sheets.items():
        ws = wb[name]
        ws.freeze_panes = "A2"
        ncol = max(len(df.columns), 1)
        last = ws.cell(row=1, column=ncol).column_letter
        ws.auto_filter.ref = f"A1:{last}{max(ws.max_row, 1)}"
        for c in range(1, ncol + 1):
            cell = ws.cell(row=1, column=c)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center")
            col = cell.column_letter
            width = max(12, min(48, int(df.iloc[:, c - 1].astype(str).str.len().max() if len(df) else 12) + 2))
            ws.column_dimensions[col].width = width
    wb.save(path)


def _write_taxonomy(path: Path, entities: list[dict], latest: pd.DataFrame) -> None:
    tax = {"types": dict(Counter(e["type"] for e in entities))}
    # GICS tree
    tree: dict = {}
    for (g1, g2, g3), _ in latest.groupby(["GICS1_name", "GICS2_name", "GICS3_name"]):
        tree.setdefault(clean_name(g1), {}).setdefault(clean_name(g2), set()).add(clean_name(g3))
    tax["gics_tree"] = {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in tree.items()}
    tax["exchanges"] = [e["code"] for e in EXCHANGES]
    tax["indices"] = list(INDEX_META)
    _write_json(path, tax)


def _stats(active_entities, archived_entities, all_codes, comp_name, gics) -> dict:
    by_type = Counter(e["type"] for e in active_entities)
    ticker_tiers = Counter(e.get("attributes", {}).get("tier", 1) for e in active_entities if e["type"] == "TICKER")
    archived_count = len(archived_entities)
    return {
        "schema_version": SCHEMA_VERSION,
        "total_active_entities": len(active_entities),
        "total_archived_entities": archived_count,
        "by_type": dict(by_type),
        "ticker_tiers": {
            "tier_1_core": ticker_tiers.get(1, 0),
            "tier_2_extended": ticker_tiers.get(2, 0),
            "tier_3_archived": archived_count,
        },
        "securities_active_total": sum(by_type[t] for t in ("TICKER", "ETF", "SECURITY_OTHER")),
        "tickers_with_name": sum(1 for c in all_codes if c in comp_name),
        "tickers_with_gics": sum(1 for c in all_codes if c in gics),
    }


def main(argv=None) -> int:
    """Run the entity catalog build command line.

    Args:
        argv: Command-line arguments. Defaults to `sys.argv`.

    Returns:
        Exit code 0 on success, 2 when the data root does not exist.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Build entity master list từ dữ liệu FRA - Data")
    ap.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if not args.data_root.exists():
        print(f"[ERR] data-root không tồn tại: {args.data_root}", file=sys.stderr)
        return 2
    stats = build(args.data_root, args.out)
    print("== BUILD OK ==")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"\nOutput -> {args.out}")
    return 0

