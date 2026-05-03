# apps/android

Будущее нативное Android-приложение для cowside / daily execution.

## Scope

- worklists
- task execution
- event capture
- cowside confirmations
- offline queue + sync
- minimal animal/group context

## Правило

Android — отдельное приложение, а не web wrapper и не упаковка веб-интерфейса.


## T32-08 foundation

Первый runnable foundation собран в `mobile_android/`.
`apps/android/` остаётся target-ownership каталогом верхнего уровня, а `mobile_android/` — фактической реализацией отдельного Android-приложения.
