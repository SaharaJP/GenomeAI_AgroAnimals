from pathlib import Path


def test_t18_01_streamlit_app_uses_navigation_shell() -> None:
    text = Path("streamlit_app/app.py").read_text(encoding="utf-8")
    assert "st.navigation" in text
    assert "_unified_shell_active" in text
