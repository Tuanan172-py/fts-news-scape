"""Kích thước và tính toàn vẹn của phần tiền tố tĩnh gửi cho worker.

Bốn nơi cần biết về prefix — bộ sinh, bộ đóng gói, sổ cái và radar — và trước đây
mỗi nơi tự giữ một hằng số riêng. Hệ quả đã đo được: dự toán chỉ đếm phần `persona`
mà bỏ quên phần harness nối thêm vào đầu mỗi request, nên số token trúng bộ nhớ đệm
bị khai hụt và không ai đối chiếu được "cache có thật sự trúng không".

Module này giữ một định nghĩa duy nhất cho hai đại lượng:

- **`persona_tokens`** — phần dự án tự sinh và tự dán vào preset.
- **`SYSTEM_OVERHEAD_TOKENS`** — phần harness luôn nối vào trước/sau persona mà dự án
  không gỡ được. Nó vẫn tĩnh và byte-identical giữa các lượt, nên vẫn trúng cache;
  bỏ nó khỏi dự toán chỉ làm sai con số, không làm rẻ đi.

Bất biến quan trọng nhất ở đây là **`persona` trong preset phải giống hệt tệp prefix
đã sinh, từng byte**. Chỉ lệch một khoảng trắng là toàn bộ phần sau nó trượt bộ nhớ
đệm, mà không có tín hiệu nào báo: hoá đơn vẫn chạy, chỉ đắt hơn 50 lần ở phần lẽ ra
phải rẻ. Trước đây `--check` chỉ so tệp với danh mục, tức thứ duy nhất bắt buộc giống
nhau lại là thứ duy nhất không ai kiểm.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent

PREFIX_DIR = PROJECT_ROOT / "data" / "prefix"
PREFIX_PATH = PREFIX_DIR / "ARTICLE_SYSTEM_CORE.md"
PREFIX_META = PREFIX_DIR / "ARTICLE_SYSTEM_CORE.meta.json"

PRESET_PATH = (REPO_ROOT / ".agents" / "dsh" / "presets" / "news-scape-conductor"
               / "agent.cordis.yml")
WORKER_ROW_ID = "tool-subagent-article"

# Quy đổi ký tự sang token, dùng chung với `src/agent/distill.py`.
CHARS_PER_TOKEN = 3

# Dùng khi chưa sinh prefix. Không phải một định mức, chỉ là chỗ dựa để dự toán không
# bằng không khi chạy trước lần sinh đầu tiên.
DEFAULT_PERSONA_TOKENS = 6400

# Phần tĩnh do harness nối thêm vào mỗi request của worker, dự án KHÔNG gỡ được:
#
#   AGENTS.md nạp lại cho mọi agent kể cả con   ~4.069 token   (plan §4.2 R2)
#   section `tools:ptc-only` + `tools:sdk`        ~640 token   (plan §4.2 R3)
#   harness identity + persona suffix              ~90 token
#
# Cả ba đều nằm TRƯỚC packet và không đổi giữa các lượt, nên chúng trúng cache y hệt
# phần persona. Đưa vào dự toán để `est_hit` so được với `cacheReadTokens` thật.
SYSTEM_OVERHEAD_TOKENS = 4_800


class _LenientLoader(yaml.SafeLoader):
    """Bộ đọc YAML bỏ qua các thẻ riêng của composition thay vì ném lỗi.

    Preset DSH dùng thẻ `!!js` cho vài trường điều kiện. `yaml.safe_load` từ chối
    chúng, mà ở đây chỉ cần đọc đúng một chuỗi `persona`, nên mọi thẻ lạ được đọc
    thành `None`.
    """


_LenientLoader.add_multi_constructor(
    None, lambda loader, suffix, node: None)


def read_meta() -> dict:
    """Đọc mô tả của prefix đang nằm trên đĩa.

    Returns:
        Từ điển mô tả, hoặc từ điển rỗng khi chưa sinh prefix hoặc tệp hỏng.
    """
    try:
        with open(PREFIX_META, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def prefix_hash() -> str | None:
    """Lấy giá trị băm của prefix đang dùng.

    Returns:
        Chuỗi băm, hoặc None khi chưa sinh prefix.
    """
    return read_meta().get("hash")


def prefix_variants() -> dict:
    """Lấy các biến thể đã bật khi sinh prefix đang nằm trên đĩa.

    Biến thể được ghi lại để chế độ kiểm dựng lại đúng nội dung ấy. Không có nó thì
    một prefix sinh kèm digest mã chứng khoán sẽ bị báo "lệch danh mục" ở mọi lần
    kiểm, dù nó hoàn toàn đúng.

    Returns:
        Từ điển biến thể, rỗng khi prefix ở dạng mặc định.
    """
    variants = read_meta().get("variants")
    return variants if isinstance(variants, dict) else {}


def persona_tokens() -> int:
    """Lấy kích thước phần persona của prefix.

    Returns:
        Số token ước lượng của persona, hoặc giá trị mặc định khi chưa sinh prefix.
    """
    try:
        return int(read_meta().get("approx_tokens") or DEFAULT_PERSONA_TOKENS)
    except (TypeError, ValueError):
        return DEFAULT_PERSONA_TOKENS


def cached_prefix_tokens() -> int:
    """Tổng số token tĩnh đứng trước packet trong mỗi request của worker.

    Đây là con số phải đối chiếu với `cacheReadTokens` thật: từ lượt gọi thứ hai trở
    đi, mỗi lượt phải đọc lại xấp xỉ bấy nhiêu token ở giá trúng cache.

    Returns:
        Tổng token của persona cộng phần harness nối thêm.
    """
    return persona_tokens() + SYSTEM_OVERHEAD_TOKENS


def persona_from_preset(path: str | Path | None = None,
                        row_id: str = WORKER_ROW_ID) -> str | None:
    """Bóc chuỗi `persona` của một row subagent trong preset.

    Args:
        path: Đường dẫn tệp preset. Mặc định dùng preset của dự án.
        row_id: Mã row cần bóc.

    Returns:
        Nội dung persona, hoặc None khi không có tệp, không có row, hoặc row không
        khai persona.
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
    """Tính giá trị băm rút gọn của một nội dung prefix.

    Args:
        content: Toàn văn prefix.

    Returns:
        Mười sáu ký tự đầu của SHA256.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def compare_persona(content: str, path: str | Path | None = None) -> tuple[bool, str]:
    """Đối chiếu persona trong preset với nội dung prefix chuẩn.

    So sánh sau khi bỏ khoảng trắng ở hai đầu, vì bộ đọc YAML luôn chuẩn hoá ký tự
    xuống dòng cuối khối. Mọi khác biệt bên trong đều tính là lệch.

    Args:
        content: Nội dung prefix chuẩn, thường là bản vừa sinh từ danh mục.
        path: Đường dẫn preset. Mặc định dùng preset của dự án.

    Returns:
        Cặp gồm kết quả khớp và một dòng mô tả để in ra cho người vận hành.
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
