# Задача PMV-B06: CSV Import — миграция данных пилотных ферм

**PROMPT:**

## Контекст
- `CLAUDE.md`, `docs/audit/AUDIT_REPORT.md`
- Worktree: `wt-iot` (ветка `b/iot`)
- В архиве УЖЕ ЕСТЬ `genomeai.connectors_v1` (1508 LoC) + готовые YAML mappings:
  - `configs/mappings/connectors/dairycomp_305/`
  - `configs/mappings/connectors/selex_basic/`
  - `configs/mappings/connectors/onec_livestock/`
- Это критическое преимущество — фермы не на пустом месте, у всех уже есть учёт

## Цель
1. Backend endpoint `POST /api/import/csv` — multi-part upload + vendor selection
2. Frontend page `/connections/import` — 3-step wizard

## Зоны параллельной работы

Этот worktree (`wt-iot`) трогает:
- `web_cabinet/import_endpoints.py` (новый)
- `web_app/app/(protected)/connections/import/page.tsx` (новый)
- `web_app/components/connections/csv-import-wizard.tsx` (новый)
- `web_cabinet/iot/tests/test_csv_import.py`
- `docs/pilot_export_guides.md`

НЕ ТРОГАЙ:
- `web_cabinet/analytics/`
- `web_cabinet/ai/`

## Backend endpoint

```python
VENDOR_OPTIONS = Literal["dairycomp_305", "selex_basic", "onec_livestock"]
TABLE_OPTIONS = Literal["animals", "lactations", "treatments", "testday", "health_events"]

@router.post("/api/import/csv")
async def import_csv_file(
    tenant_id: str = Form(...),
    vendor: VENDOR_OPTIONS = Form(...),
    table: TABLE_OPTIONS = Form(...),
    file: UploadFile = File(...),
):
    """
    1. Save to tmp
    2. Apply mapping через genomeai.connectors_v1.apply_connector()
    3. QC через genomeai.qc_v2.run_qc_v2()
    4. Если has_blockers → return preview + reject
    5. Иначе → UPSERT в БД
    """
```

## Frontend wizard

```tsx
export function CSVImportWizard() {
  const [step, setStep] = useState<1|2|3>(1);
  const [vendor, setVendor] = useState<string>();
  const [tableType, setTableType] = useState<string>();
  const [file, setFile] = useState<File>();
  const [preview, setPreview] = useState<any>();
  
  return (
    <>
      {step === 1 && <VendorPickerStep onSelect={(v) => { setVendor(v); setStep(2); }} />}
      {step === 2 && <TableAndFileStep onComplete={(t, f) => {
         setTableType(t); setFile(f);
         // Preview через POST /api/import/csv?dry_run=true
         setStep(3);
      }} />}
      {step === 3 && <PreviewAndConfirmStep
         preview={preview}
         onConfirm={async () => {
           // Real POST
         }}
      />}
    </>
  );
}
```

## Acceptance criteria

1. Endpoint работает на DC305 sample (`data/examples/dairycomp_305/animals_sample.csv`)
2. Endpoint работает на Selex sample
3. Endpoint работает на 1С sample
4. Frontend wizard рендерит 3 шага
5. Preview показывает первые 5 канонических строк после mapping
6. QC warnings отображаются inline в UI (не блокируют)
7. QC blockers блокируют import + показывают что не так
8. Tests:
   - `test_dc305_animals_import_happy_path`
   - `test_selex_with_unmapped_columns_returns_qc_warning`
   - `test_blocker_rejects_import`
   - `test_idempotency_no_duplicates`
   - `test_large_csv_10k_rows_completes`
9. **Russian copy** в UI — "Загрузка CSV", "Источник данных", "Тип таблицы", "Подтвердить"

## Документация для пилотов

`docs/pilot_export_guides.md`:
- Раздел 1: Как экспортировать из DairyComp 305 (DC305 → File → Export → CSV)
- Раздел 2: Как из Селекс (отчёты → выгрузка)
- Раздел 3: Как из 1С: Селекция (обработка → выгрузка)
- Какие колонки обязательны в каждом случае
- Скриншоты (placeholder, заполнить в Неделе 5)

## Что НЕ делать

- ❌ Не создавать новые connectors — все 3 уже в `connectors_v1.py`
- ❌ Не дублировать QC — используй `qc_v2`

## Формат ответа

T34 — `docs/iterations/PMV-B06_execution_proof.md` + screenshots wizard.
