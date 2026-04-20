from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t34_06_android_auth_runtime_files_exist():
    required = [
        ROOT / 'docs' / 'android_auth_runtime_integration.md',
        ROOT / 'scripts' / 'smoke_t34_06_android_auth_runtime.sh',
        ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'auth' / 'AuthContracts.kt',
        ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'auth' / 'AuthDiagnostics.kt',
        ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'auth' / 'ServerAuthRepository.kt',
        ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'auth' / 'AuthSessionManager.kt',
        ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'data' / 'local' / 'PreferencesSessionStore.kt',
        ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'ui' / 'screens' / 'AuthDiagnosticsScreen.kt',
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    assert not missing, f"Missing T34-06 files: {missing}"


def test_t34_06_docs_forbid_fake_mobile_auth_paths():
    doc = (ROOT / 'docs' / 'android_auth_runtime_integration.md').read_text(encoding='utf-8').lower()
    assert 'нет local role picker' in doc
    assert 'нет webview wrapper' in doc
    assert 'нет mock auth storage' in doc
    assert '/api/app/v1/auth/mobile/runtime-proof' in doc


def test_t34_06_android_shell_uses_server_auth_and_real_session_store():
    login = (ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'ui' / 'screens' / 'LoginScreen.kt').read_text(encoding='utf-8')
    shell = (ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'ui' / 'shell' / 'AppShell.kt').read_text(encoding='utf-8')
    app = (ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'GenomeAiMobileApp.kt').read_text(encoding='utf-8')
    repo = (ROOT / 'mobile_android' / 'app' / 'src' / 'main' / 'java' / 'com' / 'genomeai' / 'agroanimals' / 'mobile' / 'auth' / 'ServerAuthRepository.kt').read_text(encoding='utf-8')

    assert 'Роль для UI-проверки' not in login
    assert 'selectedRole' not in login
    assert 'authSessionManager.login' in shell
    assert 'authSessionManager.refresh' in shell
    assert 'authSessionManager.logout' in shell
    assert 'PreferencesSessionStore' in app
    assert 'ServerAuthRepository' in app
    assert '/api/app/v1/auth/login' in repo
    assert '/api/app/v1/auth/refresh' in repo
    assert '/api/app/v1/auth/logout' in repo
    assert '/api/app/v1/auth/mobile/runtime-proof' in repo
