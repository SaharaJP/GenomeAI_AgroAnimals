from __future__ import annotations

from pathlib import Path

from streamlit_app.mobile_shell_pwa import build_pwa_bootstrap_html, build_pwa_manifest, resolve_mobile_preferences


def test_t25_01_resolve_mobile_preferences_respects_query_params_and_session() -> None:
    prefs = resolve_mobile_preferences(
        session_state={"ui.mobile_mode": False, "ui.compact_mode": False},
        query_params={"mobile": "1", "compact": "1"},
    )
    assert prefs == {"mobile_mode": True, "compact_mode": True}

    prefs2 = resolve_mobile_preferences(
        session_state={"ui.mobile_mode": True, "ui.compact_mode": False},
        query_params={},
    )
    assert prefs2 == {"mobile_mode": True, "compact_mode": False}


def test_t25_01_pwa_manifest_and_bootstrap_are_bounded_and_installable() -> None:
    manifest = build_pwa_manifest(asset_base="/static/pwa")
    assert manifest["short_name"] == "GenomeAI"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/?mobile=1"
    assert manifest["icons"][0]["src"] == "/static/pwa/icon-any.svg"

    html = build_pwa_bootstrap_html(asset_base="/static/pwa")
    assert 'manifest.webmanifest' in html
    assert 'serviceWorker.register' in html
    assert 'beforeinstallprompt' in html
    assert 'apple-mobile-web-app-capable' in html


def test_t25_01_common_bootstraps_mobile_foundation_and_auth_hint() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / 'streamlit_app' / 'common.py').read_text(encoding='utf-8')
    assert 'ensure_mobile_shell_foundation' in text
    assert 'render_mobile_shell_toolbar' in text
    assert 'render_mobile_auth_hint' in text


def test_t25_01_key_daily_use_pages_expose_mobile_record_actions() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in [
        'streamlit_app/pages/15_Animal_Profile.py',
        'streamlit_app/pages/14_Group_Profile.py',
        'streamlit_app/pages/43_Daily_Worklists_By_Role.py',
    ]:
        text = (root / rel).read_text(encoding='utf-8')
        assert 'render_mobile_record_actions' in text, rel


def test_t25_01_static_assets_and_docs_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / '.streamlit' / 'config.toml').exists()
    assert (root / 'static' / 'pwa' / 'manifest.webmanifest').exists()
    assert (root / 'static' / 'pwa' / 'sw.js').exists()
    assert (root / 'docs' / 'mobile_shell_pwa_foundation.md').exists()
