# T0-02 — Master ID + дедупликация + lineage (Target)

Версия: **v1.0**  
Статус: **Спецификация (без кода)**  
Принцип: **никаких “тихо исправили”** — любые изменения идентичности/слияния/разделения и любые “исправления” полей фиксируются как **события** в lineage + audit_log.

---

## 0) Термины и цели

### Термины
- **tenant_id** — организация/хозяйство (граница мульти‑арендности). On‑prem может быть один tenant, но модель должна поддерживать несколько.
- **source_system** — источник данных (farm_erp, milking_parlor, sensor_vendor_x, lab_y, manual_ui, …).
- **source_animal_id** — идентификатор животного в конкретном источнике.
- **alias** — альтернативный идентификатор (бирка/ear_tag, RFID, transponder_id, local_animal_id, …).
- **master_animal_id (MAID)** — единый “мастер‑ID” животного в системе Target.

### Цели
1) Ввести **master_animal_id** для связки “учётка↔сенсоры↔лабы↔события” без изменения входных форматов MVP.
2) Описать mapping-таблицы и протоколы **merge/split** + аудит.
3) Описать **правила доверия источникам** и разрешение конфликтов (по полю).

### Не‑цели (на этом шаге)
- Реализация алгоритмов/кода.
- “Умная” ML‑дедупликация (может появиться позже как опция), здесь только протокол и минимальные правила.

---

## 1) Стратегия `master_animal_id`

### 1.1 Формат и жизненный цикл
- `master_animal_id` — строковый ID (рекомендуется **ULID** или UUIDv7 для сортировки по времени).
- Рекомендуемый формат: `MA_<26char_ulid>` (пример: `MA_01JH8Y8P5Q2P7V9B2J4D6W2G1A`).
- MAID **никогда не переиспользуется**.
- Жизненные статусы:
  - `active` — текущий мастер.
  - `superseded` — мастер “поглощён” в результате merge (сохраняется как “надгробие”).
  - `split_source` — мастер был источником split (после split может остаться active, если часть данных остаётся за ним).
  - `archived` — выбытие/закрытие животного (для истории).

### 1.2 Совместимость с MVP
- `animal_id` из MVP **не меняем**. Он становится **одним из alias**.
- Новые Target-сущности (SensorsDaily, HealthEvents, Lab/TestDay и др.) должны ссылаться на:
  - **либо** `master_animal_id` (предпочтительно в Target),
  - **либо** на `(source_system, source_animal_id)` с обязательной последующей привязкой к MAID.

### 1.3 Где MAID используется
- В Target все “факты/события” по животному должны иметь:
  - `master_animal_id` (если известен)
  - `link_confidence` (HIGH/MEDIUM/LOW)
  - `link_method` (exact_alias / exact_source_id / fuzzy / manual)

---

## 2) Канонические mapping-таблицы (Target)

Ниже — рекомендуемые таблицы для слоя “идентичность + lineage”. Они не ломают MVP: MVP-таблицы могут существовать параллельно.

### 2.1 `dm_master_animals` (мастер‑карточка)
**PK:** `tenant_id, master_animal_id`

Обязательные поля:
- `tenant_id` (string)
- `master_animal_id` (string)
- `status` (enum: active/superseded/split_source/archived)
- `created_at` (datetime)
- `created_by_user_id` (string, nullable для system)

Рекомендуемые поля (можно пустыми при отсутствии данных):
- `sex` (enum: F/M/U)
- `birth_date` (date)
- `breed_code` (string)
- `dam_master_animal_id` (string)
- `sire_master_animal_id` (string)
- `current_farm_id`, `current_site_id`, `current_pen_id` (string)
- `canonical_name` (string)

Правила целостности:
- `dam_master_animal_id` и `sire_master_animal_id` должны ссылаться на существующие MAID (если заполнены).
- `status='superseded'` требует наличия lineage-события `merge`.

### 2.2 `dm_animal_id_map` (alias / mapping)
Хранит все внешние идентификаторы и связь с MAID.

**PK:** `tenant_id, source_system, id_type, id_value, valid_from`  
**FK:** `tenant_id, master_animal_id -> dm_master_animals`

Поля:
- `tenant_id` (string)
- `master_animal_id` (string)
- `source_system` (string) — `mvp_import`, `sensor_vendor_x`, `lab_y`, `manual_ui`, …
- `id_type` (enum):
  - `mvp_animal_id` (текущий `animal_id` из MVP)
  - `farm_local_animal_id`
  - `ear_tag`
  - `rfid`
  - `transponder_id`
  - `lab_animal_id`
  - `sensor_animal_key`
- `id_value` (string)
- `farm_id` (string, nullable)
- `site_id` (string, nullable)
- `valid_from` (date/datetime)
- `valid_to` (date/datetime, nullable)
- `is_primary` (bool)
- `confidence` (float 0..1)
- `link_method` (enum: exact_alias/exact_source_id/fuzzy/manual)
- `created_at`, `created_by_user_id`

Правила:
- В пределах `(tenant_id, id_type, id_value)` одновременно **может быть активна** (valid_to is null) только одна связь с MAID, кроме случаев `ear_tag_reuse`/`rfid_reuse`, которые должны сопровождаться закрытием старой записи (valid_to) и событием lineage.

### 2.3 `dm_identity_events` (merge/split/manual)
Единый журнал всех действий по идентичности.

**PK:** `tenant_id, identity_event_id`

Поля:
- `tenant_id`
- `identity_event_id` (ULID/UUID)
- `event_type` (enum: link/unlink/merge/split/conflict_resolve/manual_override)
- `actor_user_id` (string; `system` допускается)
- `event_at` (datetime)
- `reason` (string)
- `evidence_refs` (json array: ссылки на записи/файлы/скрины)
- `before_state_json` (json)
- `after_state_json` (json)

### 2.4 `dm_conflicts` (реестр конфликтов)
**PK:** `tenant_id, conflict_id`

Поля:
- `tenant_id`
- `conflict_id`
- `conflict_type` (см. каталог конфликтов ниже)
- `status` (open/resolved/ignored)
- `entity_type` (master_animal/animal/lactation/event)
- `entity_id` (например `master_animal_id`)
- `field_name` (nullable)
- `left_value`, `right_value` (string/json)
- `left_source`, `right_source` (source_system)
- `detected_at` (datetime)
- `resolved_at` (datetime, nullable)
- `resolution_identity_event_id` (nullable)

### 2.5 `dm_source_trust` (правила доверия)
**PK:** `tenant_id, field_name, source_system`

Поля:
- `tenant_id`
- `field_name` (например `sex`, `birth_date`, `milk_kg`, `scc`)
- `source_system`
- `trust_weight` (0..1)
- `policy` (enum: prefer_source / most_recent / manual_only)
- `notes` (string)

---

## 3) Lineage (происхождение и трассируемость)

### 3.1 Принцип
Каждый факт в Target должен быть трассируем:
- **откуда пришёл** (source_system + ссылка на исходный record/file)
- **какими трансформациями прошёл** (ingest mapping, нормализация, дедуп/merge/split)
- **в каких версиях участвовал** (`data_version`, `qc_run`, `model_version`, `scoring_run`, `report_version`)

### 3.2 Минимальный формат lineage-события
Рекомендуемый объект lineage (может храниться в таблице или jsonl):
- `lineage_id`
- `tenant_id`
- `entity_type`, `entity_id`
- `event_type` (ingest/normalize/link/merge/split/qc/train/score/report)
- `event_at`
- `actor_user_id` (или `system`)
- `source_system`, `source_ref` (например путь/ключ строки)
- `versions`: `{data_version,qc_run,model_version,scoring_run,report_version}`
- `payload_json` (детали)

---

## 4) Алгоритмы (протоколы) link/merge/split

### 4.1 Привязка (link) записей к MAID
**Вход:** запись из источника (например sensor/lab/event) с `source_system` и одним/несколькими идентификаторами животного.

**Шаги:**
1) **Exact match** по `dm_animal_id_map`:
   - если есть `id_type` из набора {rfid, transponder_id, ear_tag, mvp_animal_id, farm_local_animal_id} и активная запись → привязываем к найденному MAID.
2) Если exact не найден, пробуем **source_animal_id** (внутренний ID источника) как alias `id_type=sensor_animal_key` / `lab_animal_id`.
3) Если всё ещё нет, допускается **fuzzy‑candidate** (в будущем): по (farm/site + sex + birth_date ±Δ + dam/sire + недавние события). В этом протоколе fuzzy‑match **не автоприменяется**, а создаёт `dm_conflicts`/`alert` на ручное решение.
4) Любая привязка порождает событие `dm_identity_events(event_type='link')` и запись lineage.

### 4.2 Merge (слияние двух MAID в один)
**Когда:** два MAID оказались одним животным (дубликаты в источниках, повторный импорт, смена локального ID).

**Правило:** merge **не удаляет** старые идентификаторы и факты, а переносит связи.

**Шаги merge:**
1) Создать `identity_event(merge)` с:
   - `before_state_json`: список MAID + их активные alias.
2) Выбрать `survivor_master_animal_id` (выживший):
   - по наличию большего числа событий/фактов,
   - или по более высокому “trust” источника,
   - или вручную.
3) Обновить все FK (в Target‑таблицах) на survivor MAID.
4) В `dm_animal_id_map` перенести alias на survivor, а у superseded MAID закрыть статус `superseded`.
5) Записать `after_state_json` и создать/обновить `dm_conflicts` (если merge был вызван конфликтом).

### 4.3 Split (разделение одного MAID на два)
**Когда:** один MAID ошибочно объединял двух животных (ear_tag reused, sensor reassigned, ручная ошибка).

**Шаги split:**
1) Создать `identity_event(split)` с evidence.
2) Создать новые MAID (или выделить один новый MAID, если часть остаётся в старом).
3) Переназначить alias по правилам `valid_from/valid_to`.
4) Перераспределить факты/события по временным интервалам (пример: датчик был на MA1 до даты D, после D на MA2).
5) Записать `after_state_json`, обновить статусы (старый может остаться active как `split_source`).

---

## 5) Правила доверия источникам (при конфликтах полей)

### 5.1 Общая схема
Для каждого поля хранится таблица `dm_source_trust`:
- выбираем значение из источника с максимальным `trust_weight`
- если веса равны — выбираем самое свежее `updated_at` (при наличии)
- если `policy=manual_only` — всегда создаём конфликт и требуем ручного решения

### 5.2 Рекомендуемые базовые веса (по умолчанию)
> Это стартовые значения. На конкретной ферме/интеграциях веса могут быть перенастроены.

| field_name | prefer order (пример) |
|---|---|
| sex | farm_erp (0.95) > manual_ui (0.8) > lab_y (0.7) > sensor_vendor_x (0.3) |
| birth_date | farm_erp (0.95) > manual_ui (0.8) > lab_y (0.6) |
| breed_code | farm_erp (0.9) > manual_ui (0.7) |
| milk_kg / milk_305d_kg | milking_parlor (0.95) > sensor_vendor_x (0.9) > manual_ui (0.5) |
| scc | lab_y (0.95) > sensor_vendor_x (0.6) |
| treatment_* | vet_system (0.95) > manual_ui (0.7) |

---

## 6) Каталог конфликтов (минимум 10) + примеры “до/после”

Ниже — типы конфликтов, которые система Target должна уметь:
1) детектировать,
2) фиксировать как `dm_conflicts(open)`,
3) разрешать через `dm_identity_events`,
4) оставлять “след” в lineage.

> В примерах ниже используется один tenant: `TEN_001`.

### C01 — Duplicate `mvp_animal_id` (один `animal_id` указывает на разных животных)
**Детект:** одинаковый `id_type=mvp_animal_id` и `id_value=A1001` активен сразу на 2 MAID.

**До:**

`dm_animal_id_map` (фрагмент)
| tenant_id | master_animal_id | source_system | id_type | id_value | valid_to |
|---|---|---|---|---|---|
| TEN_001 | MA_A | mvp_import | mvp_animal_id | A1001 | null |
| TEN_001 | MA_B | mvp_import | mvp_animal_id | A1001 | null |

**Разрешение:** `conflict_resolve` → либо merge MA_A+MA_B, либо закрыть один alias (valid_to) если это реально reuse.

**После (пример merge):**
| tenant_id | master_animal_id | id_type | id_value | valid_to |
|---|---|---|---|---|
| TEN_001 | MA_A | mvp_animal_id | A1001 | null |
| TEN_001 | MA_B | mvp_animal_id | A1001 | 2025-12-30 |

`dm_identity_events`: event_type=merge, old=[MA_B], survivor=MA_A.

---

### C02 — Ear tag reuse (бирка переиспользована после выбытия)
**Детект:** один `ear_tag` появляется у нового животного, но старое было выбыло/archived.

**До:**
| master_animal_id | id_type | id_value | valid_from | valid_to |
|---|---|---|---|---|
| MA_OLD | ear_tag | ET-7788 | 2020-01-01 | null |
| MA_NEW | ear_tag | ET-7788 | 2025-11-01 | null |

**После (split/reassign alias):**
| master_animal_id | id_type | id_value | valid_from | valid_to |
|---|---|---|---|---|
| MA_OLD | ear_tag | ET-7788 | 2020-01-01 | 2025-10-31 |
| MA_NEW | ear_tag | ET-7788 | 2025-11-01 | null |

Создаётся `identity_event(link)` для MA_NEW и `conflict_resolve` с reason=`ear_tag_reuse`.

---

### C03 — RFID/transponder reassigned
**Детект:** `rfid` активен у MA1 и появляется у MA2.

**До:**
| master_animal_id | id_type | id_value | valid_to |
|---|---|---|---|
| MA1 | rfid | 990000123456789 | null |
| MA2 | rfid | 990000123456789 | null |

**После:** закрыть у MA1 и открыть у MA2 с датой перевыпуска, событие `split` или `conflict_resolve`.

---

### C04 — Sensor key mapped to wrong animal (датчик “прыгает”)
**Детект:** в SensorsDaily по одному `sensor_animal_key` идут события на двух MAID в пересекающиеся даты.

**До (SensorsDaily):**
| date | sensor_animal_key | master_animal_id |
|---|---|---|
| 2025-12-01 | SKEY-55 | MA1 |
| 2025-12-02 | SKEY-55 | MA2 |

**После (split по времени):**
- до даты D включительно привязка к MA1, после D — к MA2,
- событие `split` (если ранее был один MA).

---

### C05 — Lab sample mislabel (проба привязана не тому)
**Детект:** `lab_sample_id` указывает на MA, но поля (sex/birth_date/farm) не совпадают, либо в тот день животное было в другой ферме.

**До (TestDay/Lab):**
| test_date | lab_sample_id | lab_animal_id | master_animal_id |
|---|---|---|---|
| 2025-12-10 | L-00077 | LID-12 | MA_WRONG |

**После:** `unlink` от MA_WRONG + `link` к MA_RIGHT (manual), фиксируется `identity_event`.

---

### C06 — Sex conflict
**Детект:** два источника с высоким trust сообщают разный sex.

**До (dm_master_animals canonical fields):**
| master_animal_id | sex | sex_source |
|---|---|---|
| MA1 | F | farm_erp |
| MA1 | M | lab_y |

**После:** выбираем `farm_erp` (higher trust), создаём `dm_conflicts(resolved)` и `identity_event(manual_override/ conflict_resolve)`.

---

### C07 — Birth date conflict
**Детект:** `birth_date` отличается > 30 дней между источниками с trust>=0.8.

**До:**
| master_animal_id | birth_date | source |
|---|---|---|
| MA1 | 2021-03-10 | farm_erp |
| MA1 | 2021-05-01 | manual_ui |

**После:** выбрать farm_erp, manual_ui отправить в конфликт с notes.

---

### C08 — Breed conflict
**Детект:** разные `breed_code` в источниках; либо порода меняется (кросс‑breed) без события.

**До:**
| master_animal_id | breed_code | source |
|---|---|---|
| MA1 | HOL | farm_erp |
| MA1 | JER | manual_ui |

**После:** выбрать HOL, создать конфликт, опционально потребовать ручное подтверждение.

---

### C09 — Parentage mismatch (dam/sire)
**Детект:** dam/sire указывают на разные MAID в разных источниках, либо родитель младше потомка.

**До:**
| master_animal_id | dam_master_animal_id | source |
|---|---|---|
| MA_CALF | MA_DAM1 | farm_erp |
| MA_CALF | MA_DAM2 | manual_ui |

**После:** выбрать по trust; проверить хронологию (dam.birth_date < calf.birth_date).

---

### C10 — Lactation overlap / duplicate lactation
**Детект:** для одного `master_animal_id` две лактации с пересекающимися периодами или одинаковым `lactation_no`.

**До (Lactation):**
| master_animal_id | lactation_no | calving_date |
|---|---:|---|
| MA1 | 2 | 2025-08-01 |
| MA1 | 2 | 2025-08-15 |

**После:** либо merge лактаций (если дубль), либо renumber (если ошибочный lactation_no), всё через событие `manual_override` и lineage.

---

### C11 — Farm transfer / new local ID
**Детект:** животное переезжает (PenMoves/Site change) и получает новый `farm_local_animal_id`.

**До:**
| master_animal_id | id_type | id_value | farm_id | valid_to |
|---|---|---|---|---|
| MA1 | farm_local_animal_id | 001234 | FARM_001 | null |

**После:** добавить новый alias на другой ферме/сайте, старый закрыть или оставить (если ID сохраняется как исторический).

---

### C12 — Mixed facts (смешались события двух животных в одном MA)
**Детект:** у MA наблюдаются два взаимоисключающих набора событий (например два разных pen_id в один день, параллельные лактации, milkings в двух фермах).

**Разрешение:** чаще всего требуется `split` с перераспределением фактов по интервалам/признакам.

---

## 7) Пример сквозного “до/после” (merge + audit)

### До
В систему загружены данные из MVP и сенсоров, но сенсор создал новый `source_animal_id`, хотя это то же животное.

`dm_animal_id_map`:
| master_animal_id | source_system | id_type | id_value |
|---|---|---|---|
| MA_01 | mvp_import | mvp_animal_id | A1001 |
| MA_02 | sensor_vendor_x | sensor_animal_key | SKEY-777 |

Данные показывают совпадение по `ear_tag=ET-0001` → требуется merge.

### После
- Создан `identity_event(merge)` actor=operator_1.
- Все sensor-факты перепривязаны на `MA_01`.

`dm_animal_id_map`:
| master_animal_id | source_system | id_type | id_value |
|---|---|---|---|
| MA_01 | mvp_import | mvp_animal_id | A1001 |
| MA_01 | sensor_vendor_x | sensor_animal_key | SKEY-777 |

`dm_master_animals`:
| master_animal_id | status |
|---|---|
| MA_01 | active |
| MA_02 | superseded |

---

## 8) Naming-конвенции и единицы измерения (для identity слоя)

### Naming
- snake_case
- все ключи заканчиваются на `_id` (кроме enum/даты)
- даты: `*_date` (YYYY-MM-DD), datetime: `*_at` (ISO 8601)

### Единицы
- веса молока: `milk_kg` / `milk_305d_kg` — **килограммы**
- время: **ISO 8601**, UTC либо локаль с явной TZ (на on‑prem допустимо local TZ, но фиксировать)

---

## 9) Минимальные требования к аудиту (DoD для будущей реализации)

Для всех операций link/merge/split/conflict_resolve система должна:
- писать запись в **audit_log**: `tenant_id, actor_user_id, action, entity_type, entity_id, event_id, timestamp, before_hash, after_hash`;
- сохранять `identity_event` и `dm_conflicts`;
- поддерживать откат (как минимум “логический” — через обратное событие).



## Implementation (code artifacts)

- Trust rules: `configs/target/trust_rules.yaml`
- Store format (storage-agnostic CSV/JSONL): `artifacts/<data_version>/runs/<run_id>/identity/`
  - `master_animals.csv`
  - `animal_id_map.csv`
  - `identity_events.jsonl` (append-only audit trail)
- Python modules:
  - `src/genomeai/target/master_id_store.py`
  - `src/genomeai/target/master_id.py`
- DDL tables (SQLite/Postgres): `db/ddl/target_v2/sqlite.sql` и `db/ddl/target_v2/postgres.sql` (раздел *Identity / Master ID*).

### CLI

Resolve (создать/получить `master_animal_id` для входного source-id):

```bash
genomeai master-id resolve --data-version <dv> --source-system registry --source-id A1001 \
  --tenant default --actor operator --sex F --birth-date 2022-03-01 --ear-tag-id ET123
```

Merge (слить два master_id, перенос алиасов в `into`):

```bash
genomeai master-id merge --data-version <dv> --from-master <MA1> --into-master <MA2> \
  --tenant default --actor admin --reason "duplicate"
```

Split (вынести алиасы в новый master):

```bash
genomeai master-id split --data-version <dv> --master <MA2> \
  --move-alias registry:A1001 --move-alias sensor:S_8899 \
  --tenant default --actor admin --reason "two different animals"
```
