from pathlib import Path


def test_t32_07_extended_surface_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = [
        root / 'web_app' / 'app' / '(protected)' / 'reproduction' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'vet' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'treatments' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'economics' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'support' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'pilot' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'readiness' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'observability' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'admin' / 'page.tsx',
        root / 'web_app' / 'components' / 'extended' / 'reproduction-surface.tsx',
        root / 'web_app' / 'components' / 'extended' / 'vet-queues-surface.tsx',
        root / 'web_app' / 'components' / 'extended' / 'treatments-withdrawal-surface.tsx',
        root / 'web_app' / 'components' / 'extended' / 'economics-master-surface.tsx',
        root / 'web_app' / 'components' / 'extended' / 'support-governance-surface.tsx',
        root / 'web_app' / 'components' / 'extended' / 'pilot-readiness-surface.tsx',
        root / 'web_app' / 'components' / 'extended' / 'admin-command-center.tsx',
        root / 'web_app' / 'components' / 'extended' / 'observability-surface.tsx',
        root / 'web_app' / 'lib' / 'api' / 'extended-surfaces.ts',
        root / 'web_app' / 'app' / 'api' / 'admin' / 'permission-matrix' / 'route.ts',
        root / 'web_app' / 'app' / 'api' / 'observability' / 'route.ts',
        root / 'docs' / 'react_extended_surface_parity.md',
    ]
    missing = [str(path.relative_to(root)) for path in expected if not path.exists()]
    assert not missing, f'Missing T32-07 artifacts: {missing}'


def test_t32_07_docs_state_office_master_system_scope() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / 'docs' / 'react_extended_surface_parity.md').read_text(encoding='utf-8')
    assert 'полный офисный/управленческий пользовательский контур' in doc
    assert 'backend evidence' in doc
    assert 'React-only shortcuts' in doc
    assert 'master system shell' in doc


def test_t32_07_navigation_contains_extended_routes() -> None:
    root = Path(__file__).resolve().parents[1]
    nav = (root / 'web_app' / 'lib' / 'navigation.ts').read_text(encoding='utf-8')
    for route in ['/reproduction', '/vet', '/treatments', '/economics', '/support', '/pilot', '/readiness', '/observability', '/admin']:
        assert route in nav


def test_t32_07_bff_routes_stay_server_side() -> None:
    root = Path(__file__).resolve().parents[1]
    admin_route = (root / 'web_app' / 'app' / 'api' / 'admin' / 'permission-matrix' / 'route.ts').read_text(encoding='utf-8')
    observability_route = (root / 'web_app' / 'app' / 'api' / 'observability' / 'route.ts').read_text(encoding='utf-8')
    assert 'backendFetch' in admin_route
    assert '/api/admin/permission-matrix' in admin_route
    assert 'backendFetch' in observability_route
    assert '/api/observability' in observability_route


def test_t32_07_extended_surfaces_keep_backend_first_posture() -> None:
    root = Path(__file__).resolve().parents[1]
    reproduction = (root / 'web_app' / 'components' / 'extended' / 'reproduction-surface.tsx').read_text(encoding='utf-8')
    admin = (root / 'web_app' / 'components' / 'extended' / 'admin-command-center.tsx').read_text(encoding='utf-8')
    api = (root / 'web_app' / 'lib' / 'api' / 'extended-surfaces.ts').read_text(encoding='utf-8')
    assert 'No reproduction logic is reimplemented in the browser' in reproduction
    assert 'backend evidence' in admin
    assert 'fetchExtendedBundle' in api
    assert '/api/admin/permission-matrix' in api
    assert '/api/observability' in api
