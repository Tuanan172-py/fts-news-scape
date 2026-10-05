"""Ánh xạ thực thể do mô hình nêu tên sang định danh chuẩn trong danh mục.

Ranh giới nghiệp vụ ở đây rất hẹp và cố ý: mô hình **quyết định** có thực thể nào
trong bài, còn module này chỉ **tra cứu** thứ mô hình đã chỉ ra. Nó không tự phát
hiện thêm, không tự suy diễn, không phủ quyết mô hình. Khi không tra được, nó ghi
nhận là ngoài danh mục thay vì đoán bừa.

Mỗi mã nhóm có một thuật toán tra riêng, và đó chính là lý do tách nhóm: mã chứng
khoán cần khớp chính xác kèm danh sách loại trừ từ viết tắt, tên doanh nghiệp cần
khớp tên gọi khác kèm rào cản hình thái, còn các nhóm đóng thì tra thẳng bảng.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.agent.entities import CODE_STOPLIST, EntityRegistry, _fold

# Mã nhóm mô hình phát ra, ánh xạ sang các loại thực thể được phép tra trong danh mục.
GROUP_TYPES: dict[str, tuple[str, ...]] = {
    "TIC": ("TICKER",),
    "COM": ("TICKER",),
    "PER": (),                       # cần bảng lãnh đạo, xem ghi chú bên dưới
    "FND": ("ETF", "SECURITY_OTHER"),
    "IDX": ("INDEX",),
    "EXC": ("EXCHANGE",),
    "IND": ("INDUSTRY_GICS3", "INDUSTRY_GICS2", "INDUSTRY_GICS1"),
    "GEO": ("MACRO_GEO",),
    "THM": ("MACRO_THEME",),
    "AST": ("ASSET_CLASS",),
    "INS": ("INSTITUTION",),
}

VALID_GROUPS = frozenset(GROUP_TYPES)

# Nhóm `PER` chưa có nguồn tra: bảng lãnh đạo ánh xạ tên người sang mã doanh nghiệp
# chưa tồn tại. Từ nay tới khi có, mọi tên người đều rơi vào ngoài danh mục — đúng
# thiết kế, không phải lỗi. Giá trị của nhóm này ở giai đoạn đầu là **thu thập dữ
# liệu** để dựng chính bảng đó, nên nó được đo bằng số tên thu được chứ không bằng
# tỷ lệ tra cứu thành công.
GROUPS_WITHOUT_RESOLVER = frozenset({"PER"})

_CODE_RE = re.compile(r"^[A-Z0-9]{3}$")
_DISCLOSURE_RE = re.compile(r"^([A-Z0-9]{3})\s*:")


@dataclass
class ResolvedEntity:
    """Kết quả tra cứu một thực thể do mô hình nêu tên."""

    surface: str
    group: str
    entity_id: str | None = None
    type: str | None = None
    method: str = "semantic"
    in_list: bool = False
    in_title: bool = False


@dataclass
class ResolveReport:
    """Thống kê tra cứu của một lô, dùng để theo dõi chất lượng theo nhóm."""

    total: dict[str, int] = field(default_factory=dict)
    resolved: dict[str, int] = field(default_factory=dict)

    def add(self, group: str, ok: bool) -> None:
        """Ghi nhận một lượt tra cứu.

        Args:
            group: Mã nhóm thực thể.
            ok: Tra cứu có ra định danh chuẩn hay không.
        """
        self.total[group] = self.total.get(group, 0) + 1
        if ok:
            self.resolved[group] = self.resolved.get(group, 0) + 1

    def rate(self, group: str) -> float:
        """Tính tỷ lệ tra cứu thành công của một nhóm.

        Args:
            group: Mã nhóm thực thể.

        Returns:
            Tỷ lệ từ 0 đến 1; trả về 0 khi nhóm chưa có lượt nào.
        """
        n = self.total.get(group, 0)
        return (self.resolved.get(group, 0) / n) if n else 0.0

    def summary(self) -> list[tuple[str, int, int, float]]:
        """Kết xuất thống kê theo nhóm để in báo cáo.

        Returns:
            Danh sách bộ gồm mã nhóm, số lượt tra, số lượt thành công và tỷ lệ.
        """
        return [(g, self.total[g], self.resolved.get(g, 0), self.rate(g))
                for g in sorted(self.total)]


class IntentResolver:
    """Tra cứu định danh chuẩn cho các thực thể mô hình đã nêu tên."""

    def __init__(self, registry: EntityRegistry):
        """Dựng bộ tra cứu và các chỉ mục ngược cần thiết.

        Args:
            registry: Danh mục thực thể đã nạp.
        """
        self.reg = registry
        self._by_type_name: dict[str, dict[str, str]] = {}
        for eid, ent in registry.entities.items():
            etype = ent.get("type")
            bucket = self._by_type_name.setdefault(etype, {})
            names = [ent.get("canonical_name") or ""] + list(ent.get("aliases") or [])
            for name in names:
                key = _fold(name)
                if key:
                    bucket.setdefault(key, eid)

    def _lookup(self, surface: str, types: tuple[str, ...]) -> tuple[str | None, str | None]:
        """Tra một chuỗi trong các loại thực thể được phép, theo thứ tự ưu tiên.

        Args:
            surface: Chuỗi nguyên văn mô hình nêu.
            types: Các loại thực thể được phép khớp, xét theo thứ tự truyền vào.

        Returns:
            Cặp định danh và loại thực thể; cả hai là None khi không khớp.
        """
        key = _fold(surface)
        if not key:
            return None, None
        for t in types:
            eid = (self._by_type_name.get(t) or {}).get(key)
            if eid:
                return eid, t
        return None, None

    def resolve_one(self, surface: str, group: str, *, title: str = "") -> ResolvedEntity:
        """Tra cứu một thực thể do mô hình nêu tên.

        Args:
            surface: Chuỗi nguyên văn mô hình nêu.
            group: Mã nhóm mô hình gán.
            title: Tiêu đề bài, dùng để biết thực thể có xuất hiện ở tiêu đề không.

        Returns:
            Kết quả tra cứu; `in_list` là False khi không có trong danh mục.
        """
        surface = (surface or "").strip()
        group = (group or "").strip().upper()
        out = ResolvedEntity(surface=surface, group=group)
        out.in_title = bool(surface) and surface in (title or "")

        if not surface or group not in VALID_GROUPS or group in GROUPS_WITHOUT_RESOLVER:
            return out

        types = GROUP_TYPES[group]

        if group == "TIC":
            code = surface.upper()
            # Mã ba ký tự trùng từ viết tắt thông dụng chỉ được công nhận khi bài là
            # công bố thông tin mở đầu bằng "MÃ:", đúng quy ước đã dùng ở tầng mã.
            if _CODE_RE.match(code):
                disclosure = _DISCLOSURE_RE.match((title or "").strip())
                exempt = bool(disclosure and disclosure.group(1) == code)
                if code in CODE_STOPLIST and not exempt:
                    return out
                ent = self.reg.entities.get(f"TICKER:{code}")
                if ent:
                    out.entity_id = ent["entity_id"]
                    out.type = ent["type"]
                    out.method = "exact_code"
                    out.in_list = True
                    return out
            # Mô hình gán nhầm nhóm thì vẫn thử tra như tên doanh nghiệp.
            types = ("TICKER",)

        eid, etype = self._lookup(surface, types)
        if eid:
            out.entity_id = eid
            out.type = etype
            out.method = "alias" if group in ("TIC", "COM") else "semantic"
            out.in_list = True
        return out

    def resolve_many(self, pairs, *, title: str = "",
                     report: ResolveReport | None = None) -> list[ResolvedEntity]:
        """Tra cứu một danh sách thực thể và khử trùng lặp.

        Args:
            pairs: Chuỗi các cặp `[chuỗi nguyên văn, mã nhóm]` do mô hình phát.
            title: Tiêu đề bài viết.
            report: Bộ đếm thống kê theo nhóm, nếu cần theo dõi.

        Returns:
            Danh sách kết quả tra cứu đã khử trùng lặp, giữ thứ tự xuất hiện.
        """
        seen: set[tuple[str, str]] = set()
        out: list[ResolvedEntity] = []
        for pair in pairs or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            surface, group = str(pair[0] or ""), str(pair[1] or "").upper()
            key = (surface.lower(), group)
            if not surface or key in seen:
                continue
            seen.add(key)
            r = self.resolve_one(surface, group, title=title)
            if report is not None:
                report.add(group, r.in_list)
            out.append(r)
        return out


def reconcile(llm: list[ResolvedEntity], code_ids: set[str]) -> dict[str, str]:
    """Đối chiếu kết quả của mô hình với kết quả của tầng mã tất định.

    Nhãn sinh ra ở đây là thứ cho người dùng cuối thấy phần nào do mô hình nhận ra và
    phần nào do mã nhận ra. Nhóm `LLM_ONLY` chính là vùng giá trị riêng của mô hình:
    thương hiệu con, ngành suy ra từ ngữ cảnh, chủ đề vĩ mô không có từ khoá cứng.

    Args:
        llm: Danh sách thực thể mô hình nêu, đã tra cứu.
        code_ids: Tập định danh mà tầng mã tất định tìm được.

    Returns:
        Từ điển ánh xạ định danh sang nhãn `BOTH`, `LLM_ONLY` hoặc `CODE_ONLY`.
    """
    llm_ids = {e.entity_id for e in llm if e.entity_id}
    labels: dict[str, str] = {}
    for eid in llm_ids | code_ids:
        if eid in llm_ids and eid in code_ids:
            labels[eid] = "BOTH"
        elif eid in llm_ids:
            labels[eid] = "LLM_ONLY"
        else:
            labels[eid] = "CODE_ONLY"
    return labels
