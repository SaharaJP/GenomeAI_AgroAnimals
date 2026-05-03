from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'configs' / 'post_removal' / 'streamlit_removal_regression_report_v1.json'


def main() -> int:
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    must_absent = [ROOT / 'streamlit_app', ROOT / '.streamlit', ROOT / 'scripts' / 'run_streamlit.sh']
    if any(p.exists() for p in must_absent):
        raise SystemExit('streamlit legacy artifacts still present')
    text_hits = []
    for path in [ROOT / 'pyproject.toml', ROOT / 'deploy' / 'docker-compose.yml', ROOT / 'src' / 'genomeai' / 'app_launcher.py']:
        txt = path.read_text(encoding='utf-8') if path.exists() else ''
        if 'streamlit' in txt.lower():
            text_hits.append(str(path.relative_to(ROOT)))
    if text_hits:
        raise SystemExit(f'active runtime references still contain streamlit: {text_hits}')
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
