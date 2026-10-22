"""Generate the static worker prefix for article processing directly from the entity catalog.

The prefix is generated rather than hand-written because the hand-written lookup table
in the old skill lacked the `IND_GICS*` prefixes, which forced the agent to open
`entities.json` itself; that alone accounted for 53% of the content of an 845k-token
trace. Generating from the source keeps the lookup table in sync with the catalog.

The prefix must stay byte-identical between batches to hit the provider-side cache, so
the generated file carries a hash; `article_run.py` compares this hash before each run.

Two check modes guard two different things:

- `--check` verifies that the file on disk matches the catalog, and that the `persona`
  in the preset matches the file on disk. The second half protects the cache: a correct
  prefix with a persona missing one line still misses the cache, silently.
- `--check-preset` runs only the second half, for confirming right after a manual paste.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.packet.prefix import (                       # noqa: E402
    PRESET_PATH,
    compare_persona,
    digest,
)
from src.core import paths                             # noqa: E402
from src.core.stdio import force_utf8_stdio          # noqa: E402
from src.core.paths import PROJECT_ROOT  # noqa: E402

force_utf8_stdio()

ENTITIES_JSON = paths.entities_dir() / "entities.json"
TAXONOMY_JSON = paths.entities_dir() / "taxonomy.json"
OUT_DIR = PROJECT_ROOT / "assets" / "prefix"

# Closed groups: fully enumerable, so all of them go into the prefix and the model does not guess.
CLOSED_TYPES = [
    "MACRO_GEO", "MACRO_THEME", "ASSET_CLASS", "INSTITUTION",
    "INDEX", "EXCHANGE", "INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3",
]
FUND_TYPES = ["ETF", "SECURITY_OTHER"]

# Group codes emitted by the model. Each code maps to its own lookup algorithm in the
# expander, which is why the groups are separate.
GROUP_CODES = [
    ("TIC", "mã chứng khoán 3 ký tự in hoa xuất hiện nguyên dạng", "HPG, VND, FPT"),
    ("COM", "tên doanh nghiệp hoặc thương hiệu, kể cả thương hiệu con", "Hòa Phát, Bách Hóa Xanh, VinFast"),
    ("PER", "tên người, thường là lãnh đạo doanh nghiệp hoặc quan chức", "ông Trần Đình Long, bà Nguyễn Thị Phương Thảo"),
    ("FND", "quỹ đầu tư hoặc chứng chỉ quỹ ETF", "Diamond ETF, VFMVN30"),
    ("IDX", "chỉ số thị trường", "VN-Index, VN30"),
    ("EXC", "sở giao dịch", "HOSE, HNX, UPCoM"),
    ("IND", "ngành hoặc nhóm ngành kinh tế", "thép, ngân hàng, bất động sản, đường sắt"),
    ("GEO", "quốc gia hoặc khu vực địa chính trị", "Mỹ, Trung Quốc, EU"),
    ("THM", "chủ đề vĩ mô", "lãi suất, tỷ giá, đầu tư công, thuế quan"),
    ("AST", "loại tài sản hoặc hàng hóa", "vàng, dầu thô, trái phiếu, HRC"),
    ("INS", "định chế hoặc cơ quan quản lý", "NHNN, Fed, Bộ Tài chính"),
]


def load_catalog() -> list[dict]:
    """Load the active entity catalog.

    Returns:
        List of entity records.

    Raises:
        FileNotFoundError: If the catalog file does not exist.
    """
    if not ENTITIES_JSON.exists():
        raise FileNotFoundError(f"Thiếu danh mục thực thể: {ENTITIES_JSON}")
    with open(ENTITIES_JSON, encoding="utf-8") as f:
        return (json.load(f) or {}).get("entities", [])


def digest_lines(items: list[dict], types: list[str], *, with_alias: bool = True) -> list[str]:
    """Compress entities of the given types into short lookup lines.

    Args:
        items: Full entity catalog.
        types: Entity types to include.
        with_alias: Whether to append the alias list.

    Returns:
        Lines of the form `entity_id | canonical name | aliases`.
    """
    out: list[str] = []
    for t in types:
        for e in items:
            if e.get("type") != t:
                continue
            parts = [e["entity_id"], e.get("canonical_name") or ""]
            if with_alias:
                aliases = [a for a in (e.get("aliases") or [])
                           if a and a != e.get("canonical_name")]
                if aliases:
                    parts.append(", ".join(aliases))
            out.append(" | ".join(parts))
    return out


def ticker_lines(items: list[dict]) -> list[str]:
    """Compress the ticker catalog into lookup lines.

    This is a variant, not the default, for cache-economics reasons rather than
    recognition quality. Tokens in the prefix cost one fiftieth of fresh tokens from
    the second call onward, so the extra table is nearly free: the full catalog of
    1,093 tickers is about 21,500 tokens, and measured on a 300-article run split into
    three batches it raised the bill by about 1.5% (mostly the cache warm-up call paid
    at the fresh-token price once). In return it may raise `COM` recall, because the
    model sees canonical company names instead of relying on memory.

    Because the variant changes model behavior (a visible ticker table may lead the
    model to emit identifiers instead of verbatim strings), it must be enabled
    explicitly and measured with per-group `resolve_rate` before becoming the default.
    See plan section 13.

    The full catalog is used rather than only the Tier-1 group sketched in the plan,
    because the watchlist changes weekly: tying the prefix to it would add another
    cache-breaking source, and each break requires a manual paste into the preset.

    Args:
        items: Full entity catalog.

    Returns:
        Lines of the form `code | canonical name | aliases`.
    """
    out: list[str] = []
    for e in items:
        if e.get("type") != "TICKER":
            continue
        code = e["entity_id"].split(":", 1)[-1]
        parts = [code, e.get("canonical_name") or ""]
        aliases = [a for a in (e.get("aliases") or [])
                   if a and a != e.get("canonical_name") and a != code]
        if aliases:
            parts.append(", ".join(aliases))
        out.append(" | ".join(parts))
    return out


def build(items: list[dict], *, with_tickers: bool = False) -> str:
    """Build the full text of the static worker prefix.

    Args:
        items: Full entity catalog.
        with_tickers: Whether to add the ticker catalog to the prefix. See
            :func:`ticker_lines` for why this is a variant and not the default.

    Returns:
        Prefix content as Markdown.
    """
    closed = digest_lines(items, CLOSED_TYPES)
    funds = digest_lines(items, FUND_TYPES)
    tickers = ticker_lines(items) if with_tickers else []

    # Map type to identifier prefix, read straight from the data so it cannot drift.
    prefix_map: dict[str, str] = {}
    for e in items:
        prefix_map.setdefault(e["type"], e["entity_id"].split(":")[0])

    parts: list[str] = []
    add = parts.append

    add("# Bộ xử lý bài đăng tài chính Việt Nam")
    add("")
    add("## Bạn không có công cụ nào")
    add("")
    add("Bạn KHÔNG có tool nào dùng được. KHÔNG gọi `run_code`. KHÔNG viết chương trình.")
    add("KHÔNG đọc tệp. KHÔNG tra cứu ở đâu khác. Mọi thứ bạn cần đều nằm trong tin nhắn này")
    add("và trong packet gửi kèm.")
    add("")
    add("Nếu phần hướng dẫn phía sau có nhắc tới SDK hay danh sách tool, hãy bỏ qua: danh")
    add("sách đó rỗng. Nhiệm vụ của bạn là đọc packet rồi trả lời bằng **một mảng JSON duy")
    add("nhất** trong thông điệp cuối, không kèm lời dẫn, không kèm khối mã.")
    add("")
    add("## Việc cần làm")
    add("")
    add("Với **mỗi bài** trong packet, làm đồng thời hai lớp:")
    add("")
    add("1. **Nhận diện thực thể** từ tiêu đề và các đoạn nội dung. Tự đọc, tự quyết định,")
    add("   không có gợi ý nào từ hệ thống và cũng không cần có.")
    add("2. **Xử lý nội dung**: tóm tắt, rút luận điểm, nêu hàm ý thị trường, chấm sắc thái")
    add("   và độ khẩn, chọn đoạn làm chứng cứ.")
    add("")
    add("## Định dạng packet nhận vào")
    add("")
    add("```json")
    add('{"d":"<ngày>","n":<số bài>,"a":[{"i":0,"t":"<tiêu đề>","p":["<đoạn 0>","<đoạn 1>"]}]}')
    add("```")
    add("")
    add("`i` là chỉ số cục bộ của bài trong lô. `p` là mảng các đoạn văn nguyên văn đã được")
    add("chắt lọc sẵn, giữ nguyên thứ tự gốc trong bài.")
    add("")
    add("## Định dạng kết quả trả về")
    add("")
    add("Trả về một mảng JSON, mỗi bài một phần tử, **đúng thứ tự `i` tăng dần**:")
    add("")
    add("```json")
    add('[{"i":0,"e":[["<chuỗi nguyên văn>","<MÃ NHÓM>"]],"s":"<tóm tắt 1-3 câu>",')
    add(' "k":["<luận điểm 1>","<luận điểm 2>"],"im":"<hàm ý thị trường>",')
    add(' "sn":"pos|neg|neu","ts":"urg|today|week|month|arch","c":[0,2]}]')
    add("```")
    add("")
    add("| Khoá | Nội dung | Ràng buộc |")
    add("| --- | --- | --- |")
    add("| `i` | chỉ số bài, chép đúng từ packet | bắt buộc |")
    add("| `e` | mảng cặp `[chuỗi nguyên văn, mã nhóm]` | chuỗi phải là **chuỗi con nguyên văn** của tiêu đề hoặc của một đoạn `p`; riêng nhóm `IND` phát đúng tên ngành chuẩn. Mảng rỗng hợp lệ |")
    add("| `s` | tóm tắt 1 đến 3 câu hoàn chỉnh, tiếng Việt có dấu | bắt buộc |")
    add("| `k` | mảng đúng 2 đến 4 luận điểm, **diễn giải bằng lời của bạn** | không chép nguyên văn đoạn gốc; không phát một chuỗi đơn |")
    add("| `im` | hàm ý với doanh thu, lợi nhuận, dòng tiền hoặc thị giá, tiếng Việt có dấu | tối thiểu 40 ký tự |")
    add("| `sn` | `pos` tích cực, `neg` tiêu cực, `neu` trung tính | đúng 1 trong 3 |")
    add("| `ts` | `urg` khẩn, `today` trong ngày, `week` trong tuần, `month` trong tháng, `arch` lưu trữ | đúng 1 trong 5 |")
    add("| `c` | **chỉ số** các đoạn `p` dùng làm chứng cứ, đếm từ 0, ví dụ `[0,2]` | 2 đến 4 số nguyên khác nhau, xếp tăng dần, mỗi số trỏ vào một đoạn có từ 20 ký tự trở lên; bài chỉ có một đoạn đủ dài thì ghi 1 số; không chép nội dung đoạn |")
    add("")
    add("Mọi khoá trong bảng đều bắt buộc, không có khoá nào khác. Giá trị ngoài danh sách")
    add("cho phép bị từ chối và bài đó phải làm lại. Không có giá trị mặc định thay cho bạn.")
    add("")
    add("Không phát `article_id`, không chép lại tiêu đề, không sinh metadata, không sinh")
    add("`categories`, không tự chấm điểm chất lượng. Hệ thống bên ngoài bù toàn bộ phần đó")
    add("với chi phí bằng không. Mỗi trường bạn phát thừa đều là tiền.")
    add("")
    add("## Mười một mã nhóm thực thể")
    add("")
    add("| Mã | Dùng khi thấy | Ví dụ |")
    add("| --- | --- | --- |")
    for code, desc, ex in GROUP_CODES:
        add(f"| `{code}` | {desc} | {ex} |")
    add("")
    add("Chỉ phát mã nhóm và chuỗi nguyên văn. **Không** phát định danh chuẩn: việc ánh xạ")
    add("sang định danh do hệ thống bên ngoài làm, và nó làm chính xác hơn bạn vì nó có")
    add("toàn bộ danh mục. Bạn thấy `Hòa Phát` thì ghi `Hòa Phát`, hệ thống biết đó là `HPG`.")
    add("")
    add("Riêng nhóm `IND`, hãy phát **đúng tên ngành chuẩn** trong bảng ngành phía dưới nếu")
    add("nhận ra được, vì tên ngành chuẩn khớp trực tiếp một-một. Nếu bài nói `đường sắt`")
    add("thì phát `Vận tải đường bộ & đường sắt`.")
    add("")
    add("## Quy tắc chống nhận nhầm")
    add("")
    add("- **Mã ba ký tự trùng từ viết tắt thông dụng**: `GDP`, `CPI`, `PMI`, `FED`, `USD`,")
    add("  `VND`, `CEO`, `HĐQT`, `UBCK`, `NĐT` thường không phải mã chứng khoán. Ngoại lệ:")
    add("  tin công bố thông tin mở đầu bằng `MÃ:` thì đó chắc chắn là mã, ví dụ")
    add("  `VND: Báo cáo tình hình quản trị` là mã `VND`.")
    add("- **`PGD` trong ngữ cảnh ngân hàng** là phòng giao dịch, không phải mã chứng khoán.")
    add("- **Tên người trùng tên nước**: `Nga` đứng sau danh xưng hoặc họ đệm là tên người,")
    add("  ví dụ `bà Trần Kim Nga`. Không gán thành quốc gia.")
    add("- **Địa danh Việt Nam bắt đầu bằng `Mỹ`**: `Mỹ Tho`, `Mỹ Đình`, `Mỹ Thuận` là địa")
    add("  danh trong nước, không phải nước Mỹ.")
    add("- **Thương hiệu con thuộc tập đoàn mẹ**: cứ phát tên thương hiệu như bài viết dùng")
    add("  (`Bách Hóa Xanh`, `WinMart`, `VinFast`), hệ thống tự quy về mã mẹ.")
    add("- Thà **bỏ sót còn hơn bịa**. Không chắc thì đừng phát.")
    add("")
    add("## Danh mục nhóm đóng")
    add("")
    add("Các nhóm dưới đây đã liệt kê đầy đủ, không có mục nào khác. Dùng đúng tên chuẩn")
    add("hoặc tên gọi khác được liệt kê.")
    add("")
    add("```")
    parts.extend(closed)
    add("```")
    add("")
    add("## Quỹ và chứng khoán khác")
    add("")
    add("```")
    parts.extend(funds)
    add("```")
    add("")
    if tickers:
        add("## Danh mục mã chứng khoán")
        add("")
        add("Bảng này để **nhận ra** doanh nghiệp, không phải để phát định danh. Thấy tên")
        add("doanh nghiệp thì vẫn phát chuỗi nguyên văn như bài viết dùng kèm mã nhóm `COM`;")
        add("thấy mã ba ký tự nguyên dạng thì phát chính mã ấy kèm `TIC`. Việc quy tên về mã")
        add("vẫn do hệ thống bên ngoài làm.")
        add("")
        add("```")
        parts.extend(tickers)
        add("```")
        add("")
    add("## Ví dụ mẫu")
    add("")
    add("Packet vào:")
    add("")
    add("```json")
    add('{"d":"2026-09-18","n":2,"a":[')
    add('{"i":0,"t":"Hòa Phát báo lãi quý 3 tăng 25%, HRC hưởng lợi thuế chống bán phá giá",')
    add(' "p":["Tập đoàn Hòa Phát công bố lợi nhuận sau thuế quý 3 đạt 3.200 tỷ đồng, tăng 25% so với cùng kỳ.",')
    add('      "Sản lượng thép cuộn cán nóng HRC tăng 32%, biên lợi nhuận gộp mở rộng lên 14,1%.",')
    add('      "Ông Trần Đình Long cho biết thuế chống bán phá giá tạo dư địa tăng giá bán nội địa."]},')
    add('{"i":1,"t":"VND: Báo cáo tình hình quản trị công ty 6 tháng đầu năm",')
    add(' "p":["VNDirect công bố báo cáo quản trị định kỳ, không ghi nhận thay đổi nhân sự cấp cao."]}]}')
    add("```")
    add("")
    add("Kết quả ra:")
    add("")
    add("```json")
    add('[{"i":0,"e":[["Hòa Phát","COM"],["HRC","AST"],["thuế chống bán phá giá","THM"],')
    add('  ["ông Trần Đình Long","PER"],["Vận tải đường bộ & đường sắt","IND"]],')
    add('  "s":"Hòa Phát đạt lợi nhuận sau thuế 3.200 tỷ đồng trong quý 3, tăng 25% so với cùng kỳ nhờ sản lượng HRC và biên lợi nhuận cải thiện.",')
    add('  "k":["Biên lợi nhuận gộp mở rộng lên 14,1% nhờ giá bán nội địa được thuế tự vệ hỗ trợ",')
    add('       "Sản lượng HRC tăng 32% cho thấy nhu cầu nội địa phục hồi"],')
    add('  "im":"Kết quả vượt kỳ vọng củng cố định giá ngắn hạn; cần theo dõi giá HRC quý 4 và tiến độ áp thuế chính thức.",')
    add('  "sn":"pos","ts":"today","c":[0,1]},')
    add(' {"i":1,"e":[["VND","TIC"]],')
    add('  "s":"VNDirect công bố báo cáo quản trị định kỳ 6 tháng, không có thay đổi nhân sự cấp cao.",')
    add('  "k":["Báo cáo mang tính tuân thủ nghĩa vụ công bố thông tin định kỳ",')
    add('       "Không có thay đổi nhân sự cấp cao nên không phát sinh rủi ro điều hành"],')
    add('  "im":"Không có tác động tới định giá; giá trị chủ yếu nằm ở hồ sơ tuân thủ của doanh nghiệp.",')
    add('  "sn":"neu","ts":"arch","c":[0]}]')
    add("```")
    add("")
    add("Lưu ý trong ví dụ: ngành `Vận tải đường bộ & đường sắt` **không** xuất hiện nguyên")
    add("văn trong bài, nhưng vẫn phát vì nhóm `IND` cho phép nhận ra ngành từ ngữ cảnh và")
    add("phát đúng tên chuẩn. Mọi nhóm khác chỉ phát chuỗi có trong tiêu đề hoặc đoạn văn.")
    add("Bài thứ hai chỉ có một đoạn đủ dài nên `c` có đúng một số.")
    add("")
    add("## Nhắc lại lần cuối")
    add("")
    add("Không tool. Không chương trình. Không đọc tệp. Một mảng JSON trong thông điệp cuối.")
    add("")
    add("---")
    add("")
    add(f"<!-- ánh xạ loại sang tiền tố định danh: "
        f"{', '.join(f'{k}->{v}' for k, v in sorted(prefix_map.items()))} -->")

    return "\n".join(parts) + "\n"


def read_variants(meta_path: Path) -> dict:
    """Read the enabled variants of the prefix currently on disk.

    Args:
        meta_path: Path of the metadata file.

    Returns:
        Variant dict, empty when the file is missing or corrupt.
    """
    try:
        with open(meta_path, encoding="utf-8") as f:
            variants = (json.load(f) or {}).get("variants")
    except (OSError, json.JSONDecodeError):
        return {}
    return variants if isinstance(variants, dict) else {}


def check_preset(content: str, preset: Path) -> bool:
    """Print the comparison of the preset persona against the reference prefix.

    Args:
        content: Reference prefix content.
        preset: Path of the preset file.

    Returns:
        True when the persona matches, otherwise False.
    """
    ok, detail = compare_persona(content, preset)
    if ok:
        print(f"✅ Persona trong preset khớp prefix. {detail}")
        return True
    print(f"❌ Persona trong preset ĐÃ LỆCH prefix: {detail}")
    print(f"   Tệp: {preset}")
    print("   Dán lại trọn nội dung prefix vào `persona` của row "
          f"`tool-subagent-article`. Lệch một dòng là mọi token sau nó trượt bộ nhớ")
    print("   đệm và bị tính giá đắt gấp 50 lần mà không có cảnh báo nào khác.")
    return False


def main(argv=None) -> int:
    """Run the prefix generation command line.

    Args:
        argv: Command-line arguments. Defaults to `sys.argv`.

    Returns:
        Exit code 0 on success, 1 when a check mode detects a mismatch.
    """
    ap = argparse.ArgumentParser(description="Sinh prefix tĩnh cho worker từ catalog")
    ap.add_argument("--out", default=str(OUT_DIR / "ARTICLE_SYSTEM_CORE.md"),
                    help="Đường dẫn tệp prefix đầu ra")
    ap.add_argument("--preset", default=str(PRESET_PATH),
                    help="Đường dẫn preset chứa persona của worker")
    ap.add_argument("--check", action="store_true",
                    help="Kiểm tệp còn khớp catalog VÀ persona còn khớp tệp, không ghi đè")
    ap.add_argument("--check-preset", action="store_true",
                    help="Chỉ kiểm persona trong preset còn khớp tệp prefix trên đĩa")
    ap.add_argument("--with-tickers", action="store_true",
                    help="Nạp thêm danh mục mã chứng khoán vào prefix (biến thể thí "
                         "nghiệm, xem plan §13). Biến thể được ghi vào tệp mô tả nên "
                         "chế độ kiểm tự dựng lại đúng biến thể ấy")
    args = ap.parse_args(argv)

    out_path = Path(args.out)
    preset_path = Path(args.preset)
    meta_path = out_path.with_suffix(".meta.json")

    if args.check_preset:
        if not out_path.exists():
            print("❌ Chưa sinh prefix. Chạy lại không kèm --check-preset.")
            return 1
        return 0 if check_preset(out_path.read_text(encoding="utf-8"), preset_path) else 1

    items = load_catalog()
    # In check mode the variant follows what is recorded on disk unless the operator
    # overrides it; otherwise a prefix generated with the ticker digest would be
    # reported as mismatched on every check even though it is correct.
    with_tickers = args.with_tickers
    if (args.check and not args.with_tickers
            and read_variants(meta_path).get("tickers")):
        with_tickers = True
    content = build(items, with_tickers=with_tickers)
    content_digest = digest(content)

    if args.check:
        if not out_path.exists():
            print("❌ Chưa sinh prefix. Chạy lại không kèm --check.")
            return 1
        current = out_path.read_text(encoding="utf-8")
        cur_digest = digest(current)
        if cur_digest != content_digest:
            print(f"❌ Prefix ĐÃ LỆCH catalog. trên đĩa={cur_digest} · "
                  f"sinh mới={content_digest}")
            print("   Sinh lại rồi cập nhật persona trong preset, nếu không sẽ vỡ "
                  "bộ nhớ đệm.")
            return 1
        print(f"✅ Prefix khớp catalog. hash={content_digest}")
        return 0 if check_preset(current, preset_path) else 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    approx_tokens = len(content) // 3
    tickers = ticker_lines(items) if with_tickers else []
    meta = {
        "hash": content_digest,
        "chars": len(content),
        "approx_tokens": approx_tokens,
        "entities_total": len(items),
        "closed_group_lines": len(digest_lines(items, CLOSED_TYPES)),
        "fund_lines": len(digest_lines(items, FUND_TYPES)),
        "ticker_lines": len(tickers),
        "variants": {"tickers": bool(tickers)},
        "source": paths.to_data_relative(ENTITIES_JSON),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Đã sinh prefix: {out_path}")
    print(f"   hash={content_digest} · {len(content):,} ký tự · ~{approx_tokens:,} token")
    print(f"   nhóm đóng {meta['closed_group_lines']} dòng · quỹ {meta['fund_lines']} dòng"
          + (f" · mã chứng khoán {meta['ticker_lines']} dòng" if tickers else ""))
    if tickers:
        base = len(build(items, with_tickers=False)) // 3
        print(f"   biến thể digest mã chứng khoán: +{approx_tokens - base:,} token mỗi "
              f"lượt gọi, trúng bộ nhớ đệm từ lượt thứ hai")
    print(f"   Dán nội dung tệp này vào `persona` của row `tool-subagent-article`,")
    print(f"   rồi kiểm lại bằng `build_article_prefix.py --check` trước mỗi đợt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
