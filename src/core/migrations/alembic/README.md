# Alembic baseline for T34 staged Postgres cutover

Этот layout — baseline дисциплины миграций для adult runtime contour.

Правила:
- runtime Postgres schema меняется только через Alembic revision;
- dev/test sqlite compat path не использует этот каталог как runtime backend;
- adult/stage/prod startup должен валидировать наличие `alembic.ini` и каталога `versions/`;
- до полного cutover наличие layout не означает, что runtime migration уже proven.
