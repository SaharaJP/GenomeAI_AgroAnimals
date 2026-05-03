# Сводный UAT checklist — Web + Android

Дата: 2026-04-14  
Статус: сводный pass/fail checklist для QA / implementation / customer UAT.

Используйте этот файл как сводный протокол. Подробные шаги смотреть в:

- `docs/ui_functional_verification_web.md`
- `docs/ui_functional_verification_android.md`

---

## 1. Базовая информация о прогоне

- Environment profile: `_____`
- URL web: `_____`
- Android build ID / APK version: `_____`
- Release / commit / tag: `_____`
- Data version: `_____`
- Date / time: `_____`
- QA owner: `_____`
- Customer/UAT owner: `_____`

---

## 2. Предварительные smoke / health checks

### 2.1 Server / deployment

- [ ] `bash scripts/smoke_t32_10_server_deployment.sh`
- [ ] `bash scripts/smoke_t32_10a_production_security.sh`
- [ ] `bash scripts/smoke_t32_13_deployment_full_guide.sh`

### 2.2 Web parity

- [ ] `bash scripts/smoke_t32_05_react_daily_operations.sh`
- [ ] `bash scripts/smoke_t32_06_react_profiles_reports_assistant.sh`
- [ ] `bash scripts/smoke_t32_07_react_extended_surface.sh`

### 2.3 Android parity / offline

- [ ] `bash scripts/smoke_t32_08_android_field_app.sh`
- [ ] `bash scripts/smoke_t32_08a_android_offline_sync_contract.sh`
- [ ] `bash scripts/smoke_t32_09_android_offline_sync_model.sh`

---

## 3. Web UAT checklist

| ID | Роль | Контур | Статус (PASS/FAIL/N/A) | Комментарий |
|---|---|---|---|---|
| WEB-AUTH-001 | All | Login / session |  |  |
| WEB-RBAC-001 | All | Role-aware navigation |  |  |
| WEB-OPS-001 | Director / Operator / Vet / Admin | Daily summary |  |  |
| WEB-OPS-002 | Operator / Vet / Director / Admin | Alerts |  |  |
| WEB-OPS-003 | Operator / Vet / Admin | Worklists |  |  |
| WEB-OPS-004 | Operator / Director / Admin | Planner |  |  |
| WEB-PROFILE-001 | Operator / Vet / Director / Viewer / Admin | Animal Profile |  |  |
| WEB-PROFILE-002 | Director / Operator / Viewer / Admin | Group Profile |  |  |
| WEB-REPORT-001 | Director / Viewer / Operator / Admin | Reports catalog |  |  |
| WEB-REPORT-002 | Admin / report-approval role / Viewer(read) | Report detail + governance |  |  |
| WEB-AI-001 | Director / Operator / Vet / Admin | Assistant |  |  |
| WEB-DEC-001 | Director / Operator / Admin | Decisions |  |  |
| WEB-REPRO-001 | Operator / Director / Admin | Reproduction |  |  |
| WEB-VET-001 | Vet / Admin | Vet queues |  |  |
| WEB-TREAT-001 | Vet / Admin / Director(read) | Treatments / withdrawal |  |  |
| WEB-ECON-001 | Director / Admin | Economics / what-if |  |  |
| WEB-SUPPORT-001 | Admin / support | Support / governance |  |  |
| WEB-READINESS-001 | Admin | Pilot / Readiness / Observability / Admin |  |  |

---

## 4. Android UAT checklist

| ID | Роль | Контур | Статус (PASS/FAIL/N/A) | Комментарий |
|---|---|---|---|---|
| AND-AUTH-001 | All | Login + role-aware navigation |  |  |
| AND-WL-001 | HerdManager / Vet / Repro / Viewer / Admin | Today worklists |  |  |
| AND-ALERT-001 | HerdManager / Vet / Repro / Viewer / Admin | Alerts now |  |  |
| AND-ANIMAL-001 | HerdManager / Vet / Viewer / Admin | Quick animal card |  |  |
| AND-EVENT-001 | HerdManager / Vet / Repro / Admin | Quick event entry |  |  |
| AND-TASK-001 | HerdManager / Vet / Repro / Admin | Task completion |  |  |
| AND-HANDOVER-001 | HerdManager / Vet / Repro / Viewer / Admin | Shift handover |  |  |
| AND-OFFLINE-001 | HerdManager / Vet / Repro / Admin | Offline queue / sync / conflict |  |  |

---

## 5. GO / No-Go summary

### 5.1 Web

- [ ] Нет блокирующих FAIL по auth/navigation
- [ ] Нет блокирующих FAIL по daily operations
- [ ] Нет блокирующих FAIL по profiles/reports
- [ ] Нет блокирующих FAIL по reproduction/vet/treatments/economics
- [ ] Все N/A честно объяснены и не маскируют регрессию

### 5.2 Android

- [ ] Нет блокирующих FAIL по login/navigation
- [ ] Нет блокирующих FAIL по базовым cowside screens
- [ ] Offline/sync smoke приложен к UAT результату
- [ ] Scope-ограничения Android честно отмечены как N/A, а не FAIL

### 5.3 Итог

- [ ] GO для customer UAT
- [ ] GO с ограничениями
- [ ] NO-GO

Итоговое решение: `______________________________`

Основание: `_______________________________`
