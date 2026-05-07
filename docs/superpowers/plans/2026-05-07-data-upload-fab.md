# Data Upload via FAB — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third FAB menu item "Загрузить данные" that opens a 4-step wizard for downloading a CSV/XLSX template, uploading the filled file, previewing valid rows / duplicates / errors, and committing valid rows to one of 4 supported `dm_*` tables.

**Architecture:** Backend `uploads_v1.py` holds a `TYPE_REGISTRY` dict that drives template generation, parsing, validation, and INSERT (single source of truth). In-memory token cache (TTL 5 min) bridges the preview→commit round-trip. Frontend wizard reads/writes via thin Next.js proxies + a typed client. No DB migration — all 4 target tables already exist.

**Tech Stack:** FastAPI + pandas + openpyxl + psycopg v3 shim (backend), Next.js 15 + React 19 + TS 5.8 (frontend), pytest + Playwright (tests).

**Spec:** `docs/superpowers/specs/2026-05-07-data-upload-fab-design.md`

**Commit policy** (CLAUDE.md §11): backend / frontend / screenshots / proof — separate commits. No migration.

---

## File Map

**Created:**
- `web_cabinet/uploads_v1.py` — TYPE_REGISTRY + generate_template + parse_file + validate_rows + commit_rows + token cache
- `tests/test_uploads_template.py`
- `tests/test_uploads_parse.py`
- `tests/test_uploads_validation.py`
- `tests/test_uploads_commit.py`
- `web_app/app/api/uploads/types/route.ts`
- `web_app/app/api/uploads/template/route.ts`
- `web_app/app/api/uploads/preview/route.ts`
- `web_app/app/api/uploads/commit/route.ts`
- `web_app/lib/api/uploads-client.ts`
- `web_app/components/data-upload/data-upload-dialog.tsx`
- `web_app/components/data-upload/type-grid.tsx`
- `web_app/components/data-upload/template-step.tsx`
- `web_app/components/data-upload/preview-step.tsx`

**Modified:**
- `packages/contracts/api_boundary_v1.py` — add upload contracts
- `web_cabinet/api_boundary_v1.py` — 4 new boundary routes
- `web_app/components/app/fab.tsx` — add 3rd menu item

---

## Schema notes (verified via psql)

All 4 target tables use composite PK `(tenant_id, <id>)` and have FK to dm_animals or dm_sites/dm_farms. The actual columns:

- `dm_milkings_daily(tenant_id, record_id, animal_id, lactation_id, date, milk_kg, milking_count, fat_pct, protein_pct, scc_cells_ml, created_at, updated_at)` — PK `(tenant_id, record_id)`
- `dm_health_events(tenant_id, event_id, animal_id, event_date, event_type, severity, notes, created_at, updated_at)` — PK `(tenant_id, event_id)`
- `dm_animals(tenant_id, animal_id, farm_id, site_id, current_pen_id, master_animal_id, external_id, sex, birth_date, breed, status, created_at, updated_at)` — PK `(tenant_id, animal_id)`. `farm_id` is NOT NULL FK.
- `dm_feed_rations(tenant_id, ration_id, site_id, ration_name, effective_from, effective_to, dm_pct, created_at, updated_at)` — PK `(tenant_id, ration_id)`. `site_id` and `ration_name` NOT NULL.

For columns the user shouldn't have to fill, the backend auto-fills from auth context:
- `tenant_id` ← `user.tenant_id`
- `farm_id` (animals) ← caller's active farm (`user.farm_id` or default)
- `site_id` (animals, feed_rations) ← caller's active site (looked up via `dm_sites WHERE tenant_id=%s LIMIT 1`)
- `record_id`, `event_id`, `ration_id` ← server-generated UUID/UUID-like prefix when not provided

The user provides only the operational columns (animal_id, date, milk_kg, etc.) — see TYPE_REGISTRY in Task 2.

---

## Task 1: Pydantic contracts

**Files:**
- Modify: `packages/contracts/api_boundary_v1.py` (append at end)

- [ ] **Step 1: Add contracts**

Append after the last existing class (search for the last `class ...` then add immediately after):

```python
class UploadColumnSpec(BaseModel):
    name: str
    required: bool = True
    kind: str = 'str'
    description: str = ''
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    fk_table: Optional[str] = None


class UploadTypeMeta(BaseModel):
    schema: str = 'genomeai.api.uploads.type.v1'
    type: str
    label: str
    target_table: str
    instructions: str = ''
    columns: list[UploadColumnSpec] = Field(default_factory=list)


class UploadTypesListResponse(BaseModel):
    schema: str = 'genomeai.api.uploads.types.list.v1'
    items: list[UploadTypeMeta] = Field(default_factory=list)


class UploadRowError(BaseModel):
    row: int
    field: Optional[str] = None
    message: str


class UploadPreviewResponse(BaseModel):
    schema: str = 'genomeai.api.uploads.preview.v1'
    type: str
    total_rows: int = 0
    valid: int = 0
    duplicates: int = 0
    errors: list[UploadRowError] = Field(default_factory=list)
    preview_token: str = ''
    valid_rows_sample: list[dict[str, Any]] = Field(default_factory=list)


class UploadCommitRequest(BaseModel):
    preview_token: str


class UploadCommitResponse(BaseModel):
    schema: str = 'genomeai.api.uploads.commit.v1'
    inserted: int = 0
    skipped_duplicates: int = 0
```

- [ ] **Step 2: Verify imports compile**

```bash
cd /opt/genomeai/repo && python -c "
from packages.contracts.api_boundary_v1 import (
    UploadColumnSpec, UploadTypeMeta, UploadTypesListResponse,
    UploadRowError, UploadPreviewResponse,
    UploadCommitRequest, UploadCommitResponse,
)
print('ok')
"
```
Expected: `ok` (Pydantic UserWarnings about `schema` field shadowing are pre-existing pattern — ignore).

- [ ] **Step 3: DO NOT COMMIT** — bundled into Task 7 backend commit.

---

## Task 2: `uploads_v1.py` — TYPE_REGISTRY + template generation (TDD)

**Files:**
- Create: `tests/test_uploads_template.py`
- Create: `web_cabinet/uploads_v1.py`

- [ ] **Step 1: Write tests for template generation**

Create `tests/test_uploads_template.py`:

```python
"""Template generation per UploadType."""
from __future__ import annotations

import csv
import io
import pytest


def test_list_types():
    from web_cabinet.uploads_v1 import list_types
    items = list_types()
    type_ids = {t.type for t in items}
    assert type_ids == {'milkings', 'health_events', 'animals', 'feed_rations'}


def test_csv_template_milkings():
    from web_cabinet.uploads_v1 import generate_template
    body, content_type, filename = generate_template('milkings', 'csv')
    assert content_type == 'text/csv; charset=utf-8'
    assert filename == 'milkings_template.csv'
    text = body.decode('utf-8-sig')  # BOM stripped
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    headers = rows[0]
    assert 'animal_id' in headers
    assert 'date' in headers
    assert 'milk_kg' in headers
    # second row is example
    assert len(rows) >= 2


def test_xlsx_template_milkings_parses_back():
    from web_cabinet.uploads_v1 import generate_template
    from openpyxl import load_workbook
    body, content_type, filename = generate_template('milkings', 'xlsx')
    assert filename == 'milkings_template.xlsx'
    wb = load_workbook(io.BytesIO(body))
    ws = wb.active
    headers = [c.value for c in ws[1]]
    assert 'animal_id' in headers
    assert 'date' in headers
    wb.close()


@pytest.mark.parametrize('type_id', ['milkings', 'health_events', 'animals', 'feed_rations'])
@pytest.mark.parametrize('fmt', ['csv', 'xlsx'])
def test_template_smoke(type_id, fmt):
    from web_cabinet.uploads_v1 import generate_template
    body, content_type, filename = generate_template(type_id, fmt)
    assert len(body) > 50, f'{type_id} {fmt} template empty'
    assert filename.endswith(f'.{fmt}')


def test_unknown_type_raises():
    from web_cabinet.uploads_v1 import generate_template
    with pytest.raises(ValueError, match='unknown type'):
        generate_template('xxx', 'csv')


def test_unknown_format_raises():
    from web_cabinet.uploads_v1 import generate_template
    with pytest.raises(ValueError, match='unknown format'):
        generate_template('milkings', 'pdf')
```

- [ ] **Step 2: Run tests, expect FAIL**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_template.py -v 2>&1 | tail -10
```
Expected: ImportError / module not found.

- [ ] **Step 3: Implement registry + template generator**

Create `web_cabinet/uploads_v1.py`:

```python
"""Data upload boundary: TYPE_REGISTRY, template generation, parse, validate, commit."""
from __future__ import annotations

import csv
import io
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Optional

from packages.contracts.api_boundary_v1 import (
    UploadColumnSpec,
    UploadTypeMeta,
    UploadRowError,
    UploadPreviewResponse,
    UploadCommitResponse,
)

logger = logging.getLogger("genomeai.web_cabinet.uploads_v1")


@dataclass
class UploadType:
    type_id: str
    label: str
    target_table: str
    columns: list[UploadColumnSpec]
    unique_key: list[str]
    sample_row: dict[str, Any]
    instructions: str = ''
    server_id_column: Optional[str] = None  # column auto-filled with UUID
    auto_fields: dict[str, str] = field(default_factory=dict)  # col -> source ('tenant_id', 'farm_id', 'site_id')


TYPE_REGISTRY: dict[str, UploadType] = {
    'milkings': UploadType(
        type_id='milkings',
        label='Надои',
        target_table='dm_milkings_daily',
        columns=[
            UploadColumnSpec(name='animal_id', required=True, kind='str',
                             description='ID животного (должно существовать)', fk_table='dm_animals'),
            UploadColumnSpec(name='date', required=True, kind='date',
                             description='Дата надоя в формате YYYY-MM-DD'),
            UploadColumnSpec(name='milk_kg', required=True, kind='float',
                             description='Надой в кг (0-80)', min_val=0, max_val=80),
            UploadColumnSpec(name='scc_cells_ml', required=False, kind='int',
                             description='SCC, cells/ml (0-5000000)', min_val=0, max_val=5_000_000),
            UploadColumnSpec(name='fat_pct', required=False, kind='float',
                             description='Жирность %, 0-10', min_val=0, max_val=10),
            UploadColumnSpec(name='protein_pct', required=False, kind='float',
                             description='Белок %, 0-10', min_val=0, max_val=10),
        ],
        unique_key=['tenant_id', 'animal_id', 'date'],
        sample_row={'animal_id': '1234', 'date': '2026-05-01', 'milk_kg': 28.5,
                    'scc_cells_ml': 180000, 'fat_pct': 3.8, 'protein_pct': 3.2},
        instructions='Каждая строка — один день надоя одной коровы.',
        server_id_column='record_id',
        auto_fields={'tenant_id': 'tenant_id'},
    ),
    'health_events': UploadType(
        type_id='health_events',
        label='События здоровья',
        target_table='dm_health_events',
        columns=[
            UploadColumnSpec(name='animal_id', required=True, kind='str',
                             description='ID животного', fk_table='dm_animals'),
            UploadColumnSpec(name='event_date', required=True, kind='date',
                             description='Дата события'),
            UploadColumnSpec(name='event_type', required=True, kind='str',
                             description='Тип: mastitis, lameness, ketosis, vet_visit, ...'),
            UploadColumnSpec(name='severity', required=False, kind='str',
                             description='Опционально: low, medium, high'),
            UploadColumnSpec(name='notes', required=False, kind='str',
                             description='Комментарий'),
        ],
        unique_key=['tenant_id', 'animal_id', 'event_date', 'event_type'],
        sample_row={'animal_id': '1234', 'event_date': '2026-05-01',
                    'event_type': 'mastitis', 'severity': 'medium',
                    'notes': 'Левая передняя четверть'},
        instructions='Регистрация событий здоровья по конкретным животным.',
        server_id_column='event_id',
        auto_fields={'tenant_id': 'tenant_id'},
    ),
    'animals': UploadType(
        type_id='animals',
        label='Животные',
        target_table='dm_animals',
        columns=[
            UploadColumnSpec(name='animal_id', required=True, kind='str',
                             description='Уникальный ID нового животного'),
            UploadColumnSpec(name='external_id', required=False, kind='str',
                             description='Внешний номер бирки'),
            UploadColumnSpec(name='birth_date', required=False, kind='date',
                             description='Дата рождения'),
            UploadColumnSpec(name='sex', required=False, kind='str',
                             description='cow | heifer | bull | calf'),
            UploadColumnSpec(name='breed', required=False, kind='str',
                             description='Порода'),
            UploadColumnSpec(name='status', required=False, kind='str',
                             description='active | dry | culled | sold'),
        ],
        unique_key=['tenant_id', 'animal_id'],
        sample_row={'animal_id': '5001', 'external_id': 'EAR-5001',
                    'birth_date': '2024-03-15', 'sex': 'heifer',
                    'breed': 'Holstein', 'status': 'active'},
        instructions='Регистрация новых животных. ID должен быть уникальным в пределах хозяйства.',
        auto_fields={'tenant_id': 'tenant_id', 'farm_id': 'farm_id'},
    ),
    'feed_rations': UploadType(
        type_id='feed_rations',
        label='Рационы',
        target_table='dm_feed_rations',
        columns=[
            UploadColumnSpec(name='ration_id', required=True, kind='str',
                             description='Уникальный ID рациона'),
            UploadColumnSpec(name='ration_name', required=True, kind='str',
                             description='Название рациона'),
            UploadColumnSpec(name='effective_from', required=True, kind='date',
                             description='Дата начала действия'),
            UploadColumnSpec(name='effective_to', required=False, kind='date',
                             description='Дата окончания (опционально)'),
            UploadColumnSpec(name='dm_pct', required=False, kind='float',
                             description='Сухое вещество %, 0-100', min_val=0, max_val=100),
        ],
        unique_key=['tenant_id', 'ration_id'],
        sample_row={'ration_id': 'R-001', 'ration_name': 'Высокопродуктивные TMR',
                    'effective_from': '2026-05-01', 'effective_to': '',
                    'dm_pct': 50.0},
        instructions='Рационы кормления для разных групп животных.',
        auto_fields={'tenant_id': 'tenant_id', 'site_id': 'site_id'},
    ),
}


def list_types() -> list[UploadTypeMeta]:
    return [
        UploadTypeMeta(
            type=t.type_id, label=t.label, target_table=t.target_table,
            instructions=t.instructions, columns=t.columns,
        )
        for t in TYPE_REGISTRY.values()
    ]


def generate_template(type_id: str, fmt: str) -> tuple[bytes, str, str]:
    """Return (body_bytes, content_type, filename)."""
    if type_id not in TYPE_REGISTRY:
        raise ValueError(f'unknown type: {type_id}')
    if fmt not in ('csv', 'xlsx'):
        raise ValueError(f'unknown format: {fmt}')
    spec = TYPE_REGISTRY[type_id]
    headers = [c.name for c in spec.columns]
    sample = [str(spec.sample_row.get(c.name, '')) for c in spec.columns]

    if fmt == 'csv':
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\n')
        w.writerow(headers)
        w.writerow(sample)
        body = ('﻿' + buf.getvalue()).encode('utf-8')  # UTF-8 BOM
        return body, 'text/csv; charset=utf-8', f'{type_id}_template.csv'

    # xlsx
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = type_id
    ws.append(headers)
    instructions = []
    for c in spec.columns:
        bits = [c.kind]
        if c.required:
            bits.append('required')
        if c.min_val is not None or c.max_val is not None:
            bits.append(f'[{c.min_val if c.min_val is not None else "-∞"}, {c.max_val if c.max_val is not None else "+∞"}]')
        if c.fk_table:
            bits.append(f'FK→{c.fk_table}')
        if c.description:
            bits.append(c.description)
        instructions.append(' • '.join(bits))
    ws.append(instructions)
    ws.append(sample)
    bold = Font(bold=True)
    for cell in ws[1]:
        cell.font = bold
        cell.alignment = Alignment(horizontal='left')
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 22
    out = io.BytesIO()
    wb.save(out)
    wb.close()
    return (
        out.getvalue(),
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        f'{type_id}_template.xlsx',
    )
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_template.py -v 2>&1 | tail -15
```
Expected: 11 PASSED (4 main + 8 parametrized + 2 error cases — actually total = 4 + (4 types * 2 fmts) + 2 = 14; verify count empirically).

- [ ] **Step 5: DO NOT COMMIT** — bundle into Task 7.

---

## Task 3: Parse + validate (TDD)

**Files:**
- Create: `tests/test_uploads_parse.py`
- Create: `tests/test_uploads_validation.py`
- Modify (extend): `web_cabinet/uploads_v1.py`

- [ ] **Step 1: Write parse tests**

`tests/test_uploads_parse.py`:

```python
"""parse_file: CSV / XLSX → list[dict]."""
from __future__ import annotations

import io


def test_parse_csv_milkings():
    from web_cabinet.uploads_v1 import parse_file, generate_template
    body, _, _ = generate_template('milkings', 'csv')
    rows = parse_file('milkings', body, 'milkings.csv')
    # Sample row from template should round-trip
    assert len(rows) == 1
    assert rows[0]['animal_id'] == '1234'
    assert rows[0]['milk_kg'] in (28.5, '28.5')


def test_parse_xlsx_milkings():
    from web_cabinet.uploads_v1 import parse_file
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(['animal_id', 'date', 'milk_kg'])
    ws.append(['A1', '2026-05-01', 28.5])
    ws.append(['A2', '2026-05-01', 30.0])
    out = io.BytesIO()
    wb.save(out); wb.close()
    rows = parse_file('milkings', out.getvalue(), 'data.xlsx')
    assert len(rows) == 2
    assert rows[0]['animal_id'] == 'A1'


def test_parse_drops_empty_rows():
    from web_cabinet.uploads_v1 import parse_file
    csv_body = '﻿animal_id,date,milk_kg\nA1,2026-05-01,28.5\n,,\nA2,2026-05-02,29.0\n'.encode('utf-8')
    rows = parse_file('milkings', csv_body, 'd.csv')
    assert len(rows) == 2


def test_parse_unsupported_extension_raises():
    from web_cabinet.uploads_v1 import parse_file
    import pytest
    with pytest.raises(ValueError, match='unsupported_format'):
        parse_file('milkings', b'x', 'd.txt')


def test_parse_cp1251_fallback():
    """Russian content saved as Windows-1251 still parses (best-effort)."""
    from web_cabinet.uploads_v1 import parse_file
    text = 'animal_id,event_date,event_type,notes\nA1,2026-05-01,mastitis,Левая передняя\n'
    body = text.encode('cp1251')
    rows = parse_file('health_events', body, 'd.csv')
    assert rows[0]['notes'] == 'Левая передняя'
```

- [ ] **Step 2: Write validation tests**

`tests/test_uploads_validation.py`:

```python
"""validate_rows: required, type, range, FK, duplicate."""
from __future__ import annotations

import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _ensure_animal(tenant_id, animal_id, farm_id='F1'):
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dm_farms (tenant_id, farm_id, farm_name) VALUES (%s, %s, 'F1') "
                "ON CONFLICT DO NOTHING",
                (tenant_id, farm_id),
            )
            cur.execute(
                "INSERT INTO dm_animals (tenant_id, animal_id, farm_id) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (tenant_id, animal_id, farm_id),
            )
        conn.commit()


def _cleanup(tenant_id):
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dm_milkings_daily WHERE tenant_id=%s", (tenant_id,))
            cur.execute("DELETE FROM dm_animals WHERE tenant_id=%s", (tenant_id,))
            cur.execute("DELETE FROM dm_farms WHERE tenant_id=%s", (tenant_id,))
        conn.commit()


def test_required_field_missing():
    from web_cabinet.uploads_v1 import validate_rows
    rows = [{'animal_id': '', 'date': '2026-05-01', 'milk_kg': 28.5}]
    result = validate_rows('milkings', rows, tenant_id='vt_tx')
    assert len(result.errors) == 1
    assert result.errors[0].field == 'animal_id'


def test_type_coercion_failure():
    from web_cabinet.uploads_v1 import validate_rows
    rows = [{'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 'abc'}]
    result = validate_rows('milkings', rows, tenant_id='vt_tx')
    assert any(e.field == 'milk_kg' for e in result.errors)


def test_range_violation():
    from web_cabinet.uploads_v1 import validate_rows
    rows = [{'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 250.0}]
    result = validate_rows('milkings', rows, tenant_id='vt_tx')
    assert any(e.field == 'milk_kg' for e in result.errors)


def test_fk_missing_animal():
    from web_cabinet.uploads_v1 import validate_rows
    tenant = f'vt_fk_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    rows = [{'animal_id': 'NOT_EXIST', 'date': '2026-05-01', 'milk_kg': 28.5}]
    result = validate_rows('milkings', rows, tenant_id=tenant)
    assert any(e.field == 'animal_id' for e in result.errors)


def test_fk_present_passes():
    from web_cabinet.uploads_v1 import validate_rows
    tenant = f'vt_fkok_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        rows = [{'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5}]
        result = validate_rows('milkings', rows, tenant_id=tenant)
        assert len(result.errors) == 0
        assert len(result.valid_rows) == 1
    finally:
        _cleanup(tenant)


def test_duplicate_detected():
    from web_cabinet.uploads_v1 import validate_rows
    from web_cabinet.insights_v1 import _conn
    tenant = f'vt_dup_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dm_milkings_daily (tenant_id, record_id, animal_id, date, milk_kg, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW())",
                    (tenant, 'r1', 'A1', '2026-05-01', 28.5),
                )
            conn.commit()
        rows = [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
            {'animal_id': 'A1', 'date': '2026-05-02', 'milk_kg': 29.0},
        ]
        result = validate_rows('milkings', rows, tenant_id=tenant)
        assert result.duplicates == 1
        assert len(result.valid_rows) == 1
    finally:
        _cleanup(tenant)
```

- [ ] **Step 3: Run tests, expect FAIL**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_parse.py tests/test_uploads_validation.py -v 2>&1 | tail -15
```
Expected: failures (`parse_file`, `validate_rows` not defined).

- [ ] **Step 4: Implement parse_file + validate_rows**

Append to `web_cabinet/uploads_v1.py`:

```python
@dataclass
class ValidationResult:
    valid_rows: list[dict]
    duplicates: int
    errors: list[UploadRowError]


def parse_file(type_id: str, file_bytes: bytes, filename: str) -> list[dict]:
    if type_id not in TYPE_REGISTRY:
        raise ValueError(f'unknown type: {type_id}')
    name = filename.lower()
    if name.endswith('.xlsx'):
        return _parse_xlsx(type_id, file_bytes)
    if name.endswith('.csv'):
        return _parse_csv(type_id, file_bytes)
    raise ValueError('unsupported_format')


def _parse_csv(type_id: str, body: bytes) -> list[dict]:
    spec = TYPE_REGISTRY[type_id]
    expected_cols = {c.name for c in spec.columns}
    text = None
    for enc in ('utf-8-sig', 'utf-8', 'cp1251'):
        try:
            text = body.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for raw in reader:
        # Drop fully empty rows
        if not any(((v or '').strip()) for v in raw.values()):
            continue
        cleaned = {k: ((v or '').strip() if isinstance(v, str) else v)
                   for k, v in raw.items() if k in expected_cols or k is None}
        # Filter to known columns only (silently drop extras)
        cleaned = {k: v for k, v in cleaned.items() if k in expected_cols}
        rows.append(cleaned)
    return rows


def _parse_xlsx(type_id: str, body: bytes) -> list[dict]:
    from openpyxl import load_workbook
    spec = TYPE_REGISTRY[type_id]
    expected_cols = {c.name for c in spec.columns}
    wb = load_workbook(io.BytesIO(body), data_only=True)
    ws = wb.active
    headers = [str(c.value).strip() if c.value is not None else '' for c in ws[1]]
    rows: list[dict] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in row):
            continue
        # Skip xlsx instruction row (xlsx template puts instructions at row 2)
        # Heuristic: if any value contains ' • ' or starts with type info ('str', 'int', 'date', 'float'), it's instructions
        if isinstance(row[0], str) and (' • ' in row[0] or row[0].strip() in ('str', 'int', 'float', 'date')):
            continue
        d: dict[str, Any] = {}
        for i, h in enumerate(headers):
            if h in expected_cols and i < len(row):
                v = row[i]
                if isinstance(v, str):
                    v = v.strip()
                if v == '':
                    continue
                if hasattr(v, 'isoformat'):  # date / datetime
                    v = v.isoformat()[:10]
                d[h] = v
        if d:
            rows.append(d)
    wb.close()
    return rows


def _coerce(value: Any, kind: str) -> tuple[Any, Optional[str]]:
    """Coerce value to kind. Returns (coerced, error_message_or_None)."""
    if value is None or value == '':
        return None, None
    try:
        if kind == 'int':
            return int(float(str(value))), None  # int("3.0") fails; via float ok
        if kind == 'float':
            return float(str(value)), None
        if kind == 'date':
            s = str(value)
            for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y'):
                try:
                    return datetime.strptime(s[:19], fmt).date().isoformat(), None
                except ValueError:
                    continue
            return None, 'Неверный формат даты (ожидается YYYY-MM-DD)'
        return str(value).strip(), None
    except (ValueError, TypeError):
        return None, 'Неверный тип'


def validate_rows(type_id: str, rows: list[dict], *, tenant_id: str) -> ValidationResult:
    if type_id not in TYPE_REGISTRY:
        raise ValueError(f'unknown type: {type_id}')
    spec = TYPE_REGISTRY[type_id]
    errors: list[UploadRowError] = []
    coerced_rows: list[dict] = []

    # Pass 1: per-row required + coercion + range
    for i, raw in enumerate(rows, start=1):
        row_errs: list[UploadRowError] = []
        clean: dict[str, Any] = {}
        for col in spec.columns:
            v = raw.get(col.name)
            if col.required and (v is None or v == ''):
                row_errs.append(UploadRowError(row=i, field=col.name, message='Обязательное поле'))
                continue
            coerced, err = _coerce(v, col.kind)
            if err is not None:
                row_errs.append(UploadRowError(row=i, field=col.name, message=f'{err}: {v!r}'))
                continue
            if coerced is None:
                continue
            if col.min_val is not None and isinstance(coerced, (int, float)) and coerced < col.min_val:
                row_errs.append(UploadRowError(row=i, field=col.name,
                    message=f'Значение {coerced} меньше минимума {col.min_val}'))
                continue
            if col.max_val is not None and isinstance(coerced, (int, float)) and coerced > col.max_val:
                row_errs.append(UploadRowError(row=i, field=col.name,
                    message=f'Значение {coerced} больше максимума {col.max_val}'))
                continue
            clean[col.name] = coerced
        if row_errs:
            errors.extend(row_errs)
        else:
            clean['_row_idx'] = i
            coerced_rows.append(clean)

    # Pass 2: FK existence (batch per fk_table)
    fk_cols = [c for c in spec.columns if c.fk_table]
    for col in fk_cols:
        ids = sorted({r[col.name] for r in coerced_rows if col.name in r})
        if not ids:
            continue
        existing = _fetch_fk_existing(col.fk_table, tenant_id, ids)
        kept: list[dict] = []
        for r in coerced_rows:
            if col.name in r and r[col.name] not in existing:
                errors.append(UploadRowError(row=r['_row_idx'], field=col.name,
                    message=f'ID {r[col.name]!r} не существует в {col.fk_table}'))
                continue
            kept.append(r)
        coerced_rows = kept

    # Pass 3: duplicate detection
    duplicates = 0
    if spec.unique_key and coerced_rows:
        existing_keys = _fetch_existing_keys(spec, tenant_id, coerced_rows)
        kept = []
        for r in coerced_rows:
            key = tuple(r.get(k) if k != 'tenant_id' else tenant_id for k in spec.unique_key)
            if key in existing_keys:
                duplicates += 1
                continue
            kept.append(r)
        coerced_rows = kept

    valid_rows = [{k: v for k, v in r.items() if not k.startswith('_')} for r in coerced_rows]
    return ValidationResult(valid_rows=valid_rows, duplicates=duplicates, errors=errors)


def _fetch_fk_existing(fk_table: str, tenant_id: str, ids: list[str]) -> set[str]:
    if fk_table != 'dm_animals':
        return set(ids)  # fallback: assume present (extend if more FKs added later)
    try:
        from web_cabinet.insights_v1 import _conn
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT animal_id FROM dm_animals WHERE tenant_id=%s AND animal_id = ANY(%s)",
                    (tenant_id, ids),
                )
                return {r[0] for r in cur.fetchall()}
    except Exception as exc:
        logger.warning(f'_fetch_fk_existing failed: {exc}')
        return set()  # be conservative — treat all as missing on error


def _fetch_existing_keys(spec: UploadType, tenant_id: str, rows: list[dict]) -> set[tuple]:
    if not rows or not spec.unique_key:
        return set()
    cols_to_select = [c for c in spec.unique_key if c != 'tenant_id']
    if not cols_to_select:
        return set()
    try:
        from web_cabinet.insights_v1 import _conn
        # Build VALUES clause for batch lookup
        from psycopg.types.json import Json  # type: ignore
        # Safer approach: SELECT existing rows for this tenant where keys IN target set
        # Use unnest-based filter to support batch
        sql = f"SELECT {', '.join(cols_to_select)} FROM {spec.target_table} WHERE tenant_id=%s"
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tenant_id,))
                existing = cur.fetchall()
        # Build set
        result: set[tuple] = set()
        for tup in existing:
            key = []
            for k in spec.unique_key:
                if k == 'tenant_id':
                    key.append(tenant_id)
                else:
                    idx = cols_to_select.index(k)
                    val = tup[idx]
                    if hasattr(val, 'isoformat'):
                        val = val.isoformat()[:10]
                    key.append(val)
            result.add(tuple(key))
        return result
    except Exception as exc:
        logger.warning(f'_fetch_existing_keys failed: {exc}')
        return set()
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_parse.py tests/test_uploads_validation.py -v 2>&1 | tail -20
```
Expected: 5 + 6 = 11 PASSED.

- [ ] **Step 6: DO NOT COMMIT** — bundle into Task 7.

---

## Task 4: Token cache + commit (TDD)

**Files:**
- Create: `tests/test_uploads_commit.py`
- Modify (extend): `web_cabinet/uploads_v1.py`

- [ ] **Step 1: Write tests**

`tests/test_uploads_commit.py`:

```python
"""Token cache + commit_rows."""
from __future__ import annotations

import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _ensure_animal(tenant_id, animal_id, farm_id='F1'):
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dm_farms (tenant_id, farm_id, farm_name) VALUES (%s, %s, 'F1') "
                "ON CONFLICT DO NOTHING",
                (tenant_id, farm_id),
            )
            cur.execute(
                "INSERT INTO dm_animals (tenant_id, animal_id, farm_id) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (tenant_id, animal_id, farm_id),
            )
        conn.commit()


def _cleanup(tenant_id):
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dm_milkings_daily WHERE tenant_id=%s", (tenant_id,))
            cur.execute("DELETE FROM dm_animals WHERE tenant_id=%s", (tenant_id,))
            cur.execute("DELETE FROM dm_farms WHERE tenant_id=%s", (tenant_id,))
        conn.commit()


def test_token_create_and_commit():
    from web_cabinet.uploads_v1 import (
        ValidationResult, store_preview_token, commit_rows,
    )
    tenant = f'vt_c_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        token = store_preview_token('milkings', tenant, [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
        ])
        assert isinstance(token, str) and len(token) > 8
        resp = commit_rows(token, tenant_id=tenant)
        assert resp.inserted == 1
    finally:
        _cleanup(tenant)


def test_commit_unknown_token_returns_410():
    from web_cabinet.uploads_v1 import commit_rows, TokenExpired
    with pytest.raises(TokenExpired):
        commit_rows('bogus_token', tenant_id='any')


def test_commit_consumed_once():
    from web_cabinet.uploads_v1 import (
        store_preview_token, commit_rows, TokenExpired,
    )
    tenant = f'vt_cs_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        token = store_preview_token('milkings', tenant, [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
        ])
        commit_rows(token, tenant_id=tenant)
        with pytest.raises(TokenExpired):
            commit_rows(token, tenant_id=tenant)
    finally:
        _cleanup(tenant)


def test_commit_tenant_mismatch():
    from web_cabinet.uploads_v1 import (
        store_preview_token, commit_rows, TenantMismatch,
    )
    tenant_a = f'vt_a_{uuid.uuid4().hex[:6]}'
    tenant_b = f'vt_b_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant_a); _cleanup(tenant_b)
    _ensure_animal(tenant_a, 'A1')
    try:
        token = store_preview_token('milkings', tenant_a, [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
        ])
        with pytest.raises(TenantMismatch):
            commit_rows(token, tenant_id=tenant_b)
    finally:
        _cleanup(tenant_a); _cleanup(tenant_b)
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_commit.py -v 2>&1 | tail -15
```
Expected: ImportError on `store_preview_token`.

- [ ] **Step 3: Implement token cache + commit**

Append to `web_cabinet/uploads_v1.py`:

```python
class TokenExpired(Exception):
    """Raised when preview_token is missing or expired or already consumed."""


class TenantMismatch(Exception):
    """Raised when commit caller's tenant_id does not match token's tenant_id."""


@dataclass
class _CacheEntry:
    type_id: str
    tenant_id: str
    valid_rows: list[dict]
    created_at: float


_TOKEN_CACHE: dict[str, _CacheEntry] = {}
_TOKEN_TTL_SECONDS = 5 * 60


def _gc_cache() -> None:
    now = time.time()
    expired = [k for k, v in _TOKEN_CACHE.items() if now - v.created_at > _TOKEN_TTL_SECONDS]
    for k in expired:
        _TOKEN_CACHE.pop(k, None)


def store_preview_token(type_id: str, tenant_id: str, valid_rows: list[dict]) -> str:
    _gc_cache()
    token = secrets.token_hex(8)
    _TOKEN_CACHE[token] = _CacheEntry(
        type_id=type_id, tenant_id=tenant_id,
        valid_rows=list(valid_rows), created_at=time.time(),
    )
    return token


def commit_rows(token: str, *, tenant_id: str, farm_id: Optional[str] = None,
                site_id: Optional[str] = None) -> UploadCommitResponse:
    _gc_cache()
    entry = _TOKEN_CACHE.pop(token, None)  # one-shot
    if entry is None:
        raise TokenExpired(token)
    if entry.tenant_id != tenant_id:
        # Restore (don't consume on auth failure)
        _TOKEN_CACHE[token] = entry
        raise TenantMismatch()
    spec = TYPE_REGISTRY[entry.type_id]
    inserted = _do_insert(spec, entry.valid_rows, tenant_id=tenant_id,
                          farm_id=farm_id, site_id=site_id)
    return UploadCommitResponse(inserted=inserted, skipped_duplicates=0)


def _do_insert(spec: UploadType, rows: list[dict], *, tenant_id: str,
               farm_id: Optional[str], site_id: Optional[str]) -> int:
    if not rows:
        return 0
    auto_value = {
        'tenant_id': tenant_id,
        'farm_id': farm_id or _resolve_default_farm(tenant_id),
        'site_id': site_id or _resolve_default_site(tenant_id),
    }
    inserted = 0
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                full: dict[str, Any] = {}
                for col_name, src in spec.auto_fields.items():
                    full[col_name] = auto_value.get(src)
                if spec.server_id_column and spec.server_id_column not in r:
                    full[spec.server_id_column] = f'{spec.type_id[:3]}_{uuid.uuid4().hex[:10]}'
                # Add user-provided columns
                for col in spec.columns:
                    if col.name in r and r[col.name] is not None:
                        full[col.name] = r[col.name]
                # created_at
                full.setdefault('created_at', datetime.utcnow().isoformat())
                cols = list(full.keys())
                placeholders = ', '.join(['%s'] * len(cols))
                # ON CONFLICT clause based on PK or unique_key
                conflict_cols = ', '.join(spec.unique_key) if spec.unique_key else 'tenant_id'
                sql = (
                    f"INSERT INTO {spec.target_table} ({', '.join(cols)}) "
                    f"VALUES ({placeholders}) "
                    f"ON CONFLICT ({conflict_cols}) DO NOTHING"
                )
                try:
                    cur.execute(sql, [full[c] for c in cols])
                    inserted += cur.rowcount
                except Exception as exc:
                    logger.warning(f'insert row failed: {exc}; row={r}')
        conn.commit()
    return inserted


def _resolve_default_farm(tenant_id: str) -> Optional[str]:
    try:
        from web_cabinet.insights_v1 import _conn
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT farm_id FROM dm_farms WHERE tenant_id=%s LIMIT 1",
                    (tenant_id,),
                )
                row = cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None


def _resolve_default_site(tenant_id: str) -> Optional[str]:
    try:
        from web_cabinet.insights_v1 import _conn
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT site_id FROM dm_sites WHERE tenant_id=%s LIMIT 1",
                    (tenant_id,),
                )
                row = cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None


def run_preview(type_id: str, file_bytes: bytes, filename: str,
                tenant_id: str) -> UploadPreviewResponse:
    """Top-level helper: parse → validate → cache token → return response."""
    if type_id not in TYPE_REGISTRY:
        return UploadPreviewResponse(
            type=type_id, total_rows=0, valid=0, duplicates=0,
            errors=[UploadRowError(row=0, message=f'Unknown type: {type_id}')],
            preview_token='',
        )
    try:
        rows = parse_file(type_id, file_bytes, filename)
    except ValueError as exc:
        return UploadPreviewResponse(
            type=type_id, total_rows=0, valid=0, duplicates=0,
            errors=[UploadRowError(row=0, message=str(exc))],
            preview_token='',
        )
    result = validate_rows(type_id, rows, tenant_id=tenant_id)
    token = ''
    if result.valid_rows:
        token = store_preview_token(type_id, tenant_id, result.valid_rows)
    return UploadPreviewResponse(
        type=type_id,
        total_rows=len(rows),
        valid=len(result.valid_rows),
        duplicates=result.duplicates,
        errors=result.errors[:50],
        preview_token=token,
        valid_rows_sample=result.valid_rows[:5],
    )
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_commit.py -v 2>&1 | tail -15
```
Expected: 4 PASSED.

- [ ] **Step 5: Run all uploads tests**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_template.py tests/test_uploads_parse.py tests/test_uploads_validation.py tests/test_uploads_commit.py -v 2>&1 | tail -25
```
Expected: ~25 PASSED total.

- [ ] **Step 6: DO NOT COMMIT** — bundle into Task 7.

---

## Task 5: Boundary routes

**Files:**
- Modify: `web_cabinet/api_boundary_v1.py`

- [ ] **Step 1: Extend imports**

Find the imports near the top. Add:

```python
import os
from .uploads_v1 import (
    list_types as _list_upload_types,
    generate_template as _generate_template,
    run_preview as _run_upload_preview,
    commit_rows as _commit_upload_rows,
    TokenExpired,
    TenantMismatch,
)
```

Extend the `from packages.contracts.api_boundary_v1 import (...)` line to include:

```python
    UploadTypesListResponse,
    UploadPreviewResponse,
    UploadCommitRequest,
    UploadCommitResponse,
```

Also import `Response` from FastAPI for raw bytes:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Query
```

(Adjust to whatever's already imported — don't duplicate.)

- [ ] **Step 2: Add 4 routes**

After the existing `boundary_qc_*` routes block (search for `boundary_qc_incident_dismiss`), add:

```python
@router.get('/uploads/types', response_model=UploadTypesListResponse)
def boundary_uploads_types(user=Depends(get_current_user)):
    if not _user_has_any(user, 'tasks.view'):
        raise HTTPException(status_code=403)
    return UploadTypesListResponse(items=_list_upload_types())


@router.get('/uploads/template')
def boundary_uploads_template(
    type: str = Query(...),
    fmt: str = Query('csv'),
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view'):
        raise HTTPException(status_code=403)
    try:
        body, content_type, filename = _generate_template(type, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=body,
        media_type=content_type,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.post('/uploads/preview', response_model=UploadPreviewResponse)
async def boundary_uploads_preview(
    type: str = Query(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    body = await file.read()
    if len(body) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='file_too_large')
    tenant_id = str(user.get('tenant_id') or 'default')
    return _run_upload_preview(type, body, file.filename or 'upload', tenant_id)


@router.post('/uploads/commit', response_model=UploadCommitResponse)
def boundary_uploads_commit(
    body: UploadCommitRequest,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    tenant_id = str(user.get('tenant_id') or 'default')
    farm_id = user.get('farm_id')
    try:
        return _commit_upload_rows(
            body.preview_token, tenant_id=tenant_id, farm_id=farm_id,
        )
    except TokenExpired:
        raise HTTPException(status_code=410, detail='token_expired')
    except TenantMismatch:
        raise HTTPException(status_code=403, detail='tenant_mismatch')
```

- [ ] **Step 3: Verify routes registered**

```bash
cd /opt/genomeai/repo && python -c "
from web_cabinet.api_boundary_v1 import router
paths = sorted({(','.join(sorted(r.methods)), r.path) for r in router.routes if 'upload' in r.path})
for m, p in paths: print(m, p)
"
```

Expected:
```
GET /api/app/v1/uploads/template
GET /api/app/v1/uploads/types
POST /api/app/v1/uploads/commit
POST /api/app/v1/uploads/preview
```

- [ ] **Step 4: Verify app imports cleanly**

```bash
cd /opt/genomeai/repo && python -c "from web_cabinet.app import app; print('ok')"
```
(If the bare invocation fails with `ModuleNotFoundError: core`, prepend `PYTHONPATH=src` — pre-existing convention.)

- [ ] **Step 5: DO NOT COMMIT** — bundle into Task 7.

---

## Task 6: Run all backend tests

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_template.py tests/test_uploads_parse.py tests/test_uploads_validation.py tests/test_uploads_commit.py -v 2>&1 | tail -30
```

Expected: ~25 PASSED.

- [ ] **Step 1: (sanity check only)**

If anything fails, fix the underlying code in `uploads_v1.py` before proceeding.

---

## Task 7: Commit backend bundle

```bash
cd /opt/genomeai/repo
git add packages/contracts/api_boundary_v1.py \
        web_cabinet/uploads_v1.py \
        web_cabinet/api_boundary_v1.py \
        tests/test_uploads_template.py \
        tests/test_uploads_parse.py \
        tests/test_uploads_validation.py \
        tests/test_uploads_commit.py
git status
```

Verify exactly 7 files staged, no PNGs, no unrelated.

```bash
git commit -m "$(cat <<'EOF'
feat(uploads): backend wizard for CSV/XLSX data upload

- TYPE_REGISTRY for 4 types (milkings, health_events, animals,
  feed_rations) drives templates + validation + INSERT
- generate_template emits CSV (UTF-8 BOM) and XLSX (formatted header
  + instruction row) per type
- parse_file accepts both formats, falls back through utf-8-sig /
  utf-8 / cp1251 for CSV
- validate_rows: required, type coercion, range, FK existence in
  dm_animals, duplicate detection on unique_key
- In-memory token cache (TTL 5 min, single-shot) bridges preview→commit
- Boundary routes: GET /uploads/types, GET /uploads/template,
  POST /uploads/preview (multipart), POST /uploads/commit (token)
- 410 on expired token; 403 on tenant mismatch

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Next.js API proxies

**Files:**
- Create: `web_app/app/api/uploads/types/route.ts`
- Create: `web_app/app/api/uploads/template/route.ts`
- Create: `web_app/app/api/uploads/preview/route.ts`
- Create: `web_app/app/api/uploads/commit/route.ts`

DO NOT COMMIT — bundle into Task 12 frontend commit.

- [ ] **Step 1: types proxy**

`web_app/app/api/uploads/types/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function GET(_request: NextRequest) {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = {};
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  let r: Response;
  try {
    r = await fetch(`${config.backendBaseUrl}/api/app/v1/uploads/types`, {
      headers, cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { 'content-type': 'application/json' },
  });
}
```

- [ ] **Step 2: template proxy (binary passthrough)**

`web_app/app/api/uploads/template/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function GET(request: NextRequest) {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = {};
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const url = new URL(request.url);
  let r: Response;
  try {
    r = await fetch(
      `${config.backendBaseUrl}/api/app/v1/uploads/template?${url.searchParams.toString()}`,
      { headers, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const buf = await r.arrayBuffer();
  return new NextResponse(buf, {
    status: r.status,
    headers: {
      'content-type': r.headers.get('content-type') ?? 'application/octet-stream',
      'content-disposition': r.headers.get('content-disposition') ?? '',
    },
  });
}
```

- [ ] **Step 3: preview proxy (multipart passthrough)**

`web_app/app/api/uploads/preview/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest) {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = {};
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  // Pass through Content-Type (multipart boundary)
  const ct = request.headers.get('content-type');
  if (ct) headers['content-type'] = ct;
  const url = new URL(request.url);
  const body = await request.arrayBuffer();
  let r: Response;
  try {
    r = await fetch(
      `${config.backendBaseUrl}/api/app/v1/uploads/preview?${url.searchParams.toString()}`,
      { method: 'POST', headers, body },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { 'content-type': 'application/json' },
  });
}
```

- [ ] **Step 4: commit proxy**

`web_app/app/api/uploads/commit/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest) {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const body = await request.text();
  let r: Response;
  try {
    r = await fetch(`${config.backendBaseUrl}/api/app/v1/uploads/commit`, {
      method: 'POST', headers, body,
    });
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { 'content-type': 'application/json' },
  });
}
```

- [ ] **Step 5: tsc**

```bash
cd /opt/genomeai/repo/web_app && npx tsc --noEmit 2>&1 | tail -10
```
Expected: clean.

- [ ] **Step 6: DO NOT COMMIT.**

---

## Task 9: Typed client

**Files:**
- Create: `web_app/lib/api/uploads-client.ts`

```ts
export interface UploadColumnSpec {
  name: string;
  required: boolean;
  kind: string;
  description: string;
  min_val?: number | null;
  max_val?: number | null;
  fk_table?: string | null;
}

export interface UploadTypeMeta {
  type: string;
  label: string;
  target_table: string;
  instructions: string;
  columns: UploadColumnSpec[];
}

export interface UploadRowError {
  row: number;
  field?: string | null;
  message: string;
}

export interface UploadPreviewResponse {
  type: string;
  total_rows: number;
  valid: number;
  duplicates: number;
  errors: UploadRowError[];
  preview_token: string;
  valid_rows_sample: Record<string, unknown>[];
}

export interface UploadCommitResponse {
  inserted: number;
  skipped_duplicates: number;
}

export async function fetchUploadTypes(): Promise<{ items: UploadTypeMeta[] }> {
  const r = await fetch('/api/uploads/types', { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchUploadTypes ${r.status}`);
  return r.json();
}

export function templateUrl(type: string, fmt: 'csv' | 'xlsx'): string {
  const qs = new URLSearchParams({ type, fmt });
  return `/api/uploads/template?${qs.toString()}`;
}

export async function postPreview(type: string, file: File): Promise<UploadPreviewResponse> {
  const fd = new FormData();
  fd.append('file', file);
  const qs = new URLSearchParams({ type });
  const r = await fetch(`/api/uploads/preview?${qs.toString()}`, {
    method: 'POST', body: fd,
  });
  if (!r.ok) throw new Error(`postPreview ${r.status}`);
  return r.json();
}

export async function postCommit(token: string): Promise<UploadCommitResponse> {
  const r = await fetch('/api/uploads/commit', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ preview_token: token }),
  });
  if (r.status === 410) throw new Error('token_expired');
  if (!r.ok) throw new Error(`postCommit ${r.status}`);
  return r.json();
}
```

- [ ] **Step 1: Write file.**

- [ ] **Step 2: tsc clean.**

- [ ] **Step 3: DO NOT COMMIT.**

---

## Task 10: UI components — wizard

**Files:**
- Create: `web_app/components/data-upload/data-upload-dialog.tsx`
- Create: `web_app/components/data-upload/type-grid.tsx`
- Create: `web_app/components/data-upload/template-step.tsx`
- Create: `web_app/components/data-upload/preview-step.tsx`

DO NOT COMMIT.

- [ ] **Step 1: TypeGrid component**

`web_app/components/data-upload/type-grid.tsx`:

```tsx
'use client';
import { Database, Activity, Rabbit, Wheat } from 'lucide-react';
import type { UploadTypeMeta } from '@/lib/api/uploads-client';

const ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  milkings: Database,
  health_events: Activity,
  animals: Rabbit,
  feed_rations: Wheat,
};

interface Props {
  types: UploadTypeMeta[];
  onSelect: (type: UploadTypeMeta) => void;
}

export function TypeGrid({ types, onSelect }: Props) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
      {types.map((t) => {
        const Icon = ICONS[t.type] ?? Database;
        return (
          <button
            key={t.type}
            onClick={() => onSelect(t)}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 8, padding: 20, borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border)', background: 'var(--bg)',
              cursor: 'pointer', textAlign: 'center',
            }}
          >
            <Icon size={28} />
            <div style={{ fontWeight: 600 }}>{t.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.target_table}</div>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: TemplateStep component**

`web_app/components/data-upload/template-step.tsx`:

```tsx
'use client';
import { useState } from 'react';
import { Download, Upload as UploadIcon } from 'lucide-react';
import { templateUrl, postPreview, type UploadTypeMeta, type UploadPreviewResponse } from '@/lib/api/uploads-client';

interface Props {
  type: UploadTypeMeta;
  onPreview: (preview: UploadPreviewResponse) => void;
  onError: (msg: string) => void;
}

export function TemplateStep({ type, onPreview, onError }: Props) {
  const [busy, setBusy] = useState(false);

  async function handleFile(file: File) {
    setBusy(true);
    try {
      const preview = await postPreview(type.type, file);
      onPreview(preview);
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Тип: {type.label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 12 }}>
        {type.instructions}
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Колонки</div>
        <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 6, padding: 8 }}>
          {type.columns.map((c) => (
            <div key={c.name} style={{ fontSize: 12, padding: '3px 0', display: 'flex', gap: 8 }}>
              <span style={{ fontWeight: 600, minWidth: 110 }}>{c.name}</span>
              <span style={{ color: c.required ? 'var(--danger, #b00020)' : 'var(--text-muted)' }}>
                {c.required ? 'обяз.' : 'опц.'}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>{c.kind}</span>
              <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{c.description}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <a className="btn-outline"
           href={templateUrl(type.type, 'csv')}
           download
           style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Download size={14} /> Скачать CSV
        </a>
        <a className="btn-outline"
           href={templateUrl(type.type, 'xlsx')}
           download
           style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Download size={14} /> Скачать XLSX
        </a>
      </div>

      <label style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        gap: 8, padding: 24, border: '2px dashed var(--border)',
        borderRadius: 8, cursor: busy ? 'wait' : 'pointer',
        background: 'var(--bg-muted)',
      }}>
        <UploadIcon size={28} color="var(--text-muted)" />
        <span style={{ fontSize: 13 }}>
          {busy ? 'Анализ файла…' : 'Перетащите файл или нажмите для выбора'}
        </span>
        <input
          type="file"
          accept=".csv,.xlsx"
          disabled={busy}
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
      </label>
    </div>
  );
}
```

- [ ] **Step 3: PreviewStep component**

`web_app/components/data-upload/preview-step.tsx`:

```tsx
'use client';
import { useState } from 'react';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import { postCommit, type UploadPreviewResponse } from '@/lib/api/uploads-client';

interface Props {
  preview: UploadPreviewResponse;
  onCommitted: (count: number) => void;
  onCancel: () => void;
  onError: (msg: string) => void;
}

export function PreviewStep({ preview, onCommitted, onCancel, onError }: Props) {
  const [busy, setBusy] = useState(false);

  async function commit() {
    setBusy(true);
    try {
      const r = await postCommit(preview.preview_token);
      onCommitted(r.inserted);
    } catch (e) {
      const msg = String(e);
      if (msg.includes('token_expired')) onError('Сессия истекла, загрузите файл заново');
      else onError(msg);
    } finally {
      setBusy(false);
    }
  }

  const stat = (icon: React.ReactNode, color: string, label: string, n: number) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '6px 12px', borderRadius: 6,
      background: color + '15', color, fontSize: 13,
    }}>
      {icon}
      <strong>{n}</strong>
      <span>{label}</span>
    </div>
  );

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {stat(<CheckCircle2 size={14} />, '#10b981', 'готовы к загрузке', preview.valid)}
        {stat(<AlertTriangle size={14} />, '#f59e0b', 'дубликатов (пропустим)', preview.duplicates)}
        {stat(<XCircle size={14} />, '#ef4444', 'ошибок', preview.errors.length)}
      </div>

      {preview.errors.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Ошибки</div>
          <div style={{
            maxHeight: 200, overflowY: 'auto',
            border: '1px solid var(--border)', borderRadius: 6, padding: 8,
            fontSize: 12,
          }}>
            {preview.errors.slice(0, 20).map((e, i) => (
              <div key={i} style={{ padding: '3px 0' }}>
                <span style={{ color: 'var(--text-muted)' }}>Строка {e.row}</span>
                {e.field && <span style={{ color: 'var(--danger, #b00020)', marginLeft: 6 }}>[{e.field}]</span>}
                <span style={{ marginLeft: 6 }}>{e.message}</span>
              </div>
            ))}
            {preview.errors.length > 20 && (
              <div style={{ color: 'var(--text-muted)', marginTop: 6 }}>
                …и ещё {preview.errors.length - 20} ошибок
              </div>
            )}
          </div>
        </div>
      )}

      {preview.valid_rows_sample.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Превью валидных (первые 5)</div>
          <pre style={{
            maxHeight: 160, overflow: 'auto',
            background: 'var(--bg-muted)', padding: 8, borderRadius: 6,
            fontSize: 11, margin: 0,
          }}>
            {JSON.stringify(preview.valid_rows_sample, null, 2)}
          </pre>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button className="btn-outline" onClick={onCancel} disabled={busy}>Отмена</button>
        <button
          className="btn-primary"
          onClick={commit}
          disabled={busy || preview.valid === 0}
        >
          {busy ? 'Загружаю…' : `Подтвердить и загрузить (${preview.valid})`}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: DataUploadDialog (state machine)**

`web_app/components/data-upload/data-upload-dialog.tsx`:

```tsx
'use client';
import { useEffect, useState } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import { fetchUploadTypes, type UploadTypeMeta, type UploadPreviewResponse } from '@/lib/api/uploads-client';
import { TypeGrid } from './type-grid';
import { TemplateStep } from './template-step';
import { PreviewStep } from './preview-step';

function toast(msg: string) {
  if (typeof window === 'undefined') return;
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

interface Props {
  open: boolean;
  onClose: () => void;
}

type Step = 'type' | 'template' | 'preview';

export function DataUploadDialog({ open, onClose }: Props) {
  const [types, setTypes] = useState<UploadTypeMeta[]>([]);
  const [step, setStep] = useState<Step>('type');
  const [selected, setSelected] = useState<UploadTypeMeta | null>(null);
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep('type');
    setSelected(null);
    setPreview(null);
    setError(null);
    fetchUploadTypes()
      .then((r) => setTypes(r.items))
      .catch((e) => setError(String(e)));
  }, [open]);

  if (!open) return null;

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 220,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 24,
        width: '100%', maxWidth: 640, maxHeight: '90vh', overflow: 'auto',
        position: 'relative',
      }}>
        <button onClick={onClose} aria-label="Закрыть"
          style={{ position: 'absolute', top: 12, right: 12, background: 'none', border: 'none', cursor: 'pointer' }}>
          <X size={18} />
        </button>

        <h3 style={{ margin: '0 0 16px', fontSize: 18 }}>
          {step !== 'type' && (
            <button
              onClick={() => {
                if (step === 'preview') setStep('template');
                else if (step === 'template') setStep('type');
              }}
              aria-label="Назад"
              style={{ background: 'none', border: 'none', cursor: 'pointer', marginRight: 6 }}>
              <ArrowLeft size={16} />
            </button>
          )}
          Загрузить данные
          {step === 'template' && selected && <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}> — {selected.label}</span>}
        </h3>

        {error && (
          <div style={{ color: 'var(--danger, #b00020)', fontSize: 12, marginBottom: 12 }}>
            {error}
          </div>
        )}

        {step === 'type' && (
          types.length === 0 && !error
            ? <div style={{ color: 'var(--text-muted)' }}>Загрузка типов…</div>
            : <TypeGrid types={types} onSelect={(t) => { setSelected(t); setStep('template'); setError(null); }} />
        )}

        {step === 'template' && selected && (
          <TemplateStep
            type={selected}
            onPreview={(p) => { setPreview(p); setStep('preview'); setError(null); }}
            onError={setError}
          />
        )}

        {step === 'preview' && preview && (
          <PreviewStep
            preview={preview}
            onCommitted={(n) => { toast(`Загружено строк: ${n}`); onClose(); }}
            onCancel={onClose}
            onError={setError}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: tsc clean.**

```bash
cd /opt/genomeai/repo/web_app && npx tsc --noEmit 2>&1 | tail -10
```
Expected: clean.

- [ ] **Step 6: DO NOT COMMIT.**

---

## Task 11: FAB extension

**Files:**
- Modify: `web_app/components/app/fab.tsx`

- [ ] **Step 1: Read current FAB**

```bash
cat /opt/genomeai/repo/web_app/components/app/fab.tsx | head -50
```

You'll see the menu has 2 items: "Добавить событие" + "Спросить ИИ-помощника". Add a 3rd: "Загрузить данные".

- [ ] **Step 2: Modify imports**

At the top of the file, add `Upload` to the lucide-react imports and import the new dialog:

```tsx
import { Plus, X, CalendarPlus, Sparkles, Upload } from 'lucide-react';
import { DataUploadDialog } from '@/components/data-upload/data-upload-dialog';
```

- [ ] **Step 3: Add state for upload dialog**

Inside `FAB()`, near the existing `[menuOpen, setMenuOpen]` and `[aiOpen, setAiOpen]`:

```tsx
const [uploadOpen, setUploadOpen] = useState(false);
```

- [ ] **Step 4: Add handler**

After `handleAskAI`:

```tsx
function handleUpload() {
  setMenuOpen(false);
  setUploadOpen(true);
}
```

Update the `useEffect` keyboard listener to also clear upload on ESC:

```tsx
useEffect(() => {
  if (!menuOpen && !aiOpen && !uploadOpen) return;
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') { setMenuOpen(false); setAiOpen(false); setUploadOpen(false); }
  }
  document.addEventListener('keydown', onKey);
  return () => document.removeEventListener('keydown', onKey);
}, [menuOpen, aiOpen, uploadOpen]);
```

- [ ] **Step 5: Add menu item**

Find the existing `<div role="menu">` block. Add a new item AFTER the "Спросить ИИ-помощника" button (before the closing `</div>` of the menu):

```tsx
<div style={{ height: 1, background: 'var(--border)', margin: '0 12px' }} />
<button
  role="menuitem"
  onClick={handleUpload}
  style={menuItemStyle}
  onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-muted)'; }}
  onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
>
  <Upload size={16} color="var(--accent)" />
  Загрузить данные
</button>
```

- [ ] **Step 6: Render dialog at the end of the fragment**

Right before the closing `</>` fragment of the FAB component (after the existing AI assistant modal block), add:

```tsx
<DataUploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} />
```

- [ ] **Step 7: tsc**

```bash
cd /opt/genomeai/repo/web_app && npx tsc --noEmit 2>&1 | tail -10
```
Expected: clean.

- [ ] **Step 8: DO NOT COMMIT** — bundle into Task 12.

---

## Task 12: Commit frontend bundle

```bash
cd /opt/genomeai/repo
git add web_app/app/api/uploads/ \
        web_app/lib/api/uploads-client.ts \
        web_app/components/data-upload/ \
        web_app/components/app/fab.tsx
git status
```
Verify: 4 created routes + 1 client + 4 wizard components + 1 modified fab. NO PNGs.

```bash
git commit -m "$(cat <<'EOF'
feat(uploads): FAB wizard for CSV/XLSX data upload

- New "Загрузить данные" item in FAB menu (third option)
- 4-step wizard: type select → template+upload → preview → commit
- Server-generated CSV (UTF-8 BOM) and XLSX (formatted) templates
- Preview shows valid/duplicate/error counts + first 20 errors with
  row+field+message + first 5 valid rows
- Commit consumes one-shot token; toast on success
- 410 (token expired) → "Сессия истекла, загрузите файл заново"

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Playwright validation

**Files:** screenshots only.

- [ ] **Step 1: Restart uvicorn so new routes are loaded**

```bash
pkill -f "uvicorn web_cabinet.app:app" || true
sleep 1
cd /opt/genomeai/repo
nohup .venv/bin/python3 -m uvicorn web_cabinet.app:app --host 0.0.0.0 --port 8000 --log-level warning > /tmp/uvicorn.log 2>&1 &
sleep 4
curl -s -o /dev/null -w "uploads types: %{http_code}\n" http://localhost:8000/api/app/v1/uploads/types
# expected: 401 (auth)
```

- [ ] **Step 2: Playwright sequence**

Use `mcp__playwright__browser_*` tools.

1. `browser_navigate http://localhost:3000/login`
2. Login as `admin`/`admin`
3. Navigate to any /protected page (e.g., `/dashboard`)
4. Click the FAB (`+` button bottom-right)
5. Take screenshot → `data-upload-fab.png`
6. Click "Загрузить данные" → wizard opens at Step 1
7. Take screenshot → `data-upload-step1.png`
8. Click the "Надои" card → Step 2 (template + upload)
9. Take screenshot → `data-upload-template.png`
10. (Optional, if a tiny CSV file can be created in-browser via download then re-upload) — skip if too complex; focus on Step 1 + Step 2 evidence
11. To test commit flow, generate a test CSV in the browser using `mcp__playwright__browser_evaluate`:
    ```js
    const csv = '﻿animal_id,date,milk_kg\n1,2026-05-15,28.5\n2,2026-05-15,30.0\n';
    const blob = new Blob([csv], {type:'text/csv'});
    const file = new File([blob], 'test.csv', {type:'text/csv'});
    // Set the file on the input
    const input = document.querySelector('input[type=file]');
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event('change', {bubbles:true}));
    ```
12. Wait for preview step. Take screenshot → `data-upload-preview.png`
13. Click "Подтвердить и загрузить" → Toast or close. Take screenshot → `data-upload-success.png`

- [ ] **Step 3: Document gaps**

If steps 11-13 fail (e.g., backend lookup of dm_animals returns FK-missing for test IDs), document in proof. The first 3 screenshots (FAB, step1, template) should always succeed.

- [ ] **Step 4: Commit screenshots**

```bash
cd /opt/genomeai/repo
git add data-upload-fab.png data-upload-step1.png data-upload-template.png \
        data-upload-preview.png data-upload-success.png
# Add only successfully captured ones
git status
git commit -m "$(cat <<'EOF'
chore(uploads): playwright evidence for data upload wizard

Live UI captures: FAB menu with new item, type grid, template step,
preview, success toast.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: 7 CI gates + execution proof

**Files:**
- Create: `docs/iterations/T34-data-upload-fab_execution_proof.md`

- [ ] **Step 1: Run gates**

```bash
cd /opt/genomeai/repo
mkdir -p artifacts/_ci
bash scripts/run_ci_gate.sh 2>&1 | tail -30 > artifacts/_ci/gate_1_pytest.log
RC1=$?; echo "EXIT_1=$RC1"

python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
  --timing-json artifacts/_ci/web_smoke.json 2>&1 | tee artifacts/_ci/gate_2_web_smoke.log | tail -10
RC2=${PIPESTATUS[0]}; echo "EXIT_2=$RC2"

python -m genomeai.cli verify_refactor --project-root . --golden golden \
  --report-root artifacts/_ci/verify_refactor 2>&1 | tee artifacts/_ci/gate_3_verify_refactor.log | tail -10
RC3=${PIPESTATUS[0]}; echo "EXIT_3=$RC3"

bash scripts/run_warning_governance_gate.sh 2>&1 | tail -30 > artifacts/_ci/gate_4_warning_governance.log
RC4=$?; echo "EXIT_4=$RC4"

bash scripts/run_operational_rollout_gate.sh 2>&1 | tail -30 > artifacts/_ci/gate_5_operational_rollout.log
RC5=$?; echo "EXIT_5=$RC5"

bash scripts/run_competitive_acceptance_gate.sh 2>&1 | tail -30 > artifacts/_ci/gate_6_competitive_acceptance.log
RC6=$?; echo "EXIT_6=$RC6"

bash scripts/run_perf_gates.sh 2>&1 | tail -30 > artifacts/_ci/gate_7_perf.log
RC7=$?; echo "EXIT_7=$RC7"

echo "FINAL: 1=$RC1 2=$RC2 3=$RC3 4=$RC4 5=$RC5 6=$RC6 7=$RC7"
```

Note: gates 5/6 and possibly 7 expected to be red (pre-existing regressions).

- [ ] **Step 2: Run targeted upload pytest**

```bash
cd /opt/genomeai/repo && pytest tests/test_uploads_template.py tests/test_uploads_parse.py tests/test_uploads_validation.py tests/test_uploads_commit.py -v 2>&1 | tail -25
```
Expected: ~25 PASSED.

- [ ] **Step 3: Write proof file**

`docs/iterations/T34-data-upload-fab_execution_proof.md`:

```markdown
# T34 — Data Upload via FAB: execution proof

## Scope

Add a 4-step wizard launched from the FAB menu for uploading CSV/XLSX
files into 4 dm_* tables (milkings, health_events, animals, feed_rations).
TYPE_REGISTRY drives templates + validation + INSERT.

Plan: docs/superpowers/plans/2026-05-07-data-upload-fab.md
Spec: docs/superpowers/specs/2026-05-07-data-upload-fab-design.md

## Executed checks

### CLAUDE.md §4 — 7 CI gates

| # | Gate | Result | Exit | Artifact |
|---|------|--------|------|----------|
| 1 | pytest | <fill> | <fill> | gate_1_pytest.log |
| 2 | web smoke | <fill> | <fill> | web_smoke.json + gate_2.log |
| 3 | verify_refactor | <fill> | <fill> | gate_3.log |
| 4 | warning governance | <fill> | <fill> | gate_4.log |
| 5 | operational rollout | <fill> | <fill> | gate_5.log |
| 6 | competitive acceptance | <fill> | <fill> | gate_6.log |
| 7 | performance | <fill> | <fill> | gate_7.log |

### Targeted uploads pytest

`pytest tests/test_uploads_*.py` → <fill — should be ~25 PASSED>

### Live UI validation

Playwright screenshots committed: data-upload-fab.png, data-upload-step1.png,
data-upload-template.png, data-upload-preview.png, data-upload-success.png.

## Failure analysis (gates 5/6 if red)

Pre-existing `validate-foundation.mjs:60` regression from commit 7b08924.
Untouched by this PR.

## Net result

<fill>. Spec acceptance criteria 1-9 verified.

## Honest status

`partially_proven` (if gates 5/6 red), or `proven` (if all 7 green).
```

Fill in `<fill>` placeholders with actual results.

- [ ] **Step 4: Commit proof**

```bash
git add docs/iterations/T34-data-upload-fab_execution_proof.md
git commit -m "$(cat <<'EOF'
docs(t34): execution proof for data upload via FAB wizard

7 CI gates run; targeted uploads pytest 25/25 passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Checklist

- ✅ Spec §1–§11 covered:
  - §4 Architecture → all tasks
  - §5 Contracts → Task 1
  - §6 Backend → Tasks 2-7 (registry, parse, validate, commit, boundary)
  - §7 Frontend → Tasks 8-11 (proxies, client, components, FAB)
  - §8 Error handling → covered in tests + UI states
  - §9 Tests → Tasks 2-4, 13
  - §10 Implementation order → mirrored
  - §11 Risks → noted in spec; multi-worker single-process limit accepted
- ✅ No placeholders or TBDs
- ✅ Type consistency: `UploadType`, `UploadColumnSpec`, `UploadPreviewResponse`, `UploadCommitResponse` defined in Task 1, used identically in Tasks 2-12
- ✅ Commits split per CLAUDE.md §11: backend / frontend / screenshots / proof
