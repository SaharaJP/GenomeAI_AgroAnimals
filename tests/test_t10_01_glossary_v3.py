from pathlib import Path

from streamlit_app.glossary_v3 import load_glossary, get_tooltip


def test_glossary_v3_tooltip_present_for_versions():
    cfg = load_glossary(Path("configs/ui/glossary_v3.yaml"))
    tip = get_tooltip(cfg, "data_version")
    assert tip is not None
    assert "Версия" in tip or "версия" in tip


def test_glossary_v3_missing_key_returns_none():
    cfg = load_glossary(Path("configs/ui/glossary_v3.yaml"))
    assert get_tooltip(cfg, "___no_such_key___") is None
