"""Kiểm tra tính hợp lệ của manifest và cấu trúc thư mục plugin fpts-market-intel."""

from __future__ import annotations

import json
from pathlib import Path
import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "fpts-market-intel"


def test_plugin_json_schema():
    """Kiểm tra plugin.json có cú pháp hợp lệ và đầy đủ các trường bắt buộc."""
    manifest_file = PLUGIN_ROOT / "plugin.json"
    assert manifest_file.exists(), f"Thiếu tệp {manifest_file}"

    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert data.get("name") == "fpts-market-intel"
    assert "description" in data and len(data["description"]) > 10
    assert "suggestedPrompts" in data
    assert isinstance(data["suggestedPrompts"], list)
    assert len(data["suggestedPrompts"]) >= 3


def test_plugin_rules_and_tools():
    """Kiểm tra các tệp quy chuẩn và công cụ thực thi có mặt đầy đủ."""
    assert (PLUGIN_ROOT / "README.md").exists()
    assert (PLUGIN_ROOT / "rules" / "AGENTS.md").exists()
    assert (PLUGIN_ROOT / "tools" / "lakehouse_client.py").exists()

    rule_text = (PLUGIN_ROOT / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert "Zero Hallucination" in rule_text or "Căn Cứ Dữ Liệu" in rule_text
    assert "BOTH" in rule_text and "LLM_ONLY" in rule_text


def test_plugin_skills_catalog():
    """Kiểm tra mọi kỹ năng nghiệp vụ theo team đều có SKILL.md với frontmatter chuẩn."""
    expected_skills = [
        "news-ticker-screener",
        "news-ticker-timeline",
        "news-catalyst-tracker",
        "news-sector-impact",
        "news-buzz-radar",
        "news-sentiment-pulse",
        "news-price-explainer",
        "news-macro-timeline",
        "news-theme-trend",
        "news-geo-link",
        "news-daily-brief",
        "news-lakehouse-explorer",
    ]
    present = {p.name for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir()}
    assert present == set(expected_skills)

    for skill_name in expected_skills:
        skill_file = PLUGIN_ROOT / "skills" / skill_name / "SKILL.md"
        assert skill_file.exists(), f"Thiếu tệp {skill_file}"

        content = skill_file.read_text(encoding="utf-8")
        assert content.startswith("---"), f"Thiếu frontmatter YAML trong {skill_file}"

        parts = content.split("---", 2)
        assert len(parts) >= 3, f"Frontmatter không đóng đúng cách trong {skill_file}"

        meta = yaml.safe_load(parts[1])
        assert meta.get("name") == skill_name, f"Tên skill không khớp trong {skill_file}"
        assert "description" in meta and len(meta["description"]) > 10


def test_skill_commands_exist_in_client():
    """Kiểm tra mọi lệnh lens được SKILL.md gọi đều là lệnh con hợp lệ của lakehouse_client."""
    import re
    import sys

    sys.path.insert(0, str(PLUGIN_ROOT / "tools"))
    from lakehouse_client import build_parser

    sub = next(a for a in build_parser()._actions if a.dest == "action")
    valid = set(sub.choices)
    for skill_file in (PLUGIN_ROOT / "skills").glob("*/SKILL.md"):
        text = skill_file.read_text(encoding="utf-8")
        for cmd in re.findall(r"python \$LH ([a-z-]+)", text):
            assert cmd in valid, f"{skill_file.parent.name} gọi lệnh không tồn tại: {cmd}"


def test_themes_config_valid():
    """Kiểm tra `config/themes.json` có cấu trúc hợp lệ và mã thực thể đúng dạng KIND:CODE."""
    data = json.loads((PLUGIN_ROOT / "config" / "themes.json").read_text(encoding="utf-8"))
    assert data["themes"]
    for key, th in data["themes"].items():
        assert th.get("label"), key
        assert th.get("entities") or th.get("keywords"), key
        assert all(":" in e and e == e.upper() for e in th.get("entities", [])), key
