# Trend Reports: Compare Periods

Describes the period-comparison reporting surface in GenomeAI AgroAnimals.

## Overview

Trend reports enable managers to compare herd performance metrics across selectable time periods (month, quarter, year) or between defined cohorts. Reports are generated as part of the `report` pipeline step and available in the report catalog.

## Comparison Modes

- **Rolling period**: current 30/90/365 days vs. prior equivalent period
- **Fixed cohort**: calving group A vs. calving group B
- **Benchmark**: farm performance vs. regional or breed benchmark

## Metrics Supported

- Milk production (kg, ECM) trend
- Reproductive efficiency (conception rate, 21-day PR)
- Genomic index distribution shift
- Culling rate and reasons
- SCC compliance rate

## Output Formats

- Interactive table in `web_app` report catalog surface
- Downloadable CSV / PDF export
- JSON fact-pack for external BI integration

## Integration Points

- Powered by `report_version` artifact from scoring pipeline
- Accessible in `web_app/app/(protected)/reports/` surface
- Data sourced from `scoring_run` + `qc_run` artifact pair

## Access Roles

- `viewer`: read-only access to published reports
- `operator`: access to current + prior period reports
- `admin`: full access + custom period selection

## Status

Report catalog and basic period comparison implemented. Advanced cohort comparison planned for subsequent iteration.
