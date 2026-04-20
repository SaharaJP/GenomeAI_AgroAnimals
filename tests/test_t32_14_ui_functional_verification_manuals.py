from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t32_14_docs_exist() -> None:
    required = [
        ROOT / 'docs' / 'ui_functional_verification_web.md',
        ROOT / 'docs' / 'ui_functional_verification_android.md',
        ROOT / 'docs' / 'full_uat_checklist.md',
        ROOT / 'scripts' / 'validate_t32_14_ui_verification_manuals.py',
        ROOT / 'scripts' / 'smoke_t32_14_ui_verification_manuals.sh',
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    assert not missing, f'Missing T32-14 artifacts: {missing}'


def test_t32_14_web_manual_is_role_based_and_honest() -> None:
    doc = (ROOT / 'docs' / 'ui_functional_verification_web.md').read_text(encoding='utf-8')
    for token in [
        'Admin',
        'Director',
        'Operator / Zootech',
        'Vet',
        'Viewer / bounded external role',
        'preview parity',
        'thin resolution shell',
        '/profiles/animal/DEMO_COW_1002',
        '/profiles/group/PEN_N1_LACT',
    ]:
        assert token in doc


def test_t32_14_android_manual_references_role_switch_and_offline_smokes() -> None:
    doc = (ROOT / 'docs' / 'ui_functional_verification_android.md').read_text(encoding='utf-8')
    for token in [
        'Роль для UI-проверки',
        'HerdManager',
        'Veterinarian',
        'ReproductionSpecialist',
        'Viewer',
        'Admin',
        'bash scripts/smoke_t32_08_android_field_app.sh',
        'bash scripts/smoke_t32_08a_android_offline_sync_contract.sh',
        'bash scripts/smoke_t32_09_android_offline_sync_model.sh',
    ]:
        assert token in doc


def test_t32_14_full_uat_has_web_and_android_scenarios() -> None:
    doc = (ROOT / 'docs' / 'full_uat_checklist.md').read_text(encoding='utf-8')
    for token in [
        'WEB-AUTH-001',
        'WEB-REPORT-002',
        'WEB-READINESS-001',
        'AND-AUTH-001',
        'AND-HANDOVER-001',
        'AND-OFFLINE-001',
        'GO / No-Go summary',
    ]:
        assert token in doc
