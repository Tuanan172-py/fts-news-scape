"""Quản lý danh mục thực thể và ánh xạ danh mục theo dõi người dùng."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from loguru import logger as _LOG

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTITIES_JSON = PROJECT_ROOT / "data" / "entities" / "entities.json"
USERS_DIR = PROJECT_ROOT / "config" / "entities" / "users"
MANIFEST_YAML = PROJECT_ROOT / "config" / "entities" / "manifest.yaml"
CONTEXT_GUARDS_YAML = PROJECT_ROOT / "config" / "entities" / "aliases" / "_context_guards.yaml"

# Mã 3 ký tự dễ nhầm với từ viết tắt trong tin tài chính -> không auto-match by code.
CODE_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "ETF", "IPO", "ROE", "ROA", "EPS", "OTC", "GMT",
})

# Alias QUA CHUNG: dia danh, hau to phap ly, mo ta nganh nghe chung. Chung lot vao alias cua
# doanh nghiep qua ten phap ly: "CTCP Chung khoan Guotai Haitong (Viet Nam)" sinh alias
# "Viet Nam" -> TICKER:IVS khop 164 bai, thanh ticker top-1 sai cua ca he thong.
# So khop tren dang DA FOLD (_fold: lower + bo dau). CHI ap cho chung khoan (TICKER/ETF/
# SECURITY_OTHER) - cac nhom nganh/quoc gia/chu de lay alias tu config/entities/aliases/*.yaml
# do nguoi bien tap, o do "xay dung"/"cong nghiep" LA alias hop le cua chinh nhom nganh do.
GENERIC_ALIAS_STOPLIST = frozenset({
    # quoc gia & dia danh hanh chinh
    "viet nam", "vietnam", "ha noi", "tp ha noi", "ho chi minh", "tp ho chi minh",
    "thanh pho ho chi minh", "tphcm", "tp hcm", "sai gon", "da nang", "hai phong",
    "can tho", "song da", "mien bac", "mien nam", "mien trung",
    # san giao dich - da la thuc the EXCHANGE rieng, khong duoc gan cho mot ma
    "hose", "hsx", "hnx", "upcom",
    # hau to phap ly & mo ta nganh nghe chung
    "tap doan", "tong cong ty", "cong ty", "co phan", "dau tu", "dau tu va phat trien",
    "phat trien", "thuong mai", "thuong mai va dich vu", "dich vu", "xuat nhap khau",
    "xay dung", "xay lap", "san xuat", "cong nghiep", "nong nghiep", "quoc te", "viet",
    # ten rut gon trung tu dien/ten rieng thong dung: "Trang" (CTCP Trang, ma TFC) an theo
    # "trạng"/"trăng"/"trắng" (tinh trang, mat trang, mau trang) va ca dang dung chinh ta
    # "trang" trong "trang suc"/"Nha Trang"/"thoi trang" — do tren 1.787 tieu de that: 21/21
    # lan khop la sai (0% dung), TFC qua nho de gia tri that bu duoc nhieu.
    "trang",
})

# Nhom chung khoan - alias sinh tu dong tu ten phap ly nen phai loc qua GENERIC_ALIAS_STOPLIST.
SECURITY_TYPES = ("TICKER", "ETF", "SECURITY_OTHER")

# Các từ ngắn (2-3 ký tự) quan trọng được bảo vệ để không bị bộ lọc độ dài loại bỏ.
PROTECTED_SHORT_WORDS = frozenset({
    "quy", "my", "us", "eu", "fed", "vang", "dau", "cpi", "gdp",
    "fomc", "sbv", "ecb", "boj", "omo", "noxh", "hrc", "ctck", "tctd", "bds",
})

_CODE_RE = re.compile(r"\b[A-Z0-9]{3}\b")
# Tin công bố thông tin (CBTT) chính thức: "VND: Báo cáo tình hình quản trị..."
# Cấp quyền miễn trừ khỏi CODE_STOPLIST nếu mã đứng ngay đầu chuỗi kèm dấu hai chấm.
_DISCLOSURE_PREFIX_RE = re.compile(r"^([A-Z0-9]{3})\s*:")
# Ngữ cảnh phía TRƯỚC khiến mã 3 ký tự không phải mã chứng khoán: "TP.HCM", "UBND HCM", "PGD Tân Bình".
_CODE_LEFT_BLOCK_RE = re.compile(r"(?:\bT\.?P\.?\s*|\bUBND\s*|\bkhu\s+vực\s*)$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")

# Nhóm trong file đăng ký -> thứ tự type thử khi ánh xạ code sang entity_id.
_CATEGORY_TYPES = {
    "tickers": ("TICKER", "SECURITY_OTHER", "ETF"),
    "stocks": ("TICKER", "SECURITY_OTHER", "ETF"),
    "etfs": ("ETF", "SECURITY_OTHER"),
    "indices": ("INDEX",),
    "exchanges": ("EXCHANGE",),
    "nations": ("MACRO_GEO",),
    "themes": ("MACRO_THEME",),
    "macro": ("MACRO_GEO", "MACRO_THEME"),
    "assets": ("ASSET_CLASS",),
    "institutions": ("INSTITUTION",),
}
_INDUSTRY_TYPES = ("INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3")



def _fold(s: str) -> str:
    """Chuyển chuỗi về dạng chữ thường không dấu phục vụ so khớp.

    Args:
        s: Chuỗi văn bản gốc.

    Returns:
        Chuỗi văn bản đã chuyển đổi chữ thường và loại bỏ dấu tiếng Việt.
    """
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return _WS_RE.sub(" ", s.lower()).strip()


def _locate_folded(key: str, raw: str) -> tuple[str | None, tuple[int, int] | None]:
    """Tìm đoạn văn bản con nguyên bản tương ứng với khóa đã chuẩn hóa.

    Args:
        key: Chuỗi khóa đã chuẩn hóa không dấu.
        raw: Chuỗi văn bản gốc cần tìm kiếm.

    Returns:
        Tuple chứa đoạn văn bản tìm thấy và vị trí bắt đầu, kết thúc (start, end).
    """
    n = len(key)
    for m in re.finditer(r"\S+", raw):
        start = m.start()
        # do dai raw co the dai hon key (dau tach ra khi NFD, khoang trang gop lai)
        for end in range(start + n, min(len(raw), start + n + 16) + 1):
            if _fold(raw[start:end]) == key:
                return raw[start:end], (start, end)
    return None, None


def _load_context_guards() -> tuple[dict[str, list[str]], set[str]]:
    """Tải cấu hình ngữ cảnh chặn nhận diện thực thể gây nhiễu.

    Returns:
        Tuple gồm từ điển cụm từ chặn theo entity_id và tập hợp entity_id cần bỏ alias đơn lẻ.
    """
    if not CONTEXT_GUARDS_YAML.exists():
        return {}, set()
    raw = yaml.safe_load(CONTEXT_GUARDS_YAML.read_text(encoding="utf-8")) or {}
    blocks: dict[str, list[str]] = {}
    drop_bare: set[str] = set()
    for eid, cfg in (raw or {}).items():
        cfg = cfg or {}
        folded = [f for f in (_fold(p) for p in (cfg.get("block_in") or [])) if f]
        if folded:
            blocks[str(eid)] = folded
        if cfg.get("drop_bare"):
            drop_bare.add(str(eid))
    return blocks, drop_bare


class EntityRegistry:
    """Sổ đăng ký thực thể hỗ trợ nhận diện và liên kết người dùng đăng ký.

    Attributes:
        entities: Từ điển các thực thể theo entity_id.
        subscriptions: Ánh xạ tên người dùng sang tập hợp entity_id theo dõi.
        aliases_dropped: Số lượng alias bị loại bỏ do quá chung chung.
    """

    def __init__(self, entities: list[dict], subscriptions: dict | None = None):
        """Khởi tạo sổ đăng ký EntityRegistry.

        Args:
            entities: Danh sách các từ điển thực thể.
            subscriptions: Ánh xạ danh mục đăng ký theo người dùng tùy chọn.
        """
        self.entities = {e["entity_id"]: e for e in entities}
        # index alias (đã fold) -> list[entity_id], chỉ alias đủ dài hoặc trong whitelist từ ngắn
        self._alias_index: dict[str, list[str]] = {}
        # dang NGUYEN BAN cua alias theo cung key da fold - dung de xac nhan khop
        # (xem _alias_match), chan false positive do bo dau / hoa-thuong va lay surface nguyen van
        self._alias_forms: dict[str, list[str]] = {}
        # tra ngành GICS theo CODE (chuẩn hoá đồng bộ với các nhóm code khác — KHÔNG theo tên)
        self._industry_ids_by_code: dict[str, list[str]] = {}
        # so alias bi loai vi qua chung — de script build/kiem tra bao cao, khong im lang
        self.aliases_dropped = 0
        # chan alias 1 tu bi trung nghia theo ngu canh (config/entities/aliases/_context_guards.yaml)
        self._context_guards, self._drop_bare_alias = _load_context_guards()
        for eid, e in self.entities.items():
            is_security = e["type"] in SECURITY_TYPES
            # Alias sinh tu ten phap ly cua chung khoan co the la dia danh/hau to chung
            # ("viet nam" -> TICKER:IVS, "song da" -> TICKER:SJG) va se khop gan nhu moi bai.
            # Loai NGAY TAI REGISTRY (khong chi tai index) de moi consumer doc e["aliases"]
            # - _passes_noise_filter, _silver_noise_signals - cung thay tap alias da sach.
            # File entities.json tren dia giu nguyen de kiem toan; build_entities.py loc o
            # lan build sau. Day la nguon chan ly luc chay.
            if is_security:
                kept = [a for a in e.get("aliases", []) if _fold(a) not in GENERIC_ALIAS_STOPLIST]
                if len(kept) != len(e.get("aliases", [])):
                    self.aliases_dropped += len(e["aliases"]) - len(kept)
                    e["aliases"] = kept
            for a in e.get("aliases", []):
                key = _fold(a)
                # drop_bare: ten nganh la tu don trung nghia voi tu thong dung
                # ("Nuoc", "Dien", "Giay", "Quy"). Bo alias MOT TU, chi giu cac cum mang
                # dung intent trong industries.yaml — danh sach CHO PHEP, khong bao gio hut
                # nhu blocklist. Xem _context_guards.yaml.
                if eid in self._drop_bare_alias and " " not in key:
                    self.aliases_dropped += 1
                    continue
                # Nguong do dai: chung khoan giu >= 4 (alias sinh tu dong, 3 ky tu chi la
                # short-name trung lap voi khop theo CODE nen khong them gia tri, lai on).
                # Cac nhom con lai lay alias tu config/entities/aliases/*.yaml do nguoi bien tap
                # nen cho phep >= 3, lay lai cac alias that tung bi mat oan: HNX, HSX, USA, DXY,
                # FDI, IMF, SSC, Nga, ECB, BOJ...
                if len(key) >= 4 or key in PROTECTED_SHORT_WORDS or (not is_security and len(key) >= 3):
                    self._alias_index.setdefault(key, []).append(eid)
                    self._alias_forms.setdefault(key, []).append(a)
            if e["type"] in _INDUSTRY_TYPES:
                self._industry_ids_by_code.setdefault(e["code"], []).append(eid)

        # subscriptions: {tên người dùng -> set(entity_id đã giải)}
        self.subscriptions: dict[str, set[str]] = {
            name: {i for i in ids if i in self.entities}
            for name, ids in (subscriptions or {}).items()
        }

    # ---- lookup ----------------------------------------------------------
    def get(self, entity_id: str) -> dict | None:
        """Lấy thông tin chi tiết một thực thể theo ID.

        Args:
            entity_id: Mã định danh thực thể.

        Returns:
            Từ điển thông tin thực thể hoặc None nếu không tìm thấy.
        """
        return self.entities.get(entity_id)

    def by_type(self, *types: str) -> list[dict]:
        """Lọc danh sách thực thể theo một hoặc nhiều loại.

        Args:
            *types: Các chuỗi phân loại thực thể cần lọc.

        Returns:
            Danh sách các từ điển thực thể thỏa mãn điều kiện.
        """
        ts = set(types)
        return [e for e in self.entities.values() if e["type"] in ts]

    # ---- đăng ký theo người dùng ----------------------------------------
    def select(self, doc: dict) -> tuple[set[str], list[tuple[str, str]]]:
        """Phân giải tệp cấu hình theo dõi của người dùng sang tập ID thực thể.

        Args:
            doc: Dữ liệu cấu hình người dùng từ tệp YAML.

        Returns:
            Tuple chứa tập hợp entity_id hợp lệ và danh sách các mã chưa rõ.
        """
        ids: set[str] = set()
        unknown: list[tuple[str, str]] = []
        doc = doc or {}

        for cat, types in _CATEGORY_TYPES.items():
            for code in doc.get(cat) or []:
                c_clean = str(code).strip().upper()
                hit = next((f"{t}:{c_clean}" for t in types if f"{t}:{c_clean}" in self.entities), None)
                ids.add(hit) if hit else unknown.append((cat, str(code)))

        # industries: chỉ theo CODE ngành (vd THEP, NGAN_HANG, QUY)
        for val in doc.get("industries") or []:
            hits = self._industry_ids_by_code.get(str(val).strip().upper())
            ids.update(hits) if hits else unknown.append(("industries", str(val)))

        for eid in doc.get("entities") or []:   # cửa thoát: entity_id nguyên bản
            ids.add(eid) if eid in self.entities else unknown.append(("entities", str(eid)))

        return ids, unknown

    def resolve_subscription(self, name: str) -> set[str]:
        """Lấy tập hợp ID thực thể mà người dùng đăng ký theo dõi.

        Args:
            name: Tên định danh người dùng.

        Returns:
            Tập hợp các entity_id người dùng đã đăng ký.
        """
        return set(self.subscriptions.get(name, set()))

    def subscribers_for(self, entity_ids) -> set[str]:
        """Tìm danh sách người dùng đăng ký theo dõi các thực thể được chỉ định.

        Args:
            entity_ids: Tập hợp hoặc danh sách entity_id cần tra cứu.

        Returns:
            Tập hợp tên người dùng có đăng ký chứa ít nhất một thực thể trong danh sách.
        """
        ids = set(entity_ids)
        return {u for u, subs in self.subscriptions.items() if subs & ids}

    # ---- detect (matcher chi tiết, ghi rõ khớp qua code/alias) ------------
    def detect(self, text: str) -> list[dict]:
        """Nhận diện các thực thể xuất hiện trong đoạn văn bản kèm nguồn trích dẫn.

        Args:
            text: Đoạn văn bản cần nhận diện thực thể.

        Returns:
            Danh sách từ điển thực thể nhận diện được kèm thông tin hình thái và căn cứ khớp.
        """
        if not text:
            return []
        out: list[dict] = []
        seen: set[str] = set()
        for m in _CODE_RE.finditer(text):
            code = m.group()
            # Miễn trừ cho tin CBTT chính thức ở đầu tiêu đề (ví dụ "VND: Báo cáo quản trị...")
            is_disclosure_prefix = (m.start() == 0 and _DISCLOSURE_PREFIX_RE.match(text))
            if code in CODE_STOPLIST and not is_disclosure_prefix:
                continue
            if _CODE_LEFT_BLOCK_RE.search(text[:m.start()]):
                continue                       # "TP.HCM", "UBND HCM" không phải mã chứng khoán HCM
            # PGD guard: mã PGD (Khí thấp áp) bị nhầm với "Phòng giao dịch" của ngân hàng
            if code == "PGD":
                left_text = text[:m.start()]
                right_text = text[m.end():]
                is_bank_pgd = (
                    re.search(r"(?:thành\s+lập|đổi\s+tên|chi\s+nhánh|điểm|quản\s+lý|tên|[/\\])\s*$", left_text, re.IGNORECASE)
                    or re.match(r"^\s+[A-ZÀ-Ỹ0-9]", right_text)  # "PGD Chợ Tân Bình", "PGD Quận 9"
                    or any(b in text for b in ("MBB:", "TCB:", "VCB:", "BID:", "CTG:", "ACB:", "HDB:", "SHB:", "VPB:", "STB:", "TPB:", "LPB:", "MSB:", "VIB:", "OCB:", "EIB:"))
                )
                if is_bank_pgd:
                    continue

            # EXCHANGE bo sung 2026-09-08: truoc day thieu nen HNX viet dang ma trong tieu de
            # khong bao gio giai duoc ve EXCHANGE:* (lech voi process_l1_pipeline.py).
            for etype in ("TICKER", "ETF", "SECURITY_OTHER", "INDEX", "EXCHANGE",
                          "MACRO_GEO", "MACRO_THEME", "ASSET_CLASS", "INSTITUTION"):
                eid = f"{etype}:{code}"
                if eid in self.entities and eid not in seen:
                    seen.add(eid)
                    out.append({"entity_id": eid, "via": "code", "surface": code})
                    break

        cand: list[tuple[tuple[int, int] | None, str | None, list[str], str]] = []
        folded = _fold(text)
        for key, eids in self._alias_index.items():
            # Prefilter bang `in` truoc khi chay regex: index co ~4.3k alias, hau het khong
            # xuat hien trong tieu de. Kiem tra chuoi con re hon regex ~100x va KHONG doi
            # ngu nghia (regex ranh gioi tu van la dieu kien quyet dinh). Truoc toi uu nay
            # detect() cham toi muc l1_route phai dat tran 50 bai/lan chay.
            if key not in folded:
                continue
            if not re.search(r"\b" + re.escape(key) + r"\b", folded):
                continue
            ok, surface, span = self._alias_match(key, text)
            if not ok:
                continue
            cand.append((span, surface, eids, key))

        # Khu chong lan GIUA CAC CHUNG KHOAN: ten cong ty nay khong the nam long trong ten
        # cong ty khac. "Tap doan Xang dau Viet Nam" (PLX) chua "dau Viet Nam" (OIL) -> chi
        # giu ma dai hon. KHONG ap cho nganh/vi mo: 'Ngan hang' nam trong ten TCB la khop
        # DUNG va can giu ca hai.
        cand.sort(key=lambda c: -((c[0][1] - c[0][0]) if c[0] else 0))
        taken: list[tuple[int, int]] = []
        for span, surface, eids, key in cand:
            sec = [e for e in eids if self.entities[e]["type"] in SECURITY_TYPES]
            if span and sec and any(t[0] <= span[0] and span[1] <= t[1] for t in taken):
                eids = [e for e in eids if e not in sec]
                if not eids:
                    continue
            if span and sec:
                taken.append(span)
            for eid in eids:
                if self._blocked_by_context(eid, key, folded):
                    continue
                if self._blocked_by_morphology(eid, key, surface, span, text):
                    continue
                if eid not in seen:
                    seen.add(eid)
                    out.append({"entity_id": eid, "via": "alias", "surface": surface})

        result = []
        for o in out:
            e = self.entities[o["entity_id"]]
            result.append({
                "entity_id": e["entity_id"], "type": e["type"], "code": e["code"],
                "canonical_name": e["canonical_name"], "via": o["via"],
                "surface": o["surface"],
            })
        return result

    def _blocked_by_context(self, eid: str, key: str, folded: str) -> bool:
        """Kiểm tra sự xuất hiện của alias có bị chi phối hoàn toàn bởi ngữ cảnh chặn hay không.

        Args:
            eid: Mã định danh thực thể.
            key: Khóa alias đã chuẩn hóa.
            folded: Chuỗi tiêu đề đã chuẩn hóa.

        Returns:
            True nếu alias nằm hoàn toàn trong ngữ cảnh bị chặn, ngược lại False.
        """
        phrases = self._context_guards.get(eid)
        if not phrases:
            return False
        stripped = folded
        for ph in phrases:
            if key in ph:
                # PHAI dung ranh gioi tu: str.replace tran lan khien cum 'nuoc ta' an trung
                # ben trong 'nuoc tang gia' va xoa mat mot lan khop dung.
                stripped = re.sub(r"\b" + re.escape(ph) + r"\b", " ", stripped)
        return not re.search(r"\b" + re.escape(key) + r"\b", stripped)

    _INTL_AFTER_MY = frozenset({
        "trump", "biden", "obama", "bush", "clinton", "harris", "hegseth",
        "powell", "yellen", "blinken", "fed", "sec", "cpi", "ppi", "pmi", "gdp",
        "wall", "street", "nasdaq", "dow", "jones", "sp500", "s&p", "pentagon",
        "donald", "joe", "kamala", "barack", "george", "bill", "ronald",
    })
    _VIETNAMESE_PREFIXES = frozenset({"á", "phú", "phù", "nam", "bắc"})
    _HONORIFIC_PREFIXES = frozenset({"bà", "ông", "cô", "chị", "anh", "em", "thị", "văn"})

    def _blocked_by_morphology(self, eid: str, key: str, surface: str | None,
                               span: tuple[int, int] | None, raw: str) -> bool:
        """Chặn các kết quả khớp sai do trùng hình thái từ ghép hoặc danh từ riêng.

        Args:
            eid: Mã định danh thực thể.
            key: Khóa alias đã chuẩn hóa.
            surface: Chuỗi bề mặt văn bản khớp được.
            span: Vị trí (start, end) của chuỗi khớp trong văn bản gốc.
            raw: Chuỗi văn bản gốc.

        Returns:
            True nếu khớp vi phạm quy tắc hình thái học, ngược lại False.
        """
        if not span or not raw:
            return False
        if eid == "MACRO_GEO:MY" and key == "my":
            start, end = span
            # 1. Capitalized suffix: nếu sau "Mỹ" là một từ viết hoa tiếng Việt (Mỹ Thuận, Mỹ Tho, Mỹ Đình, Mỹ Thủy...)
            after = raw[end:].lstrip()
            m_after = re.match(r"^([A-ZÀ-Ỹa-zà-ỹ0-9]+)", after)
            if m_after:
                next_w = m_after.group(1)
                if next_w[0].isupper() and next_w.lower() not in self._INTL_AFTER_MY:
                    return True
            # 2. Prefix guard: nếu trước "Mỹ" là tên riêng ghép (Á Mỹ, Phú Mỹ) hoặc danh xưng/họ tên (Bà Phạm Thị Mỹ Diệu)
            before = raw[:start].rstrip()
            m_before = re.search(r"([A-ZÀ-Ỹa-zà-ỹ0-9]+)$", before)
            if m_before:
                prev_w = m_before.group(1).lower()
                if prev_w in self._VIETNAMESE_PREFIXES or prev_w in self._HONORIFIC_PREFIXES:
                    return True

        if eid == "MACRO_GEO:NGA" and key == "nga":
            start, end = span
            # 1. Prefix guard: Chặn tên người nếu trước "Nga" là danh xưng (Bà, Ông, Chị, Cô) hoặc họ tên ghép (Kim Nga, Thúy Nga, Thiên Nga)
            before = raw[:start].rstrip()
            m_before = re.search(r"([A-ZÀ-Ỹa-zà-ỹ0-9]+)$", before)
            if m_before:
                prev_w = m_before.group(1).lower()
                if prev_w in self._HONORIFIC_PREFIXES or prev_w in {"kim", "thúy", "thuy", "thiên", "thien", "bích", "bich", "hoàng", "hoang"}:
                    return True
            # 2. Suffix guard: Chặn tên tài khoản mạng / tên người ngoại quốc ghép ("Nga Rose", "Nga Phạm"...)
            after = raw[end:].lstrip()
            m_after = re.match(r"^([A-ZÀ-Ỹa-zà-ỹ0-9]+)", after)
            if m_after:
                next_w = m_after.group(1)
                # Nếu từ tiếp theo viết hoa mà không phải từ trong quan hệ ngoại giao / kinh tế
                if next_w.lower() in {"rose", "pham", "nguyen", "tran", "le"} or (next_w[0].isupper() and next_w.lower() in {"hoang", "mai", "lan"}):
                    return True
        return False


    def _alias_match(self, key: str, raw: str) -> tuple[bool, str | None, tuple[int, int] | None]:
        """Xác thực kết quả khớp alias và trích xuất chuỗi bề mặt nguyên bản.

        Args:
            key: Khóa alias đã chuẩn hóa.
            raw: Chuỗi văn bản gốc.

        Returns:
            Tuple gồm trạng thái khớp, chuỗi bề mặt và vị trí (start, end).
        """
        forms = self._alias_forms.get(key) or []
        for f in forms:
            #  * alias CO DAU -> chi doi hoi dung dang co dau, KHONG phan biet hoa-thuong.
            #    Ten nganh trong industries.yaml viet hoa dau dong ('Điện', 'Nước') van la
            #    danh tu CHUNG; bat dung hoa se chan nham 'gia dien', 'nganh dien'.
            #  * KY HIEU ASCII viet hoa NGAN (<=3: US, EU, DXY) -> phai dung hoa, neu khong
            #    'tham my' se khop MACRO_GEO:MY. Ky hieu dai (HOSE, UPCOM) khong mo ho voi tu
            #    thuong nen bo qua hoa-thuong — bao chi hay viet 'HoSE'.
            flags = 0 if (f.isascii() and f.isupper() and len(f) <= 3) else re.IGNORECASE
            m = re.search(r"\b" + re.escape(f) + r"\b", raw, flags)
            if m:
                return True, m.group(0), m.span()
        if " " not in key:
            return False, None, None
        surface, span = _locate_folded(key, raw)
        return True, surface, span

    # ---- text matching (tương thích ngược) -------------------------------
    def match(self, text: str) -> list[dict]:
        """Nhận diện danh sách thực thể duy nhất xuất hiện trong văn bản.

        Args:
            text: Đoạn văn bản cần phân tích.

        Returns:
            Danh sách các từ điển thực thể tương ứng.
        """
        return [self.entities[d["entity_id"]] for d in self.detect(text)]


def _load_manifest() -> dict:
    """Tải tệp manifest quy định trạng thái kích hoạt người dùng."""
    if not MANIFEST_YAML.exists():
        return {"enabled": True, "default": True, "users": {}}
    m = yaml.safe_load(MANIFEST_YAML.read_text(encoding="utf-8")) or {}
    return {
        "enabled": bool(m.get("enabled", True)),
        "default": bool(m.get("default", True)),
        "users": m.get("users") or {},
    }


def _user_enabled(manifest: dict, stem: str) -> bool:
    """Kiểm tra người dùng có được bật nhận tin trong manifest hay không.

    Args:
        manifest: Từ điển cấu hình manifest.
        stem: Tên định danh người dùng.

    Returns:
        True nếu người dùng được kích hoạt, ngược lại False.
    """
    if not manifest.get("enabled", True):
        return False
    return bool(manifest.get("users", {}).get(stem, manifest.get("default", True)))


def _load_subscriptions(reg: EntityRegistry) -> tuple[dict, dict]:
    """Đọc và giải mã các tệp cấu hình theo dõi của người dùng.

    Args:
        reg: Đối tượng EntityRegistry dùng để phân giải thực thể.

    Returns:
        Tuple chứa từ điển danh mục theo dõi và từ điển cảnh báo mã không rõ theo người dùng.
    """
    subs: dict[str, set[str]] = {}
    warnings: dict[str, list] = {}
    if not USERS_DIR.exists():
        return subs, warnings
    manifest = _load_manifest()
    for f in sorted(USERS_DIR.glob("*.yaml")):
        if not _user_enabled(manifest, f.stem):
            # `default: false` khien user co file dang ky nhung chua duoc liet ke bi tat IM LANG.
            # VyPTT da o tinh trang nay. Ghi canh bao de khong lap lai.
            _LOG.warning(
                "[entities] users/{}.yaml co ton tai nhung KHONG duoc bat trong {} "
                "(default={}) -> nguoi dung nay se khong nhan duoc bai nao.",
                f.stem, MANIFEST_YAML.name, manifest.get("default", True))
            continue                               # DEV tat user nay -> bo qua
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        ids, unknown = reg.select(doc)
        subs[f.stem] = ids
        if unknown:
            warnings[f.stem] = unknown
    return subs, warnings


@lru_cache(maxsize=1)
def load_registry() -> EntityRegistry:
    """Nạp và khởi tạo thể hiện EntityRegistry dùng chung từ tệp dữ liệu chuẩn."""
    entities = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))["entities"]
    reg = EntityRegistry(entities)                 # dựng index trước
    subs, warnings = _load_subscriptions(reg)      # rồi giải đăng ký người dùng (đã lọc manifest)
    reg.subscriptions = subs
    reg.subscription_warnings = warnings
    return reg
