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

from src.agent.prefix import (                       # noqa: E402
    PRESET_PATH,
    compare_persona,
    digest,
)
from src.core import paths                             # noqa: E402
from src.core.stdio import force_utf8_stdio          # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
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

# The monorepo's news-watch impact rubric, adapted from (article, subject) pairs to the entities of `e`.
# r2 was validated at direction kappa 0.77; r3 (decision U12) adds the derived-effect and speaker rules,
# the sev 2 ownership clause and a market-wrap example. Kept in English, the language it was measured in.
# The monorepo test `tests/news_watch/test_rubric_parity.py` pins the anchors against drift.
IMPACT_SECTION = [
    "## Đánh giá tác động `x` (rubric r3)",
    "",
    "Rate the effect of the article on every entity pair you put in `e`, one `x` item per pair:",
    "`[surface, group, dir, sev, horizon, channel, why]`, with `surface` and `group` copied exactly from `e`.",
    "Judge only from the article text. Do not invent facts or numbers.",
    "Do not put an institution in `e` when it appears only as the speaker or the source of a quote.",
    "",
    "Who the entity stands for:",
    "- A ticker or company (`TIC`, `COM`): that company's earnings, valuation, financing and share flows.",
    "- A sector (`IND`): the listed companies of that sector as a group.",
    "- A macro theme, institution, country, asset, index, exchange, fund or person: Vietnamese listed equities broadly. Rate the effect on the whole market, not on one sector: lower lending rates are `+` for the market even though they squeeze bank margins. Name the most exposed sector in `why`.",
    "",
    "First decide whether the article is about the entity. Give `sev` 0 and `dir` `0` when:",
    "- the entity appears only in a list, a market wrap, a price or rate table, or a line saying its shares rose, fell or supported the index;",
    "- the article is about something else that shares a word with the entity (a domestic tax cut is not trade tariffs; a loan collateral note is not news about the lender);",
    "- the title and the paragraphs describe different events: the text is unreliable, so do not rate it;",
    "- the entity is a sector, macro theme, institution, country or asset, and its only link to the article is one company's news: one company's results, contract, export order, financing or legal case does not move its sector or the market, so rate that company and give the entity sev 0;",
    "- the entity is an institution that appears only as the speaker or the source of a quote: a minister describing the economy does not make the ministry the entity.",
    "",
    "Example, a market wrap. Title `Chứng khoán chiều 5/9: VN-Index tăng 6 điểm, nhóm ngân hàng dẫn dắt`, paragraph `VCB và CTG tăng hơn 2%, khối ngoại mua ròng 300 tỷ đồng, tập trung ở FPT.`",
    "Every entity gets `sev` 0 and `dir` `0`, including the ones the title names. A session's price moves and net buying or selling are not news about any of them:",
    '`[["VN-Index","IDX","0",0,"s","flows","Bản tin phiên giao dịch, chỉ nêu biến động điểm số."],["Ngân hàng","IND","0",0,"s","flows","Nhóm ngành chỉ được nêu là dẫn dắt chỉ số trong phiên."],["VCB","TIC","0",0,"s","flows","Cổ phiếu chỉ xuất hiện trong danh sách tăng giá của phiên."],["CTG","TIC","0",0,"s","flows","Cổ phiếu chỉ xuất hiện trong danh sách tăng giá của phiên."],["FPT","TIC","0",0,"s","flows","Giao dịch mua ròng trong một phiên, không có thông tin mới về doanh nghiệp."]]`',
    "",
    "Direction `dir`:",
    "- `+` the news is good for the entity, `-` bad, `0` neutral, unclear, or only a passing mention.",
    "- When effects pull both ways, give the net direction and name the other side in `why`.",
    "",
    "Severity `sev`, an integer with these anchors:",
    "- sev 0: the entity is only mentioned. No plausible effect on its earnings, valuation, financing or flows. Examples: one name in a market wrap, a routine administrative filing, a list of top gainers. `sev 0` always has `dir` `0`.",
    "- sev 1: minor. Routine or small items: governance and personnel filings, small contracts, an effect under about 2% of annual profit, sentiment that fades within days.",
    "- sev 2: material. An analyst covering the entity should comment. It needs a decision, a reported number or a priced deal that belongs to the entity itself: its own results, issuance or contract, a figure for the whole sector, a policy addressed to it. A number that belongs to someone else, such as a state budget the entity's companies may bid for, is at most sev 1 for the entity. Opinions, forecasts, commentary and promotional pieces are at most sev 1. Examples: quarterly results against expectations, dividend or share issuance decisions, contracts or cost changes worth about 2% to 10% of annual profit, a regulatory change that touches a revenue line, a credible report of a corporate action.",
    "- sev 3: major. It changes the investment case. Examples: more than about 10% of annual profit or of net asset value, M&A, delisting or a major restructuring, legal action against the company or its leaders, a bond default, a policy that resets the sector's economics.",
    "",
    "Horizon: `s` short (sentiment, flows, days to weeks) or `l` long (earnings, assets, competitive position).",
    "",
    "Channel, exactly one of: `earnings`, `dividend`, `capital` (issuance, debt, M&A), `legal`, `policy`, `flows` (foreign or retail trading, index changes), `operations`, `other`.",
    "",
    "`why`: one sentence in Vietnamese, at most 30 words and 240 characters, naming the mechanism: what changes, and for whom.",
    "",
]

IMPACT_EXAMPLE_0 = [
    '  "x":[["Hòa Phát","COM","+",2,"l","earnings","Lợi nhuận quý 3 tăng 25% nhờ sản lượng HRC và biên gộp mở rộng, nâng kỳ vọng lợi nhuận cả năm của Hòa Phát."],',
    '       ["HRC","AST","+",1,"s","policy","Thuế chống bán phá giá hỗ trợ giá HRC nội địa, có lợi cho nhóm thép trong ngắn hạn."],',
    '       ["thuế chống bán phá giá","THM","+",1,"l","policy","Thuế bảo hộ giúp thép nội địa giữ giá bán; ngành thép hưởng lợi nhiều nhất."],',
    '       ["ông Trần Đình Long","PER","0",0,"s","other","Chỉ được trích lời bình luận, không có thay đổi nào liên quan trực tiếp."],',
    '       ["Thép","IND","+",1,"l","policy","Thuế chống bán phá giá giữ giá HRC nội địa, hỗ trợ biên lợi nhuận ngành thép; lợi nhuận riêng của Hòa Phát không tính cho ngành."]]},',
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


def build(items: list[dict], *, with_tickers: bool = False, impacts: bool = False) -> str:
    """Build the full text of the static worker prefix.

    Args:
        items: Full entity catalog.
        with_tickers: Whether to add the ticker catalog to the prefix. See
            :func:`ticker_lines` for why this is a variant and not the default.
        impacts: Emit the ``article-compact-v3`` variant (draft ADR-0028): the record gains
            key ``x`` and the prefix carries the impact rubric (``IMPACT_SECTION``). Off by default, so the v2 prefix is
            byte-identical.

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
    if impacts:
        add(' "sn":"pos|neg|neu","ts":"urg|today|week|month|arch","c":[0,2],"ek":"<MÃ SỰ KIỆN>",')
        add(' "x":[["<chuỗi nguyên văn>","<MÃ NHÓM>","+|-|0",0,"s|l","<kênh>","<lý do>"]]}]')
    else:
        add(' "sn":"pos|neg|neu","ts":"urg|today|week|month|arch","c":[0,2],"ek":"<MÃ SỰ KIỆN>"}]')
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
    add("| `ek` | bản chất sự kiện của bài, đúng 1 mã trong danh sách sáu mã bên dưới | tùy chọn; không chắc thì bỏ hẳn khoá này, đừng đoán |")
    add("| `c` | **chỉ số** các đoạn `p` dùng làm chứng cứ, đếm từ 0, ví dụ `[0,2]` | 2 đến 4 số nguyên khác nhau, xếp tăng dần, mỗi số trỏ vào một đoạn có từ 20 ký tự trở lên; bài chỉ có một đoạn đủ dài thì ghi 1 số; không chép nội dung đoạn |")
    if impacts:
        add("| `x` | mỗi cặp trong `e` một mục `[chuỗi, mã nhóm, dir, sev, horizon, channel, why]`, theo mục \"Đánh giá tác động\" | chuỗi và mã nhóm chép đúng một cặp trong `e`; mỗi cặp tối đa một mục; mảng rỗng khi `e` rỗng |")
    add("")
    add("Mọi khoá trong bảng đều bắt buộc trừ `ek`, không có khoá nào khác. Giá trị ngoài danh sách")
    add("cho phép bị từ chối và bài đó phải làm lại. Không có giá trị mặc định thay cho bạn.")
    add("")
    add("Sáu mã `ek`, chọn theo **việc đang xảy ra**, không theo giọng văn của bài:")
    add("")
    add("| Mã | Dùng khi bài nói về |")
    add("| --- | --- |")
    add("| `MACRO_POLICY` | chính sách hoặc số liệu vĩ mô: lãi suất, tỷ giá, tín dụng, thuế, quy hoạch, luật mới ban hành |")
    add("| `EARNINGS_FINANCE` | kết quả kinh doanh, báo cáo tài chính, cổ tức, kế hoạch lợi nhuận, huy động vốn |")
    add("| `CORP_ACTION_MA` | mua bán sáp nhập, thoái vốn, phát hành, niêm yết, đổi lãnh đạo hay cổ đông lớn |")
    add("| `LEGAL_RISK` | thanh tra, xử phạt, khởi tố, kiện tụng, nợ xấu, vi phạm công bố thông tin |")
    add("| `MARKET_MICROSTRUCTURE` | diễn biến phiên giao dịch, thanh khoản, dòng tiền khối ngoại, margin, ETF cơ cấu danh mục |")
    add("| `PR_BRANDING` | quảng bá thương hiệu, giải thưởng, kỷ niệm, sự kiện truyền thông, tài trợ, tuyển dụng, không đổi định giá |")
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
    add("Chỉ phát một ngành khi bài **nói về** ngành đó, hoặc ngành đó là ngành kinh doanh")
    add("chính của doanh nghiệp là chủ thể bài. Không gán ngành cho doanh nghiệp, tài sản hay")
    add("địa danh chỉ được nhắc qua: tin đấu giá đất không tự động là `Bất động sản`, tin có")
    add("chữ `ngân hàng` trong một danh sách không tự động là `Ngân hàng`.")
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
    if impacts:
        parts.extend(IMPACT_SECTION)
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
    add('  ["ông Trần Đình Long","PER"],["Thép","IND"]],')
    add('  "s":"Hòa Phát đạt lợi nhuận sau thuế 3.200 tỷ đồng trong quý 3, tăng 25% so với cùng kỳ nhờ sản lượng HRC và biên lợi nhuận cải thiện.",')
    add('  "k":["Biên lợi nhuận gộp mở rộng lên 14,1% nhờ giá bán nội địa được thuế tự vệ hỗ trợ",')
    add('       "Sản lượng HRC tăng 32% cho thấy nhu cầu nội địa phục hồi"],')
    add('  "im":"Kết quả vượt kỳ vọng củng cố định giá ngắn hạn; cần theo dõi giá HRC quý 4 và tiến độ áp thuế chính thức.",')
    if impacts:
        add('  "sn":"pos","ts":"today","c":[0,1],"ek":"EARNINGS_FINANCE",')
        for line in IMPACT_EXAMPLE_0:
            add(line)
    else:
        add('  "sn":"pos","ts":"today","c":[0,1],"ek":"EARNINGS_FINANCE"},')
    add(' {"i":1,"e":[["VND","TIC"]],')
    add('  "s":"VNDirect công bố báo cáo quản trị định kỳ 6 tháng, không có thay đổi nhân sự cấp cao.",')
    add('  "k":["Báo cáo mang tính tuân thủ nghĩa vụ công bố thông tin định kỳ",')
    add('       "Không có thay đổi nhân sự cấp cao nên không phát sinh rủi ro điều hành"],')
    add('  "im":"Không có tác động tới định giá; giá trị chủ yếu nằm ở hồ sơ tuân thủ của doanh nghiệp.",')
    if impacts:
        add('  "sn":"neu","ts":"arch","c":[0],"ek":"LEGAL_RISK",')
        add('  "x":[["VND","TIC","0",0,"l","other","Báo cáo quản trị định kỳ, không đổi nhân sự cấp cao nên không tác động tới VNDirect."]]}]')
    else:
        add('  "sn":"neu","ts":"arch","c":[0],"ek":"LEGAL_RISK"}]')
    add("```")
    add("")
    add("Lưu ý trong ví dụ: ngành `Thép` **không** xuất hiện nguyên văn trong bài, nhưng vẫn")
    add("phát vì Hòa Phát là chủ thể bài và thép là ngành kinh doanh chính của nó; nhóm `IND`")
    add("cho phép nhận ra ngành từ ngữ cảnh như vậy và phát đúng tên chuẩn. Mọi nhóm khác chỉ")
    add("phát chuỗi có trong tiêu đề hoặc đoạn văn.")
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


def sync_preset(content: str, preset: Path) -> bool:
    """Write the prefix into the `persona` block of the worker row in the preset.

    The persona must equal the prefix file byte for byte (see `src/agent/prefix.py`), so the
    block is replaced as a whole. Only the lines of the block scalar change; the rest of the
    preset is untouched.

    Args:
        content: Reference prefix content.
        preset: Path of the preset file.

    Returns:
        True when the block was found and rewritten, otherwise False.
    """
    text = preset.read_text(encoding="utf-8")
    lines = text.split("\n")
    try:
        row = next(i for i, ln in enumerate(lines) if ln.strip() == "- id: tool-subagent-article")
        head = next(i for i in range(row, len(lines)) if lines[i] == "    persona: |")
    except StopIteration:
        return False
    end = head + 1
    while end < len(lines) and (lines[end].strip() == "" or lines[end].startswith("      ")):
        end += 1
    while end > head + 1 and lines[end - 1].strip() == "":
        end -= 1
    block = [("      " + ln) if ln.strip() else "" for ln in content.strip().split("\n")]
    new_lines = lines[:head + 1] + block + lines[end:] if end < len(lines) else lines[:head + 1] + block
    preset.write_text("\n".join(new_lines), encoding="utf-8", newline="")
    return True


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
    ap.add_argument("--sync-preset", action="store_true",
                    help="Sinh prefix rồi ghi trọn nó vào `persona` của preset, thay bước dán tay")
    ap.add_argument("--with-tickers", action="store_true",
                    help="Nạp thêm danh mục mã chứng khoán vào prefix (biến thể thí "
                         "nghiệm, xem plan §13). Biến thể được ghi vào tệp mô tả nên "
                         "chế độ kiểm tự dựng lại đúng biến thể ấy")
    ap.add_argument("--impacts", action="store_true",
                    help="Biến thể article-compact-v3 (ADR-0028, đề xuất): thêm khoá x và "
                         "rubric tác động. Mặc định ghi ARTICLE_SYSTEM_CORE_V3.md")
    args = ap.parse_args(argv)
    if args.impacts and args.out == ap.get_default("out"):
        args.out = str(OUT_DIR / "ARTICLE_SYSTEM_CORE_V3.md")

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
    impacts = args.impacts or (args.check and bool(read_variants(meta_path).get("impacts")))
    content = build(items, with_tickers=with_tickers, impacts=impacts)
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
        "variants": {"tickers": bool(tickers), "impacts": impacts},
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
    if args.sync_preset:
        if not sync_preset(content, preset_path):
            print(f"❌ Không tìm thấy khối `persona` của row `tool-subagent-article` trong {preset_path}")
            return 1
        print(f"✅ Đã ghi persona vào {preset_path}")
        return 0 if check_preset(content, preset_path) else 1
    print(f"   Dán nội dung tệp này vào `persona` của row `tool-subagent-article`,")
    print(f"   rồi kiểm lại bằng `build_article_prefix.py --check` trước mỗi đợt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
