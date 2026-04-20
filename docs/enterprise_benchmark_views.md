# T28-03 — Enterprise dashboards и benchmark views

Что добавлено:
- Новый explainable enterprise benchmark layer поверх уже видимых operational items.
- Новый экран `68_Enterprise_Benchmark_Views.py` с holding summary, site comparison и group benchmark.
- Связь summary → action surfaces: быстрые переходы в Operational Planner, Daily Worklists, KPI Drilldown и Group Profile.

Как считается benchmark:
- Benchmark = sibling median внутри текущего фильтра.
- Для `farm` сравнение идёт по видимым farms.
- Для `site` сравнение идёт внутри `farm -> site`.
- Для `group` сравнение идёт внутри `site -> group`.
- Используются только visible operational items; отдельный скрытый corporate KPI engine не вводится.

Что показывается:
- holding summary: farms / sites / groups / overdue / high-priority;
- top deviations across sites;
- top issues across sites;
- compare tables для farm / site / group;
- benchmark basis и top issue hint для каждого scope.

Почему это не corporate BI:
- нет тяжёлых исторических витрин и кастомного OLAP;
- нет непрозрачных composite KPI;
- все отклонения объяснимы через counts/rates уже видимых operational items.

Single-farm usability:
- если виден один farm/site, экран остаётся полезным: benchmark basis явно показывает текущий scope;
- руководитель всё ещё может открыть planner/worklists/group profile без enterprise-only перегруза.
