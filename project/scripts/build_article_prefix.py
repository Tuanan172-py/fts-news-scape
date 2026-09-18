"""Sinh prefix tĩnh cho worker xử lý bài đăng, trực tiếp từ catalog thực thể.

Prefix được sinh chứ không gõ tay vì một lý do đã trả giá bằng token thật: bảng tra
chép tay trong skill cũ thiếu tiền tố `IND_GICS*`, khiến agent phải tự mở
`entities.json` để dò, và riêng việc đó chiếm 53% toàn bộ nội dung của vệt 845 nghìn
token. Sinh từ nguồn thì bảng tra không bao giờ lệch catalog được nữa.

Prefix phải giữ nguyên từng byte giữa các lô để trúng bộ nhớ đệm phía nhà cung cấp,
nên tệp sinh ra kèm một giá trị băm; `article_run.py` đối chiếu băm này trước mỗi đợt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.stdio import force_utf8_stdio          # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTITIES_JSON = PROJECT_ROOT / "data" / "entities" / "entities.json"
TAXONOMY_JSON = PROJECT_ROOT / "data" / "entities" / "taxonomy.json"
OUT_DIR = PROJECT_ROOT / "data" / "prefix"

# Nhóm đóng: liệt kê được toàn bộ nên đưa hết vào prefix, model không phải đoán.
CLOSED_TYPES = [
    "MACRO_GEO", "MACRO_THEME", "ASSET_CLASS", "INSTITUTION",
    "INDEX", "EXCHANGE", "INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3",
]
FUND_TYPES = ["ETF", "SECURITY_OTHER"]

# Mã nhóm model phát ra. Mỗi mã ứng với một thuật toán tra cứu riêng ở expander,
# đó là lý do tách nhóm chứ không phải để phân loại cho đẹp.
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
    """Nạp danh mục thực thể đang hiệu lực.

    Returns:
        Danh sách bản ghi thực thể.

    Raises:
        FileNotFoundError: Khi tệp danh mục không tồn tại.
    """
    if not ENTITIES_JSON.exists():
        raise FileNotFoundError(f"Thiếu danh mục thực thể: {ENTITIES_JSON}")
    with open(ENTITIES_JSON, encoding="utf-8") as f:
        return (json.load(f) or {}).get("entities", [])


def digest_lines(items: list[dict], types: list[str], *, with_alias: bool = True) -> list[str]:
    """Nén các thực thể thuộc một số loại thành các dòng tra cứu ngắn gọn.

    Args:
        items: Toàn bộ danh mục thực thể.
        types: Danh sách loại cần lấy.
        with_alias: Có kèm danh sách tên gọi khác hay không.

    Returns:
        Danh sách dòng dạng `entity_id | tên chuẩn | các alias`.
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


def build(items: list[dict]) -> str:
    """Dựng toàn văn prefix tĩnh cho worker.

    Args:
        items: Toàn bộ danh mục thực thể.

    Returns:
        Nội dung prefix dạng Markdown.
    """
    closed = digest_lines(items, CLOSED_TYPES)
    funds = digest_lines(items, FUND_TYPES)

    # Ánh xạ loại sang tiền tố định danh, đọc thẳng từ dữ liệu để không bao giờ lệch.
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
    add("| `e` | mảng cặp `[chuỗi nguyên văn, mã nhóm]` | chuỗi phải là **chuỗi con nguyên văn** của tiêu đề hoặc của một đoạn `p` |")
    add("| `s` | tóm tắt 1 đến 3 câu hoàn chỉnh | bắt buộc |")
    add("| `k` | 2 đến 4 luận điểm, **diễn giải bằng lời của bạn** | không chép nguyên văn đoạn gốc |")
    add("| `im` | hàm ý với doanh thu, lợi nhuận, dòng tiền hoặc thị giá | tối thiểu 40 ký tự |")
    add("| `sn` | `pos` tích cực, `neg` tiêu cực, `neu` trung tính | đúng 1 trong 3 |")
    add("| `ts` | `urg` khẩn, `today` trong ngày, `week` trong tuần, `month` trong tháng, `arch` lưu trữ | đúng 1 trong 5 |")
    add("| `c` | **chỉ số** các đoạn `p` dùng làm chứng cứ, ví dụ `[0,2]` | không chép nội dung đoạn, chỉ ghi số |")
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
    add('  "k":["Báo cáo mang tính tuân thủ nghĩa vụ công bố thông tin định kỳ"],')
    add('  "im":"Không có tác động tới định giá; giá trị chủ yếu nằm ở hồ sơ tuân thủ của doanh nghiệp.",')
    add('  "sn":"neu","ts":"arch","c":[0]}]')
    add("```")
    add("")
    add("Lưu ý trong ví dụ: ngành `Vận tải đường bộ & đường sắt` **không** xuất hiện nguyên")
    add("văn trong bài, nhưng vẫn phát vì nhận ra được từ ngữ cảnh, và phát đúng tên chuẩn.")
    add("Đó là phần giá trị mà chỉ bạn làm được.")
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


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh sinh prefix.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0 khi sinh thành công, 1 khi chế độ kiểm phát hiện lệch.
    """
    ap = argparse.ArgumentParser(description="Sinh prefix tĩnh cho worker từ catalog")
    ap.add_argument("--out", default=str(OUT_DIR / "ARTICLE_SYSTEM_CORE.md"),
                    help="Đường dẫn tệp prefix đầu ra")
    ap.add_argument("--check", action="store_true",
                    help="Chỉ kiểm tệp hiện có còn khớp catalog không, không ghi đè")
    args = ap.parse_args(argv)

    items = load_catalog()
    content = build(items)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    out_path = Path(args.out)
    meta_path = out_path.with_suffix(".meta.json")

    if args.check:
        if not out_path.exists():
            print("❌ Chưa sinh prefix. Chạy lại không kèm --check.")
            return 1
        current = out_path.read_text(encoding="utf-8")
        cur_digest = hashlib.sha256(current.encode("utf-8")).hexdigest()[:16]
        if cur_digest == digest:
            print(f"✅ Prefix khớp catalog. hash={digest}")
            return 0
        print(f"❌ Prefix ĐÃ LỆCH catalog. trên đĩa={cur_digest} · sinh mới={digest}")
        print("   Sinh lại rồi cập nhật persona trong preset, nếu không sẽ vỡ bộ nhớ đệm.")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    approx_tokens = len(content) // 3
    meta = {
        "hash": digest,
        "chars": len(content),
        "approx_tokens": approx_tokens,
        "entities_total": len(items),
        "closed_group_lines": len(digest_lines(items, CLOSED_TYPES)),
        "fund_lines": len(digest_lines(items, FUND_TYPES)),
        "source": str(ENTITIES_JSON),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Đã sinh prefix: {out_path}")
    print(f"   hash={digest} · {len(content):,} ký tự · ~{approx_tokens:,} token")
    print(f"   nhóm đóng {meta['closed_group_lines']} dòng · quỹ {meta['fund_lines']} dòng")
    print(f"   Dán nội dung tệp này vào `persona` của row `tool-subagent-article`,")
    print(f"   rồi kiểm lại bằng `build_article_prefix.py --check` trước mỗi đợt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
