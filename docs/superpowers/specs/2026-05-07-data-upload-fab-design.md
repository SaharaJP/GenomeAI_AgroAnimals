# Design: Data Upload via FAB (CSV / XLSX)

**Status:** Approved (brainstorm phase)
**Date:** 2026-05-07
**Owner:** AI assistant + project lead
**Scope:** GenomeAI AgroAnimals — manual data upload from the web UI through a wizard launched by the FAB button

## 1. Problem

Operators currently have only two ways to enter data into GenomeAI: (1) the AI assistant (free-text Q&A, doesn't write to canonical tables), and (2) timeline events (only event records). For routine operational data — daily milkings, health events, new animal registrations, ration changes — there is no in-app data-entry path. Operators must SSH or use the legacy HTML `/upload` page (which is part of the frozen `web_cabinet` legacy surface and not exposed in the new web app).

The user wants a button on the floating action button (FAB, bottom-right corner of every page) that opens a wizard:
1. Pick a data type
2. Download a pre-built CSV or XLSX template
3. Fill it in offline
4. Upload the filled file
5. See a preview of valid rows / duplicates / errors
6. Commit valid rows

## 2. Goals

1. New third FAB menu item: "Загрузить данные".
2. 4 supported data types in v1: `milkings`, `health_events`, `animals`, `feed_rations`.
3. Server-generated CSV and XLSX templates (consistent with the live schema, not stale static files).
4. Both formats accepted on upload (auto-detected by extension).
5. Preview-then-commit flow: every upload first runs validation and shows row-level errors before any DB write.
6. Duplicate detection (existing rows skipped, not errored).
7. All 7 CI gates pass before `proven` claim.

## 3. Non-Goals

- Editing or deleting existing rows through the wizard. Append-only semantics.
- Real-time streaming validation (validate-as-you-type). Server-side batch validation only.
- Bulk export of existing data through this wizard. Use existing reports surface for export.
- Multi-tenant cross-farm uploads — uploads are scoped to the caller's `tenant_id` (active farm).
- Background processing for large files (>10 000 rows). v1 is synchronous.
- Schema editing UI for ColSpecs. Adding a new type is a code change.

## 4. Architecture

```
┌─ Frontend (Next.js) ──────────────────────────────┐
│  FAB → "Загрузить данные"                         │
│  └─ <DataUploadDialog> (4-step wizard)            │
│     ├─ Step 1 <TypeGrid>     pick type            │
│     ├─ Step 2 <TemplateStep> download + upload    │
│     ├─ Step 3 <PreviewStep>  show stats + commit  │
│     └─ Step 4: success toast                      │
│                                                   │
│  API calls:                                       │
│   GET  /api/uploads/template?type=&fmt=           │
│   POST /api/uploads/preview   (multipart)         │
│   POST /api/uploads/commit    (JSON {token})      │
└──────────────────┬────────────────────────────────┘
                   │ proxy w/ auth-token forward
┌──────────────────▼────────────────────────────────┐
│  Backend FastAPI (web_cabinet)                    │
│  /api/app/v1/uploads/*  (boundary, new)           │
│   └─ uploads_v1.py                                │
│       ├─ TYPE_REGISTRY: { type → UploadType }     │
│       ├─ generate_template(type, fmt) → bytes     │
│       ├─ parse_file(type, file_bytes) → rows      │
│       ├─ validate_rows(type, rows) → result       │
│       └─ commit_rows(type, valid_rows) → count    │
│                                                   │
│  Cache: in-memory dict { token → cached_rows }    │
│         TTL 5 minutes                             │
└──────────────────┬────────────────────────────────┘
                   │ pandas + openpyxl + psycopg
              ┌────▼─────────────────┐
              │ dm_milkings_daily    │
              │ dm_health_events     │
              │ dm_animals           │
              │ dm_feed_rations      │
              └──────────────────────┘
```

Single source of truth for column specs is `TYPE_REGISTRY` in `web_cabinet/uploads_v1.py`. Templates, validation, and INSERT all derive from this dict — schema drift between the three is impossible by construction. Adding a new type is a registry entry plus tests.

## 5. Data Model

No DB schema changes. All four target tables already exist (`dm_milkings_daily`, `dm_health_events`, `dm_animals`, `dm_feed_rations`).

### Pydantic contracts (`packages/contracts/api_boundary_v1.py`)

```python
class UploadColumnSpec(BaseModel):
    name: str
    required: bool = True
    kind: str = 'str'         # str|int|float|date
    description: str = ''
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    fk_table: Optional[str] = None  # if FK lookup needed


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
    total_rows: int
    valid: int
    duplicates: int
    errors: list[UploadRowError] = Field(default_factory=list)
    preview_token: str
    valid_rows_sample: list[dict[str, Any]] = Field(default_factory=list)


class UploadCommitRequest(BaseModel):
    preview_token: str


class UploadCommitResponse(BaseModel):
    schema: str = 'genomeai.api.uploads.commit.v1'
    inserted: int
    skipped_duplicates: int
```

### Internal data classes (not exposed)

```python
@dataclass
class UploadType:
    label: str
    target_table: str
    columns: list[UploadColumnSpec]
    unique_key: list[str]      # columns forming the dedup key
    sample_row: dict[str, Any] # for the template's example row
    instructions: str
```

## 6. Backend

### 6.1 Type registry (`web_cabinet/uploads_v1.py`)

Four entries:

**milkings:**
- target_table: `dm_milkings_daily`
- columns: animal_id, date, milk_kg, scc_cells_ml (opt), fat_pct (opt), protein_pct (opt)
- unique_key: `(tenant_id, animal_id, date)`

**health_events:**
- target_table: `dm_health_events`
- columns: animal_id, event_date, event_type, treatment, withdrawal_days (opt), notes (opt)
- unique_key: `(tenant_id, animal_id, event_date, event_type)`

**animals:**
- target_table: `dm_animals`
- columns: animal_id, ext_id (opt), birth_date, sex (cow|heifer|bull), breed (opt), current_pen_id (opt)
- unique_key: `(tenant_id, animal_id)`

**feed_rations:**
- target_table: `dm_feed_rations`
- columns: ration_id, valid_from (date), valid_to (opt), pen_group, ingredients_json (str), notes (opt)
- unique_key: `(tenant_id, ration_id, valid_from)`

The exact columns per type are derived from each table's actual schema (read via `\d` on first implementation; the spec sets the user-facing minimum that's required + a sensible optional set).

### 6.2 Template generation

`generate_template(type_id: str, fmt: 'csv'|'xlsx') -> bytes`:

- CSV: header row of column names + one example row from `sample_row`. Encoded UTF-8 with BOM (Excel-friendly).
- XLSX: row 1 = column names; row 2 = inline instructions (`required`, type, range); row 3 = sample row; bold header. Uses openpyxl Workbook in-memory then `save(BytesIO)`.

Returns `(bytes, content_type, filename)` tuple.

### 6.3 Parse + validate

`parse_file(type_id: str, file_bytes: bytes, filename: str) -> list[dict]`:

- Detect format by extension (`.csv` or `.xlsx`).
- pandas read (`read_csv` or `read_excel`).
- Drop fully-empty rows.
- Cast types per column spec; keep raw values on coercion failure (validator surfaces them).

`validate_rows(type_id: str, rows: list[dict], tenant_id: str) -> ValidationResult`:

- For each row: check required, type, range.
- Collect FK targets in batches: e.g., for `milkings`, gather all unique `animal_id` values, then run `SELECT animal_id FROM dm_animals WHERE tenant_id=%s AND animal_id = ANY(%s)`. Animals not present → row is invalid with `field='animal_id', message='не существует'`.
- Detect duplicates: query by `unique_key` columns in batches; matched rows go to `duplicates` bucket (not errors). For the `dm_milkings_daily` example, a tuple `(tenant_id, animal_id, date)` already in DB → duplicate.
- Return:
  ```python
  {
    'valid_rows': [...],          # ready to insert
    'duplicates': [...],          # already exist
    'errors': [{'row': i, 'field': 'X', 'message': '...'}, ...],
  }
  ```

### 6.4 Token cache

In-memory `dict[token, CachedPreview]` keyed by random `token = secrets.token_hex(8)`. Each entry includes `valid_rows`, `tenant_id`, `type_id`, `created_at`. Background sweep every minute removes entries older than 5 minutes (kept simple — single-process server).

(Multi-worker uvicorn breaks this. Note: production guard — if `WORKERS > 1`, a Redis-backed cache is required. v1 ships with in-memory + a documented limitation. Backend is currently single-worker so this is fine.)

### 6.5 Commit

`commit_rows(token: str, user) -> UploadCommitResponse`:

- Look up cache entry; if missing or expired → 410 Gone.
- Re-check tenant_id matches user's active farm (defense in depth).
- INSERT `valid_rows` into target table within a single transaction. Use `ON CONFLICT (unique_key) DO NOTHING` so race-condition duplicates are silent skips, not errors.
- Delete the cache entry on success (one-shot token).
- Return `{ inserted, skipped_duplicates }`.

### 6.6 Boundary routes (`web_cabinet/api_boundary_v1.py`)

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/app/v1/uploads/types` | List of all upload types with column specs |
| GET | `/api/app/v1/uploads/template` | `?type=&fmt=csv\|xlsx` — file download |
| POST | `/api/app/v1/uploads/preview` | multipart `?type=` body=file → `UploadPreviewResponse` |
| POST | `/api/app/v1/uploads/commit` | JSON `{ preview_token }` → `UploadCommitResponse` |

Permissions: GET endpoints `tasks.view`. POST endpoints `tasks.create`.

### 6.7 File size limit

Reuse existing `save_upload_limited` helper (`web_cabinet/utils.py`). Cap at 10 MB. Larger → 413.

## 7. Frontend

### 7.1 New routes (`web_app/app/api/uploads/`)

- `types/route.ts` — GET (proxy)
- `template/route.ts` — GET (proxy; pass-through `Content-Type` and `Content-Disposition` headers)
- `preview/route.ts` — POST (multipart pass-through; the Next.js handler should preserve the multipart body)
- `commit/route.ts` — POST (JSON proxy)

### 7.2 Typed client (`web_app/lib/api/uploads-client.ts`)

```ts
export interface UploadColumnSpec { name: string; required: boolean; kind: string; description: string; min_val?: number; max_val?: number; fk_table?: string }
export interface UploadTypeMeta { type: string; label: string; target_table: string; instructions: string; columns: UploadColumnSpec[] }
export interface UploadRowError { row: number; field?: string; message: string }
export interface UploadPreviewResponse { type: string; total_rows: number; valid: number; duplicates: number; errors: UploadRowError[]; preview_token: string; valid_rows_sample: Record<string, unknown>[] }
export interface UploadCommitResponse { inserted: number; skipped_duplicates: number }

export async function fetchUploadTypes(): Promise<{ items: UploadTypeMeta[] }>
export function templateUrl(type: string, fmt: 'csv'|'xlsx'): string  // returns "/api/uploads/template?type=...&fmt=..."
export async function postPreview(type: string, file: File): Promise<UploadPreviewResponse>
export async function postCommit(token: string): Promise<UploadCommitResponse>
```

### 7.3 UI components (`web_app/components/data-upload/`)

`data-upload-dialog.tsx` — main wizard (state machine over 4 steps).

`type-grid.tsx` — Step 1: 4 cards with icons, labels, brief descriptions. Click → state advances to step 2 with the chosen type.

`template-step.tsx` — Step 2: shows the column spec table (name, required, type, description), two download buttons (CSV / XLSX) that hit `templateUrl(...)` via `<a href download>`, and a file picker (drag-drop + click). On file pick → `postPreview` → state advances to step 3.

`preview-step.tsx` — Step 3: numeric stats (valid/duplicates/errors counts), a scrollable list of up to 20 errors with `row`, `field`, `message`, the `valid_rows_sample` table preview (first 5 rows), Cancel + "Подтвердить и загрузить" buttons. Confirm → `postCommit` → step 4.

Step 4: success toast; modal closes; if the active surface is one that should refresh (e.g., user uploaded milkings while on /analytics), the parent page is responsible for its own refresh — wizard doesn't reach into other surfaces.

### 7.4 FAB extension

Modify `web_app/components/app/fab.tsx`: add a third menu item "Загрузить данные" with the `Upload` icon from lucide-react. Click → opens `<DataUploadDialog>`.

### 7.5 Localization

UI labels in Russian (matching the rest of the app): "Загрузить данные", "Тип данных", "Скачать шаблон CSV", "Скачать шаблон XLSX", "Перетащите файл или нажмите для выбора", "Подтвердить и загрузить", "Отмена", "Дубликатов: N", "Ошибок: N", "Готовых к загрузке: N", "Загружено N строк".

## 8. Error Handling

| Case | Behavior |
|---|---|
| Unsupported extension (.txt, .pdf) | preview returns 400 with `{error: 'unsupported_format', accepted: ['csv', 'xlsx']}` |
| File > 10 MB | 413 from `save_upload_limited` |
| Empty file | preview returns `total_rows=0, errors=[{row:0, message:'Файл пуст'}]` |
| Missing required column in header | preview returns single error `row=0, message='Отсутствует колонка X'`; no row processing |
| Extra columns in header | warning but accepted (extra columns ignored) |
| Type coercion fails | row → error with `field`, `message='Неверный тип'` |
| Range violation | row → error with `field`, `message='Значение V вне диапазона [min,max]'` |
| FK target missing | row → error with `field`, `message='ID X не существует'` |
| Duplicate row | row → duplicate (not error) |
| `preview_token` expired | commit returns 410 Gone, frontend toast "Сессия истекла, загрузите файл заново" |
| Concurrent commit of same token | first wins, second → 409 with `{error: 'token_already_consumed'}` |
| Tenant_id mismatch on commit | 403 (token belongs to other user/farm) |
| INSERT transaction error | rollback, 500, frontend toast "Не удалось сохранить, попробуйте снова" |
| Multi-worker uvicorn (token cache split brain) | documented limitation; out-of-scope for v1 |

## 9. Testing

### 9.1 Pytest

`tests/test_uploads_v1_milkings.py`:
- Happy path: parse a 5-row CSV → validate → commit → verify all 5 inserted
- XLSX path: parse XLSX → same outcome
- Date format alternates: ISO and `DD.MM.YYYY` both accepted

`tests/test_uploads_validation.py`:
- Required missing → error
- Type coercion failure → error
- Range violation → error
- FK missing → error
- Duplicate detected → goes into duplicates bucket, not errors

`tests/test_uploads_template.py`:
- For each of 4 types, CSV template has correct headers
- For each of 4 types, XLSX template parses back into a valid dict via openpyxl

`tests/test_uploads_preview_token.py`:
- TTL: token created, sleep 6 min, commit returns 410
- Single-shot: commit twice → second 409
- Tenant guard: token issued to user A, user B commits → 403

### 9.2 Playwright

Boot stack, login as `admin`/`admin`, capture in repo root:

- `data-upload-fab.png` — FAB menu shows the new "Загрузить данные" item
- `data-upload-step1.png` — Step 1 type selection grid
- `data-upload-template.png` — Step 2 with column table + download buttons
- `data-upload-preview.png` — Step 3 with valid/duplicate/error counts
- `data-upload-success.png` — toast after successful commit

### 9.3 Acceptance Criteria

1. FAB menu has 3 items including the new "Загрузить данные".
2. Wizard opens; type grid lists 4 types with labels.
3. CSV download produces a file with header + sample row, encoding UTF-8 with BOM.
4. XLSX download opens cleanly in Excel/LibreOffice with formatted header.
5. Upload of a CSV with 1 valid + 1 duplicate + 1 invalid row produces preview with `valid=1, duplicates=1, errors=[1]`.
6. Commit inserts the valid row into `dm_milkings_daily` and skips the duplicate.
7. Token expiry returns 410 after 5 minutes.
8. Tenant mismatch on commit returns 403.
9. All 7 CI gates from `CLAUDE.md §4` pass.

## 10. Implementation Plan (high-level)

1. Pydantic contracts (`packages/contracts/api_boundary_v1.py`)
2. `web_cabinet/uploads_v1.py` — TYPE_REGISTRY + generate_template + parse_file + validate_rows + commit_rows + token cache
3. Pytest for all 4 types + edge cases (token TTL, FK, duplicate)
4. Boundary routes in `web_cabinet/api_boundary_v1.py`
5. Backend bundle commit
6. Next.js API proxies (`web_app/app/api/uploads/`)
7. Typed client (`web_app/lib/api/uploads-client.ts`)
8. UI components: dialog + type-grid + template-step + preview-step
9. FAB extension (`web_app/components/app/fab.tsx`)
10. Frontend bundle commit
11. Playwright validation + screenshots
12. 7 CI gates + execution proof

Commits split per CLAUDE.md §11: backend / frontend / screenshots / proof. No DB migration needed.

## 11. Risks and Assumptions

- **Multi-worker token cache split brain.** v1 cache is in-memory single-process. If the deployment ever scales to multiple uvicorn workers, the wizard breaks because step-2 token may live on worker A while step-3 commit hits worker B. Mitigation: documented as known limitation; if/when needed, swap the cache for Redis (interface stays the same).
- **CSV encoding.** Russian fields require UTF-8. We add BOM for Excel friendliness. If users produce files in Windows-1251 (legacy Russian Excel), parsing may produce gibberish — surfaced as range/type errors rather than corrupting data. Mitigation: documented in template instructions, parser tries `utf-8-sig` first then `utf-8` then `cp1251` as a final fallback.
- **Schema drift.** TYPE_REGISTRY is the source of truth for templates and validation. The actual DB schema can drift if migrations add columns. Mitigation: include a unit test that runs `pg_introspect` on each target table and asserts every required column in the registry exists in the DB.
- **No background processing.** Synchronous commit blocks the request thread for the duration of INSERT. For 10 000-row files this could take seconds. Mitigation: enforce 10 MB / ~10 000 row soft limit (one warning at 5 000+ rows in the preview). Larger uploads are out of scope.
- **AI is not used in this feature.** No Claude calls. Worth noting because the user has been asking for AI-driven things — this one is deliberately deterministic.
- **Pre-existing gates 5/6 regression** from commit `7b08924` will still apply. Mark `partially_proven` if needed.
