# Investor Demo Farm v1 — SYNTHETIC dataset

Farm: **Демо-ферма** (Агрохолдинг Заря), с. Васильково
Director: Андрей Жиров
Generated: 2026-04-21 | seed=42 | mode=connecterra

## Files

| File | Records | Description |
|------|---------|-------------|
| `animals.json` | 350 | 350 active dairy cows |
| `events.json` | 3364 | Health/calving/pen-move events |
| `treatments.json` | 61 | Drug treatments with withdrawal dates |
| `breedings.json` | 159 | AI breeding records |
| `milk_yields.json` | 37310 | Daily milk yield (350 cows × 180 days) |
| `operator_tasks.json` | 8 | Act 5: 8 operator worklist tasks |
| `culling_candidates.json` | 15 | Act 3: 15 culling candidates (5 sell/5 watch/5 keep) |
| `insights_seeded.json` | 12 | 12 seeded AI insights for demo acts |
| `timeline_events_seeded.json` | 12 | 10–12 timeline events with impact |
| `morning_briefs_seeded.json` | 3 | 3 morning briefings (today/yesterday/day before) |
| `weekly_briefs_seeded.json` | 2 | 2 weekly briefings |
| `impact_analyses_seeded.json` | 4 | Economic impact per timeline event |
| `seeded_insights.json` | 12 | 12 AI-schema insights (Insight model) — --with-ai-seeds |
| `seeded_morning_briefs.json` | 3 | 3 MorningBrief-schema briefings — --with-ai-seeds |
| `seeded_weekly_briefs.json` | 2 | 2 WeeklyBrief-schema briefings — --with-ai-seeds |
| `seeded_impact_analyses.json` | 8 | 8 ImpactAnalysis-schema records — --with-ai-seeds |

## Seeded Demo Cases

### Акт 2 — Звёздочка (ID 4821)
- 3-я лактация, 156 DIM
- Мастит -42 дня, лечение Цефквином, перевод в группу 3
- Удой упал с 36 до 28 кг/день (-22%)

### Акт 3 — Малина (ID 3891)
- 3-я лактация, 285 DIM, 2 эпизода мастита за 60 дней
- Open 145 дней, NPV -$180, рекомендация SELL

### Акт 4 — Ночка (ID 3142)
- 2-я лактация, 45 DIM
- Активность снизилась 3 дня, СКК 450k, нет открытого лечения

### Акт 5 — Worklist оператора
- 8 задач: 3 проверки стельности, 2 осеменения, 2 наблюдения, 1 DMI

## KPI Dashboard (Акт 1)
- avg_milk_yield: 28.5 кг/гол/день
- health_index: 94%
- pregnancy_rate_21d: 24%
- cows_need_attention_today: 3

---
SYNTHETIC DATA — not for production use.