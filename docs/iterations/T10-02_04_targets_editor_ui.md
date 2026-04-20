# T10-02 (шаг 4) — Редактор целей/порогов KPI в кабинете

## Цель
Сделать «задаваемые в кабинете» цели/пороги KPI для Director dashboard без переноса бизнес‑логики в UI.

## Реализация
- **Источник истины:** `configs/kpi/kpi_targets_v1.yaml`.
- **Override-механизм:** UI сохраняет полный YAML‑override в:
  `WEB_STORAGE_DIR/config_overrides/<targets_rel_path>`
  (по умолчанию: `web_cabinet/storage/config_overrides/configs/kpi/kpi_targets_v1.yaml`).

### Offline-core
Используются функции из `genomeai.kpi_targets`:
- `list_target_specs(...)` — построение таблицы текущих целей/порогов по scope;
- `upsert_target_rule(...)` — апдейт/инсерт правила для scope (`tenant_id/farm_id[/site_id]`);
- `save_override_yaml(...)` — сохранение override YAML;
- `reset_override(...)` — удаление override.

### Web-cabinet (Streamlit)
На странице `Director Summary (v2)` добавлен expander:
- выбор scope (tenant/farm/site optional);
- редактирование `target/direction/warn_pct/alert_pct/unit` через `st.data_editor`;
- кнопки **Сохранить** и **Сбросить override**.

Все операции пишутся в audit log:
- `kpi.targets.update`
- `kpi.targets.reset`

## Проверка
1) Войти под пользователем с правом `configs.manage` (Director после T10-02 имеет его по умолчанию).
2) Открыть `Director Summary (v2)` → expander «Настроить цели/пороги KPI».
3) Изменить target и пороги для пары KPI → Сохранить.
4) Убедиться, что:
   - появился файл override YAML в `web_cabinet/storage/config_overrides/...`;
   - `Targets source` на дашборде указывает на override-файл;
   - `plan_fact` и `Top deviations vs targets` отражают новые значения;
   - запись попала в `web_cabinet/storage/web.db` → `audit_log`.
