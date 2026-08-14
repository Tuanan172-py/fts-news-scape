"""
Shared pytest config.

Chỉ đảm bảo project root trên sys.path (đồng nhất với các test cũ) và cho phép
import `_fakes`. KHÔNG chdir toàn cục — vài module (notifier/sentiment) load config
theo đường dẫn tương đối; capture tests tự cô lập raw_dir qua fixture `env` của
chúng (monkeypatch.chdir).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
