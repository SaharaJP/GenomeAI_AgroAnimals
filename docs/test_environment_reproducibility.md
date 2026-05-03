# Test environment reproducibility notes

Этот шаг не меняет зависимости и не вводит lockfile-force.

Цель — сделать test/CI environment прозрачным и воспроизводимым на уровне артефактов:
- какие ключевые пакеты мы отслеживаем;
- какие версии реально стояли в прогоне;
- какие upgrades допустимы только отдельным controlled change.

## Что добавлено

- `configs/compat/test_environment_policy_v1.json` — policy со списком отслеживаемых пакетов и их ролями.
- `src/core/infra/environment_snapshot.py` — helper для построения snapshot текущей среды.
- `scripts/export_test_env_snapshot.py` — экспорт snapshot в JSON артефакт.
- `scripts/run_ci_gate.sh` теперь пишет `python_environment.json` рядом с `pytest.warning_report.json`.

## Почему это не lockfile

Проект сейчас использует `pyproject.toml` с диапазонами версий (`>=`).
В рамках рефакторинга мы не делаем массовый dependency churn.

Поэтому policy такая:
- бизнес-рефакторинг не меняет зависимости;
- если нужен upgrade — это отдельный controlled change;
- перед upgrade прогоняются targeted pytest, smoke и `verify_refactor`.

## Что лежит в `python_environment.json`

- версия Python и платформа;
- `requires-python` из `pyproject.toml`;
- список ключевых пакетов;
- установленная версия каждого пакета в текущем прогоне;
- declared requirement/group из `pyproject.toml`, если пакет объявлен проектом.

## Как использовать

Локально:

```bash
PYTHONPATH=src python scripts/export_test_env_snapshot.py artifacts/_ci/python_environment.json
```

В CI артефактах сравнивайте:
- `pytest.warning_report.json`
- `python_environment.json`

Если warning появился только после смены версии зависимости, это признак dependency-origin изменения, а не бизнес-регрессии.
