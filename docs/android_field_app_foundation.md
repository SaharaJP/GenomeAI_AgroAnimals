# T32-08 — Android field app foundation

## Цель

Сформировать отдельное нативное Android-приложение `mobile_android/` для cowside / field execution сценариев.

Критическое правило: Android — **отдельное приложение**, а не Streamlit, не PWA и не web wrapper.

## Scope этого шага

- Kotlin / Jetpack Compose foundation
- auth-aware app shell
- role-aware navigation
- sync-safe local state baseline
- first cowside surfaces:
  - today worklists
  - alerts now
  - quick animal card
  - quick event entry
  - task completion
  - shift handover

## Архитектурные правила

- Мобильный клиент не содержит бизнес-логики ранжирования, explainability или decision rules.
- Мобильный клиент использует backend API / canonical contracts.
- Offline/poor-connectivity допустим только для ограниченного набора безопасных действий через sync queue.
- Любые финальные доменные решения и audit/governance подтверждаются сервером.

## Структура

- `mobile_android/` — реальный Android foundation project
- `apps/android/` — repo-level target ownership marker

## Что реализовано

### Auth / session baseline
- логин как отдельный мобильный flow
- mobile session model с `deviceId`
- mobile client ориентирован на T32-03 unified auth/session model

### Navigation / shell
- role-aware набор мобильных destinations
- отдельный field shell
- явное разделение mobile-only cowside screens и office/web surfaces

### Sync-safe local baseline
- модели для offline-safe queue
- policy: в очередь разрешены только:
  - quick event entry
  - task completion
  - shift handover

### First cowside screens
- Today Worklists
- Alerts Now
- Quick Animal Card
- Quick Event Entry
- Task Completion
- Shift Handover

## Что не делается на этом шаге

- полный перенос web-функционала на Android
- локальный расчет business rules
- замена backend audit/governance локальным mobile logic
- Streamlit/PWA substitute

## Проверяемые признаки parity/foundation

- есть отдельный `mobile_android/`
- есть Kotlin/Compose shell
- есть auth/session models
- есть role-aware navigation
- есть sync queue baseline
- есть 6 базовых cowside screens
- docs прямо фиксируют, что Android не является web wrapper
- offline/sync conflict contract hardened in `docs/android_offline_sync_contract.md`
