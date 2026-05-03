# T11-01 (step3): Экономика 2.0 в Director Summary + дефолтная валюта ₽

## Что сделано
1) В **Director Summary** добавлена best-effort панель **«Экономика (₽)»**:
   - UI **ничего не рассчитывает**: читает последнюю витрину `economics_v2` из `artifacts/<data_version>/economics_v2/<economics_run>/economics_daily.csv`.
   - Показывает ключевые показатели (выручка, корм, прочие, маржа) и табличный срез на дату `<= as-of date`.
   - Дает кнопку быстрого перехода на страницу **Economics 2.0**.

2) Улучшена навигация на странице **Economics 2.0**:
   - параметры (`data_version/date_from/date_to/economics_run`) сохраняются в `st.session_state`, поэтому переходы между страницами не сбрасывают контекст.

3) Конфиг `economics_v2.yaml`: дефолтная валюта входных параметров `dm_economics_daily_currency` теперь **RUB** (требование «по умолчанию ₽»).
   - Если входная таблица в другой валюте — указывайте её явно в колонках `milk_price_ccy/feed_cost_ccy` (и аналогично для other_cost).

## Как проверить
1) Посчитать витрину:
   ```bash
   python -m genomeai economics-v2 --data-version dv_demo --date-from 2025-01-01 --date-to 2025-01-31
   ```

2) Запустить кабинет:
   ```bash
   streamlit run streamlit_app/app.py
   ```

3) Открыть **Director Summary** → увидеть блок **Экономика (₽)** → нажать **Открыть Economics 2.0**.

## Артефакты
- `artifacts/<data_version>/economics_v2/<economics_run>/economics_daily.csv`
- `artifacts/<data_version>/economics_v2/<economics_run>/formulas_catalog.json` (прозрачные формулы)
