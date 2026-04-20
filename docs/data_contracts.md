# Data Contracts (P0)

Контракты лежат в `configs/contracts/*.json`:

- `dm_farms.json`
- `dm_animals.json`
- `dm_lactations.json`
- `dm_testday.json` (опционально)

Проверки A0:
- наличие обязательных файлов (кроме dm_testday),
- наличие обязательных колонок,
- типы значений (int/float/bool/date/string),
- allowed_values (если задано).


## T13-03 / шаг 1

Добавлен машиночитаемый каталог контрактов `configs/contracts/catalog.json` и CLI-экспорт:

```bash
genomeai contracts-catalog \
  --contracts configs/contracts \
  --catalog configs/contracts/catalog.json \
  --output artifacts/system/data_contract_catalog.json
```

Что попадает в каталог:
- `dataset`, `contract_version`, `status`, `domain`;
- обязательные поля и PK/FK;
- примеры файлов и найденные mapping templates;
- статус покрытия QC (`covered/planned/n/a`) для UI каталога схем.

## T13-03 / шаг 2

Добавлена pre-ingest contract validation для исходных файлов + mapping YAML:

- web `/upload/ingest-all` валидирует файл до постановки job в очередь;
- connector run валидирует выбранный binding до записи в canonical;
- ошибки показываются в человекочитаемом виде: dataset, строка, поле, пример значения;
- результаты валидации логируются в `audit_log` (`action=contract.validate`);
- для connector runs сохраняется JSON-отчет `contract_validation_<dataset>.json` рядом с `manifest.json`.

Добавлены reusable mapping templates:

- `configs/mappings/templates/selex/*.yaml`
- `configs/mappings/templates/1c/*.yaml`
- `configs/mappings/templates/excel/*.yaml`

Каталог контрактов теперь автоматически подхватывает шаблоны из `configs/mappings/templates/**`.


## T13-03 / шаг 3

Добавлен UI Data Catalog 2.0:

- HTML-страница `/contracts` показывает схемы, версии, обязательные поля, examples, QC coverage и reusable mapping templates;
- JSON API `/api/contracts/catalog` отдает тот же каталог для UI/интеграций;
- каталог поддерживает фильтры по domain / status / source system и текстовый поиск;
- шаблоны mapping отображаются с путями, source system, числом колонок и `dayfirst`.

Дополнительно каталог теперь можно выгружать не только в JSON, но и в Markdown:

```bash
genomeai contracts-catalog   --contracts configs/contracts   --catalog configs/contracts/catalog.json   --output artifacts/system/data_contract_catalog.json   --markdown-output docs/contracts/catalog.md
```

## T13-03 step4
- Upload и connector run detail теперь содержат deeplink на контракт и на validation report.
- Validation report доступен в web-cabinet через `/contracts/validation-report` и в JSON через `/api/contracts/validation-report`.
- При failed pre-ingest validation отчет сохраняется в `artifacts/<data_version>/contract_precheck/...`.
