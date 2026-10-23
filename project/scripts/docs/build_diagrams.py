"""Build `docs/diagrams/index.html`: one self-contained page with the interactive map and the detail diagrams."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.stdio import force_utf8_stdio

DIAGRAMS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "diagrams"
TEMPLATE = "map.template.html"
MERMAID = Path("vendor") / "mermaid.min.js"
FIRST_FIGURE = 2  # Figure 1 is the interactive map in map.template.html
_META = re.compile(r"^%%\s*(title|desc):\s*(.+)$")


def read_diagram(path: Path) -> dict:
    """Read one `.mmd` file and split its title and description from the Mermaid code.

    Args:
        path: Path of the `.mmd` file.

    Returns:
        Dict with `id`, `title`, `desc` and `code`.
    """
    meta: dict[str, str] = {}
    body: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _META.match(line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
        else:
            body.append(line)
    return {"id": path.stem, "title": meta.get("title", path.stem),
            "desc": meta.get("desc", ""), "code": "\n".join(body).strip() + "\n"}


def build(diagrams_dir: Path = DIAGRAMS_DIR) -> str:
    """Assemble the map template, the inlined Mermaid library and the detail diagrams into one HTML page.

    Args:
        diagrams_dir: Directory holding `map.template.html`, `*.mmd` and `vendor/mermaid.min.js`.

    Returns:
        The complete HTML string, with no reference to an external URL.
    """
    page = (diagrams_dir / TEMPLATE).read_text(encoding="utf-8")
    items = [read_diagram(p) for p in sorted(diagrams_dir.glob("*.mmd"))]
    tabs = "".join(
        f'<button class="tog" type="button" role="tab" data-d="{d["id"]}" aria-pressed="false">'
        f'Figure {i}. {html.escape(d["title"])}</button>' for i, d in enumerate(items, start=FIRST_FIGURE))
    panes = "\n".join(
        f'<figure class="dpane" data-d="{d["id"]}" role="tabpanel"><div class="plot">'
        f'<pre class="mermaid">{html.escape(d["code"])}</pre></div>'
        f'<figcaption><span class="lab">Figure {i}.</span> {html.escape(d["title"])}.'
        f'<span class="note">Note: {html.escape(d["desc"])} Source: <code>{html.escape(d["id"])}.mmd</code>.</span></figcaption></figure>'
        for i, d in enumerate(items, start=FIRST_FIGURE))
    mermaid_js = (diagrams_dir / MERMAID).read_text(encoding="utf-8")
    return (page.replace("@@DETAIL_TABS@@", tabs)
                .replace("@@DETAIL_PANES@@", panes)
                .replace("@@MERMAID@@", mermaid_js))


def main(argv: list[str] | None = None) -> int:
    """Build and write `index.html`; `--check` only compares it with the existing file.

    Args:
        argv: Command-line arguments; None uses `sys.argv`.

    Returns:
        0 on success or when the file matches, 1 when `--check` finds a stale file.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Only check that index.html matches the sources.")
    args = ap.parse_args(argv)
    force_utf8_stdio()
    out = DIAGRAMS_DIR / "index.html"
    content = build()
    if args.check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        print("index.html matches the sources." if current == content else "index.html is STALE; rerun build_diagrams.py.")
        return 0 if current == content else 1
    out.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {out} ({len(content) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
