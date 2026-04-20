# Python multipart compatibility shim

## Что стабилизировано

В проект добавлен локальный shim-пакет `src/multipart/`, который проксирует
старые импорты `multipart` и `multipart.multipart` к актуальному пакету
`python_multipart`.

Это нужно для совместимости с версиями Starlette/FastAPI, которые ещё импортируют
`multipart`, тогда как новые версии `python-multipart` сохраняют такой alias, но
выдают `PendingDeprecationWarning: Please use import python_multipart instead.`

## Почему решение локализовано в shim

- не меняет web routes, upload handlers и HTML-формы;
- не требует rewrite страниц или FastAPI-обвязки;
- сохраняет обратную совместимость со старым import surface;
- устраняет warning уже в текущем runtime, даже если среда ещё не обновлена до
  FastAPI/Starlette, которые сами перешли на `python_multipart`.

## Что должно остаться неизменным

- upload/form handlers продолжают работать как раньше;
- контракт `from multipart.multipart import parse_options_header` сохраняется;
- web smoke и targeted upload tests остаются зелёными;
- `verify_refactor` не показывает расхождений golden-артефактов.

## Дальнейший целевой путь

Когда базовая версия FastAPI/Starlette в проекте будет гарантированно выше
порога, где они сами используют `python_multipart`, локальный shim можно будет
удалить отдельной совместимой задачей после повторного smoke/regression pass.
