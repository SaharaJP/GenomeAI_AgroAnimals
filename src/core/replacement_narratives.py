from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from core.commercial_packaging import load_commercial_packaging_config, load_runtime_packaging_context
from core.demo_farm import load_demo_scenarios_config
from core.observability.competitive_acceptance import load_competitive_acceptance_policy
def load_ia_config(path):
    return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}

_DEFAULT_CFG = Path('configs/product/replacement_narratives_v1.yaml')


@dataclass(frozen=True)
class ResolvedNavRef:
    key: str
    label: str
    page: str


@dataclass(frozen=True)
class ProofPoint:
    key: str
    title: str
    statement: str
    enabled: bool
    required_features: tuple[str, ...]
    nav_refs: tuple[ResolvedNavRef, ...]
    source_docs: tuple[str, ...]
    source_tests: tuple[str, ...]
    source_scripts: tuple[str, ...]
    acceptance_scenarios: tuple[str, ...]
    demo_scenarios: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            'nav_refs': [asdict(x) for x in self.nav_refs],
        }


def _norm_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    return [str(value).strip()]


def _validate_cfg(cfg: Mapping[str, Any]) -> None:
    if not isinstance(cfg, Mapping):
        raise ValueError('Replacement narratives config must be a mapping')
    if int(cfg.get('version', 0)) != 1:
        raise ValueError('Replacement narratives config version must be 1')
    if not isinstance(cfg.get('themes'), Mapping) or not cfg.get('themes'):
        raise ValueError("Replacement narratives config must contain non-empty 'themes'")
    if not isinstance(cfg.get('proof_points'), Mapping) or not cfg.get('proof_points'):
        raise ValueError("Replacement narratives config must contain non-empty 'proof_points'")
    if not isinstance(cfg.get('compare_checklists'), Mapping) or not cfg.get('compare_checklists'):
        raise ValueError("Replacement narratives config must contain non-empty 'compare_checklists'")
    if not isinstance(cfg.get('feature_maps'), Mapping) or not cfg.get('feature_maps'):
        raise ValueError("Replacement narratives config must contain non-empty 'feature_maps'")


def load_replacement_narratives_config(path: str | Path = _DEFAULT_CFG) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'Replacement narratives config not found: {p}')
    cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    _validate_cfg(cfg)
    return cfg


def _collect_nav(cfg: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for group in cfg.get('nav') or []:
        if not isinstance(group, Mapping):
            continue
        for item in group.get('items') or []:
            if not isinstance(item, Mapping):
                continue
            key = str(item.get('key') or '').strip()
            if not key:
                continue
            page = str(item.get('page') or item.get('page_by_role', {}).get('default') or item.get('page_by_role', {}).get('Viewer') or '').strip()
            out[key] = {
                'key': key,
                'label': str(item.get('label') or key),
                'page': page,
            }
    return out


def _demo_scenario_index(cfg: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for role, role_cfg in (cfg.get('roles') or {}).items():
        if not isinstance(role_cfg, Mapping):
            continue
        for scenario in role_cfg.get('scenarios') or []:
            if not isinstance(scenario, Mapping):
                continue
            sid = str(scenario.get('scenario_id') or '').strip()
            if sid:
                out[sid] = {'role': str(role), 'title': str(scenario.get('title') or sid)}
    return out


def build_replacement_narratives_summary(*, project_root: str | Path = '.', config_path: str | Path | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve()
    cfg_path = Path(config_path).resolve() if config_path is not None else (root / _DEFAULT_CFG).resolve()
    cfg = load_replacement_narratives_config(cfg_path)
    packaging_cfg = load_commercial_packaging_config(root / 'configs' / 'product' / 'commercial_packaging_v1.yaml')
    packaging = load_runtime_packaging_context(project_root=root, env=env)
    ia_cfg = load_ia_config(root / 'configs' / 'ui' / 'ia_v3.yaml')
    nav = _collect_nav(ia_cfg)
    acceptance = load_competitive_acceptance_policy(project_root=root, profile=str(cfg.get('default_profile') or 'legacy_replacement_ci'))
    acceptance_scenarios = set((acceptance.get('profile') or {}).keys())
    demo_cfg = load_demo_scenarios_config(root / 'configs' / 'ui' / 'demo_farm_scenarios_v1.yaml')
    demo_scenarios = _demo_scenario_index(demo_cfg)
    feature_catalog = set((packaging_cfg.get('feature_catalog') or {}).keys())

    proof_points: dict[str, ProofPoint] = {}
    for key, meta in (cfg.get('proof_points') or {}).items():
        if not isinstance(meta, Mapping):
            continue
        required_features = tuple(_norm_list(meta.get('required_features')))
        unknown_features = [f for f in required_features if f not in feature_catalog]
        if unknown_features:
            raise ValueError(f'Unknown required_features for {key}: {unknown_features}')
        nav_keys = _norm_list(meta.get('source_nav_keys'))
        nav_refs: list[ResolvedNavRef] = []
        for nav_key in nav_keys:
            item = nav.get(nav_key)
            if item is None:
                raise ValueError(f'Unknown nav key for {key}: {nav_key}')
            nav_refs.append(ResolvedNavRef(key=nav_key, label=item['label'], page=item['page']))
        source_docs = tuple(_norm_list(meta.get('source_docs')))
        source_tests = tuple(_norm_list(meta.get('source_tests')))
        source_scripts = tuple(_norm_list(meta.get('source_scripts')))
        for rel in [*source_docs, *source_tests, *source_scripts]:
            if not (root / rel).exists():
                raise FileNotFoundError(f'{key}: missing source file {rel}')
        acc = tuple(_norm_list(meta.get('acceptance_scenarios')))
        for scenario in acc:
            if scenario not in acceptance_scenarios:
                raise ValueError(f'{key}: unknown acceptance scenario {scenario}')
        demo = tuple(_norm_list(meta.get('demo_scenarios')))
        for scenario in demo:
            if scenario not in demo_scenarios:
                raise ValueError(f'{key}: unknown demo scenario {scenario}')
        enabled = all(f in set(packaging.enabled_features) for f in required_features)
        proof_points[str(key)] = ProofPoint(
            key=str(key),
            title=str(meta.get('title') or key),
            statement=str(meta.get('statement') or '').strip(),
            enabled=enabled,
            required_features=required_features,
            nav_refs=tuple(nav_refs),
            source_docs=source_docs,
            source_tests=source_tests,
            source_scripts=source_scripts,
            acceptance_scenarios=acc,
            demo_scenarios=demo,
        )

    themes: list[dict[str, Any]] = []
    for key, meta in (cfg.get('themes') or {}).items():
        if not isinstance(meta, Mapping):
            continue
        pp_keys = [pp for pp in _norm_list(meta.get('proof_points')) if pp in proof_points]
        themes.append({
            'theme_key': str(key),
            'title': str(meta.get('title') or key),
            'summary': str(meta.get('summary') or '').strip(),
            'why_it_wins': str(meta.get('why_it_wins') or '').strip(),
            'not_claimed': _norm_list(meta.get('not_claimed')),
            'proof_points': [proof_points[pp].as_dict() for pp in pp_keys],
        })

    compare_checklists: list[dict[str, Any]] = []
    for key, meta in (cfg.get('compare_checklists') or {}).items():
        if not isinstance(meta, Mapping):
            continue
        rows = []
        for row in meta.get('entries') or []:
            if not isinstance(row, Mapping):
                continue
            pp_keys = [pp for pp in _norm_list(row.get('proof_points')) if pp in proof_points]
            rows.append({
                'question': str(row.get('question') or '').strip(),
                'proof_points': [proof_points[pp].as_dict() for pp in pp_keys],
            })
        compare_checklists.append({
            'checklist_key': str(key),
            'title': str(meta.get('title') or key),
            'audience': str(meta.get('audience') or '').strip(),
            'entries': rows,
        })

    feature_maps: list[dict[str, Any]] = []
    for key, meta in (cfg.get('feature_maps') or {}).items():
        if not isinstance(meta, Mapping):
            continue
        rows = []
        for row in meta.get('entries') or []:
            if not isinstance(row, Mapping):
                continue
            nav_refs = []
            for nav_key in _norm_list(row.get('genomeai_surfaces')):
                item = nav.get(nav_key)
                if item is None:
                    raise ValueError(f'Unknown feature map nav key {nav_key} in {key}')
                nav_refs.append(item)
            pp_keys = [pp for pp in _norm_list(row.get('proof_points')) if pp in proof_points]
            rows.append({
                'legacy_capability': str(row.get('legacy_capability') or row.get('win_theme') or '').strip(),
                'genomeai_surfaces': nav_refs,
                'proof_points': [proof_points[pp].as_dict() for pp in pp_keys],
            })
        feature_maps.append({
            'map_key': str(key),
            'title': str(meta.get('title') or key),
            'entries': rows,
        })

    return {
        'config_version': int(cfg.get('version', 1)),
        'profile_name': str(cfg.get('default_profile') or 'legacy_replacement_ci'),
        'runtime_packaging': packaging.as_dict(),
        'themes': themes,
        'compare_checklists': compare_checklists,
        'feature_maps': feature_maps,
        'proof_points': {k: v.as_dict() for k, v in proof_points.items()},
        'source_statement': 'All proof points are linked to actual pages, docs, tests, scripts, acceptance scenarios or runnable demo scenarios in the current product.',
    }


def render_replacement_narratives_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        '# Replacement narratives and win themes',
        '',
        str(summary.get('source_statement') or ''),
        '',
        f"- profile: `{summary.get('profile_name')}`",
        f"- edition: `{(summary.get('runtime_packaging') or {}).get('edition_key')}`",
        '',
        '## Win themes',
    ]
    for theme in summary.get('themes') or []:
        lines.extend(['', f"### {theme.get('title')}", '', str(theme.get('summary') or ''), '', f"Why it wins: {theme.get('why_it_wins') or ''}"])
        for item in theme.get('not_claimed') or []:
            lines.append(f'- Not claimed: {item}')
        lines.append('- Proof points:')
        for pp in theme.get('proof_points') or []:
            lines.append(f"  - **{pp.get('title')}** — {pp.get('statement')}")
    lines.extend(['', '## Compare checklists'])
    for checklist in summary.get('compare_checklists') or []:
        lines.extend(['', f"### {checklist.get('title')}"])
        for row in checklist.get('entries') or []:
            lines.append(f"- {row.get('question')}")
            for pp in row.get('proof_points') or []:
                lines.append(f"  - proof: {pp.get('title')}")
    return '\n'.join(lines) + '\n'


__all__ = [
    'ProofPoint',
    'ResolvedNavRef',
    'build_replacement_narratives_summary',
    'load_replacement_narratives_config',
    'render_replacement_narratives_markdown',
]
