from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / 'configs' / 'post_removal' / 'streamlit_legacy_cleanup_manifest_v1.json'
REPORT_PATH = ROOT / 'configs' / 'post_removal' / 'streamlit_legacy_cleanup_report_v1.json'
DOC_PATH = ROOT / 'docs' / 'streamlit_legacy_cleanup_gate.md'
TOKENS = ['streamlit', '8501', 'STREAMLIT_']
IMPORT_PATTERNS = [
    re.compile(r'(^|\W)import\s+streamlit(\W|$)', re.M),
    re.compile(r'(^|\W)from\s+streamlit(\W|$)', re.M),
    re.compile(r'streamlit_app'),
]


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return None


def _is_allowed(rel_path: str, allowed_globs: list[str]) -> bool:
    return any(fnmatch(rel_path, pat) for pat in allowed_globs)


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    allowed_globs = manifest['allowed_historical_globs']

    required_absent_failures: list[str] = []
    for rel in manifest['required_absent_paths']:
        if (ROOT / rel).exists():
            required_absent_failures.append(rel)

    dependency_hits: list[dict[str, str]] = []
    for rel in manifest['dependency_files']:
        path = ROOT / rel
        if not path.exists():
            continue
        text = _read_text(path) or ''
        if re.search(r'(?i)(^|[^a-z0-9_])streamlit([^a-z0-9_]|$)', text):
            dependency_hits.append({'path': rel, 'reason': 'streamlit dependency or reference in deployment/dependency file'})

    import_hits: list[dict[str, str]] = []
    for root_rel in manifest['runtime_import_roots']:
        root = ROOT / root_rel
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            if '__pycache__' in path.parts or path.suffix in {'.png', '.jpg', '.jpeg', '.woff', '.woff2', '.ico', '.db'}:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if _is_allowed(rel, allowed_globs):
                continue
            text = _read_text(path)
            if text is None:
                continue
            if any(p.search(text) for p in IMPORT_PATTERNS):
                import_hits.append({'path': rel, 'reason': 'runtime import or direct streamlit_app reference'})

    disallowed_operational_refs: list[dict[str, str]] = []
    allowed_historical_refs: list[dict[str, str]] = []
    for root_rel in manifest['operational_scan_roots']:
        root = ROOT / root_rel
        candidates = [root] if root.is_file() else list(root.rglob('*')) if root.exists() else []
        for path in candidates:
            if not path.is_file():
                continue
            if '__pycache__' in path.parts or path.suffix in {'.png', '.jpg', '.jpeg', '.woff', '.woff2', '.ico', '.db'}:
                continue
            rel = path.relative_to(ROOT).as_posix()
            text = _read_text(path)
            if text is None:
                continue
            token_hits = [tok for tok in TOKENS if tok.lower() in text.lower()]
            if not token_hits:
                continue
            record = {'path': rel, 'tokens': sorted(set(token_hits))}
            if _is_allowed(rel, allowed_globs):
                allowed_historical_refs.append(record)
            else:
                disallowed_operational_refs.append(record)

    checks = {
        'required_absent_paths': not required_absent_failures,
        'dependency_files_clean': not dependency_hits,
        'runtime_imports_clean': not import_hits,
        'operational_refs_clean': not disallowed_operational_refs,
        'docs_gate_exists': DOC_PATH.exists(),
        'manifest_exists': MANIFEST_PATH.exists(),
    }

    status = 'pass' if all(checks.values()) else 'fail'
    report = {
        'schema': 'genomeai.post_removal.streamlit_legacy_cleanup_report.v1',
        'gate_id': 'T32-12A',
        'status': status,
        'streamlit_contour_fully_removed': status == 'pass',
        'required_absent_failures': required_absent_failures,
        'dependency_hits': dependency_hits,
        'runtime_import_hits': import_hits,
        'disallowed_operational_refs': disallowed_operational_refs,
        'allowed_historical_ref_count': len(allowed_historical_refs),
        'allowed_historical_refs_sample': allowed_historical_refs[:40],
        'checks': checks,
        'archive_manifest': manifest['archive_manifest'],
        'notes': [
            'Historical/evidence references are allowed only by explicit manifest allowlist.',
            'Active product/deployment/config paths must remain free of Streamlit tails.',
            'Validator checks absence paths, dependency files, runtime imports and disallowed operational references.'
        ]
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'status': status,
        'streamlit_contour_fully_removed': report['streamlit_contour_fully_removed'],
        'allowed_historical_ref_count': report['allowed_historical_ref_count'],
        'disallowed_operational_ref_count': len(disallowed_operational_refs),
        'runtime_import_hit_count': len(import_hits),
        'dependency_hit_count': len(dependency_hits),
    }, ensure_ascii=False))
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
