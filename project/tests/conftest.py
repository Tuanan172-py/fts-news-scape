"""Cô lập bộ test khỏi dữ liệu vận hành và đặt project root lên sys.path.

Trước khi module test nào được import, `MONOCLE_DATA_DIR` và `MONOCLE_DB_PATH` trỏ vào
một thư mục tạm, nên mọi đường phân giải mặc định (kể cả script con gọi qua subprocess)
ghi vào đó. Một chốt chặn trên `sqlite3.connect` làm test thất bại ngay khi có kết nối
tới thư mục dữ liệu vận hành hoặc `harness.db` của kho.

Danh mục thực thể thu nhỏ `tests/fixtures/entities_min.json` được chép vào thư mục tạm
đó, nên mọi test dùng `load_registry()` chạy được trên bản clone sạch.

Không chdir toàn cục: vài module (notifier, sentiment) tải config theo đường dẫn tương
đối; capture tests tự cô lập `raw_dir` qua fixture `env` của chúng (monkeypatch.chdir).
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="news-scape-test-"))
os.environ["MONOCLE_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["MONOCLE_DB_PATH"] = str(_TEST_DATA_DIR / "monocle.db")
os.environ.pop("MONOCLE_ALLOW_SYNCED_DB", None)
os.environ.pop("NEWS_SCAPE_SUBSCRIPTIONS_DIR", None)

_ENTITIES_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "entities_min.json"
(_TEST_DATA_DIR / "entities").mkdir(parents=True, exist_ok=True)
(_TEST_DATA_DIR / "entities" / "entities.json").write_bytes(_ENTITIES_FIXTURE.read_bytes())

import pytest  # noqa: E402
from src.core.config import OPERATIONAL_DB_PATH  # noqa: E402
from src.crawler.backoff import SourceBackoff  # noqa: E402

_PROTECTED_ROOTS = (
    OPERATIONAL_DB_PATH.parent.resolve(),
    Path(r"C:\data\news-scape").resolve(),
)
_PROTECTED_FILES = ((PROJECT_ROOT.parent / "harness.db").resolve(),)
_real_connect = sqlite3.connect


def _is_protected(database: object) -> bool:
    """Cho biết tham số `database` của sqlite3.connect có trỏ vào dữ liệu vận hành không.

    Args:
        database: Tham số đầu tiên truyền cho `sqlite3.connect` (str, bytes hoặc Path).

    Returns:
        True khi đường dẫn nằm dưới thư mục dữ liệu vận hành hoặc là `harness.db` của kho.
    """
    if isinstance(database, bytes):
        database = database.decode(errors="ignore")
    raw = str(database)
    if raw.startswith("file:"):
        raw = raw[5:].split("?", 1)[0]
    if not raw or raw == ":memory:":
        return False
    try:
        p = Path(raw).resolve()
    except (OSError, ValueError):
        return False
    if p in _PROTECTED_FILES:
        return True
    return any(p == root or root in p.parents for root in _PROTECTED_ROOTS)


def _guarded_connect(database, *args, **kwargs):
    """Mở kết nối SQLite, từ chối đường dẫn thuộc dữ liệu vận hành.

    Raises:
        RuntimeError: Khi test mở DB vận hành hoặc `harness.db` của kho.
    """
    if _is_protected(database):
        raise RuntimeError(
            f"Test mở DB vận hành {database}. Truyền db_path trong tmp_path hoặc dùng "
            f"MONOCLE_DATA_DIR={_TEST_DATA_DIR}."
        )
    return _real_connect(database, *args, **kwargs)


sqlite3.connect = _guarded_connect


@pytest.fixture(autouse=True)
def fast_tests(monkeypatch):
    """Disable backoff sleep during tests to run suite instantaneously."""
    monkeypatch.setattr(SourceBackoff, "before_fetch", lambda self, domain: None)
