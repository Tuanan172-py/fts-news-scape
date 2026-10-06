"""Kiểm tra chuẩn trình bày của tài liệu, tin nhắn và giao diện vận hành, 0 token."""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Phạm vi kiểm tra. Tài liệu cũ ngoài danh sách này chưa bị áp chuẩn.
DOC_GLOBS = ("docs/GLOSSARY.md", "docs/templates/*.md", "project/docs/operations/ops-daemon*.md",
             "project/docs/operations/publisher.md", ".agents/skills/ops-supervision/SKILL.md")
ADR_GLOB = "docs/decisions/*.md"
ADR_MIN_LINT = 14        # blacklist và emoji áp từ ADR này
ADR_MIN_STRUCTURE = 15   # cấu trúc bắt buộc áp từ ADR này
PY_GLOBS = ("project/src/ops/*.py", "project/scripts/ops_daemon.py", "project/scripts/ops_console.py")
HTML_GLOBS = ("project/src/ops/web/*.html",)

# Rule 06 §2: danh mục từ cấm. Ranh giới từ tính theo ký tự Unicode.
BLACKLIST = ("nhìn chung", "thông thường", "nói chung", "về cơ bản", "đáng chú ý",
             "cần lưu ý rằng", "đóng vai trò quan trọng", "toàn diện", "mạnh mẽ",
             "hiệu quả cao", "tối ưu nhất", "chúng ta", "tôi", "bạn có thể thấy rằng")
_BLACKLIST_RE = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in BLACKLIST) + r")(?!\w)",
                           re.IGNORECASE)

_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u23F8\u23F9\u25AB\u25D0"
                       "\u2705\u274C\u26A0\u2713\u2717]|\ufe0f")
# Dòng giao thức đọc đầu ra của `article_run.py`, không phải chữ cho người đọc.
_EMOJI_ALLOW = ("_BATCH_LINE", "(✅|⚠️)")

# Tên cũ đã có tên chuẩn trong GLOSSARY mục 6.
LEGACY_TERMS = (("standing order", "mandate"), ("control room", "Phòng điều khiển"))
_LEGACY_ALLOW = ("agy_standing_order", "Tên cũ")
# Mã nội bộ không được lộ ra người đọc cuối.
_INTERNAL_CODE_RE = re.compile(r"\bUS-(?!IMP\b)[A-Z0-9]+\b|\bD-[A-E]\b")

MAX_SENTENCE_WORDS = 25
RUNBOOK_HEADINGS = ("Mục đích", "Điều kiện", "Các bước", "Xử lý sự cố", "Quay lui", "Tham chiếu")
ADR_HEADINGS = ("Bối cảnh", "Quyết định", "Phương án đã loại", "Hệ quả", "Quay lui")
ADR_META = ("**Ngày:**", "**Trạng thái:**", "**Lane:**")


@dataclass(frozen=True)
class Finding:
    """Một vi phạm chuẩn trình bày.

    Attributes:
        rule: Mã luật (L01 đến L08).
        path: Đường dẫn tương đối của tệp.
        line: Số dòng, bắt đầu từ 1; 0 khi vi phạm ở cấp tệp.
        message: Mô tả vi phạm.
    """

    rule: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line} {self.rule} {self.message}"


def _heading_texts(text: str) -> list[str]:
    """Liệt kê nội dung các tiêu đề `##`, bỏ số thứ tự đầu dòng."""
    return [re.sub(r"^\d+\.\s*", "", m.group(1)).strip()
            for m in re.finditer(r"^##\s+(.+)$", text, re.M)]


def _strip_inline(line: str) -> str:
    """Bỏ định dạng markdown khỏi một dòng để đếm từ."""
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
    return re.sub(r"[*_>#]", "", line)


def lint_markdown(path: str, text: str, *, root: Path = REPO_ROOT, reader_facing: bool = True,
                  check_terms: bool = True, adr_number: int | None = None,
                  check_length: bool = True) -> list[Finding]:
    """Kiểm một tệp markdown.

    Args:
        path: Đường dẫn tương đối dùng để báo lỗi và giải liên kết.
        text: Nội dung tệp.
        root: Gốc kho dùng giải liên kết tương đối.
        reader_facing: True khi áp luật mã nội bộ lộ ra người đọc cuối.
        check_terms: True khi áp luật tên cũ (GLOSSARY và ADR được miễn).
        adr_number: Số của ADR nếu tệp là ADR, để áp cấu trúc bắt buộc.
        check_length: True khi áp luật độ dài câu.

    Returns:
        Danh sách vi phạm.
    """
    out: list[Finding] = []
    in_fence = False
    for no, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        prose = _strip_inline(line)
        m = _BLACKLIST_RE.search(prose)
        if m:
            out.append(Finding("L01", path, no, f"từ cấm \"{m.group(1)}\" (rule 06 mục 2)"))
        if _EMOJI_RE.search(line):
            out.append(Finding("L02", path, no, "có emoji hoặc biểu tượng trang trí"))
        if check_terms:
            low = line.lower()
            for old, new in LEGACY_TERMS:
                if old in low and not any(a in line for a in _LEGACY_ALLOW):
                    out.append(Finding("L03", path, no, f"tên cũ \"{old}\", dùng \"{new}\""))
        if reader_facing:
            m = _INTERNAL_CODE_RE.search(re.sub(r"`[^`]*`", " ", line))
            if m:
                out.append(Finding("L04", path, no, f"mã nội bộ \"{m.group(0)}\" lộ ra người đọc"))
        stripped = line.strip()
        if check_length and stripped and not stripped.startswith(("|", "#", "---", "<!--")):
            for sentence in re.split(r"(?<=[.!?])\s+", prose):
                words = len(sentence.split())
                if words > MAX_SENTENCE_WORDS:
                    out.append(Finding("L08", path, no,
                                       f"câu {words} từ, tối đa {MAX_SENTENCE_WORDS}"))
                    break
    out += _lint_links(path, text, root)
    out += _lint_structure(path, text, adr_number)
    return out


def _lint_links(path: str, text: str, root: Path) -> list[Finding]:
    """Báo liên kết tương đối trỏ tới tệp không tồn tại."""
    out = []
    base = (root / path).parent
    in_fence = False
    for no, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        for target in re.findall(r"\]\(([^)\s]+)\)", re.sub(r"`[^`]*`", " ", line)):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            rel = target.split("#", 1)[0]
            if rel and not (base / rel).exists():
                out.append(Finding("L07", path, no, f"liên kết gãy: {target}"))
    return out


def _lint_structure(path: str, text: str, adr_number: int | None) -> list[Finding]:
    """Kiểm mục bắt buộc theo loại tài liệu khai báo hoặc theo số ADR."""
    out = []
    heads = _heading_texts(text)

    def missing(required: tuple[str, ...]) -> list[str]:
        return [r for r in required if not any(h.lower().startswith(r.lower()) for h in heads)]

    if adr_number is not None and adr_number >= ADR_MIN_STRUCTURE:
        for r in missing(ADR_HEADINGS):
            out.append(Finding("L05", path, 0, f"ADR thiếu mục \"{r}\""))
        for meta in ADR_META:
            if meta not in text:
                out.append(Finding("L05", path, 0, f"ADR thiếu dòng {meta}"))
    if re.search(r"\*\*Loại tài liệu:\*\*\s*hướng dẫn thao tác", text):
        for r in missing(RUNBOOK_HEADINGS):
            out.append(Finding("L06", path, 0, f"runbook thiếu mục \"{r}\""))
    return out


def _docstring_lines(tree: ast.AST) -> set[int]:
    """Tập số dòng thuộc docstring của module, lớp và hàm."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                c = body[0].value
                lines.update(range(c.lineno, (c.end_lineno or c.lineno) + 1))
    return lines


def lint_python(path: str, text: str) -> list[Finding]:
    """Kiểm một tệp Python: từ cấm trong docstring và comment; emoji, tên cũ, mã nội bộ trong chuỗi.

    Args:
        path: Đường dẫn tương đối dùng để báo lỗi.
        text: Nội dung tệp.

    Returns:
        Danh sách vi phạm.
    """
    out: list[Finding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [Finding("L00", path, exc.lineno or 0, f"không đọc được cú pháp: {exc.msg}")]
    doc_lines = _docstring_lines(tree)
    src_lines = text.splitlines()
    for no in sorted(doc_lines):
        m = _BLACKLIST_RE.search(src_lines[no - 1])
        if m:
            out.append(Finding("L01", path, no, f"từ cấm \"{m.group(1)}\" trong docstring"))
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            m = _BLACKLIST_RE.search(tok.string)
            if m:
                out.append(Finding("L01", path, tok.start[0], f"từ cấm \"{m.group(1)}\" trong comment"))
            if _EMOJI_RE.search(tok.string):
                out.append(Finding("L02", path, tok.start[0], "emoji trong comment"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if node.lineno in doc_lines:
            continue
        s = node.value
        line_src = src_lines[node.lineno - 1]
        if _EMOJI_RE.search(s) and not any(a in line_src for a in _EMOJI_ALLOW):
            out.append(Finding("L02", path, node.lineno, "emoji trong chuỗi hiển thị"))
        low = s.lower()
        for old, new in LEGACY_TERMS:
            if old in low and not any(a in s for a in _LEGACY_ALLOW):
                out.append(Finding("L03", path, node.lineno, f"tên cũ \"{old}\", dùng \"{new}\""))
        m = _INTERNAL_CODE_RE.search(s)
        if m:
            out.append(Finding("L04", path, node.lineno, f"mã nội bộ \"{m.group(0)}\" lộ ra người đọc"))
    return out


def lint_html(path: str, text: str) -> list[Finding]:
    """Kiểm trang HTML: emoji, từ cấm, tên cũ và mã nội bộ trong chữ hiển thị.

    Args:
        path: Đường dẫn tương đối dùng để báo lỗi.
        text: Nội dung tệp.

    Returns:
        Danh sách vi phạm.
    """
    out: list[Finding] = []
    for no, line in enumerate(text.splitlines(), 1):
        visible = re.sub(r"<[^>]+>", " ", line)
        if _EMOJI_RE.search(line):
            out.append(Finding("L02", path, no, "emoji trong giao diện"))
        m = _BLACKLIST_RE.search(visible)
        if m and "//" not in line.split(m.group(0))[0]:
            out.append(Finding("L01", path, no, f"từ cấm \"{m.group(1)}\""))
        for old, new in LEGACY_TERMS:
            if old in line.lower():
                out.append(Finding("L03", path, no, f"tên cũ \"{old}\", dùng \"{new}\""))
        m = _INTERNAL_CODE_RE.search(line)
        if m:
            out.append(Finding("L04", path, no, f"mã nội bộ \"{m.group(0)}\" lộ ra người đọc"))
    return out


def lint_repo(root: Path = REPO_ROOT) -> list[Finding]:
    """Kiểm toàn bộ phạm vi đã khai báo của kho.

    Args:
        root: Gốc kho.

    Returns:
        Danh sách vi phạm, sắp theo tệp và dòng.
    """
    out: list[Finding] = []
    for pattern in DOC_GLOBS:
        for f in sorted(root.glob(pattern)):
            rel = f.relative_to(root).as_posix()
            is_glossary = rel == "docs/GLOSSARY.md"
            is_template = rel.startswith("docs/templates/")
            out += lint_markdown(rel, f.read_text(encoding="utf-8"), root=root,
                                 reader_facing=not (is_glossary or is_template),
                                 check_terms=not (is_glossary or is_template))
    for f in sorted(root.glob(ADR_GLOB)):
        m = re.match(r"(\d{4})-", f.name)
        if not m or int(m.group(1)) < ADR_MIN_LINT:
            continue
        rel = f.relative_to(root).as_posix()
        out += lint_markdown(rel, f.read_text(encoding="utf-8"), root=root, reader_facing=False,
                             check_terms=False, adr_number=int(m.group(1)),
                             check_length=int(m.group(1)) >= ADR_MIN_STRUCTURE)
    for pattern in PY_GLOBS:
        for f in sorted(root.glob(pattern)):
            out += lint_python(f.relative_to(root).as_posix(), f.read_text(encoding="utf-8"))
    for pattern in HTML_GLOBS:
        for f in sorted(root.glob(pattern)):
            out += lint_html(f.relative_to(root).as_posix(), f.read_text(encoding="utf-8"))
    return sorted(out, key=lambda x: (x.path, x.line, x.rule))


def main(argv: list[str] | None = None) -> int:
    """Chạy lint và in vi phạm; mã thoát 1 khi có vi phạm.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    ap = argparse.ArgumentParser(description="Lint chuẩn trình bày tài liệu và giao diện")
    ap.add_argument("--summary", action="store_true", help="Chỉ in số vi phạm theo luật")
    args = ap.parse_args(argv)
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    findings = lint_repo()
    if args.summary:
        for rule in sorted({f.rule for f in findings}):
            print(f"{rule}: {sum(1 for f in findings if f.rule == rule)}")
    else:
        for f in findings:
            print(f)
    print(f"Tổng: {len(findings)} vi phạm")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
