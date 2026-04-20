# Web template contracts migration (T16-03)

## Что изменено

Web-cabinet переведён на актуальный request-first контракт `Jinja2Templates.TemplateResponse`.

Старый вызов:

```python
templates.TemplateResponse(name, {"request": request, ...})
```

Заменён на канонический вызов:

```python
templates.TemplateResponse(request, name, context)
```

## Где локализовано изменение

Изменение вынесено в helper-layer:

- `web_cabinet/rendering.py` — canonical render helper
- `web_cabinet/app.py::_render()` — thin wrapper над helper

Маршруты и шаблоны не переписывались: страницы по-прежнему вызывают `_render(...)`, а helper гарантирует тот же базовый контекст:

- `request`
- `settings`
- `active`
- дополнительные поля страницы

## Что сохраняется

- те же route paths;
- те же template names;
- тот же Jinja context surface для существующих HTML-страниц;
- то же поведение навигационного `active` section.

## Проверка

- `pytest -q tests/test_t16_03_web_template_contracts.py`
- `python -m web_cabinet.smoke --workdir _tmp/t16_03_web_smoke --clean`
- `python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_verify_refactor_t16_03`

После миграции warning от deprecated `TemplateResponse(name, context)` больше не должен появляться.
