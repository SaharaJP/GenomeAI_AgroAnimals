# T10-02 Step8 — Trend exceptions: snapshot как источник истины

- Добавлен helper `find_latest_dashboard_run()` для поиска последнего snapshot run_id в `artifacts/<dv>/runs/*/dashboards/<kind>`.
- В Director Summary UI тренды и trend exceptions теперь читаются из snapshot CSV (если они есть), а не пересчитываются в вебе.
- Trend exceptions включают relpath до артефактов `milk_trend_windows.csv` и `milk_trend_exceptions.csv` для lineage.
