# Reproduction Cockpit

Describes the reproduction management surface in GenomeAI AgroAnimals.

## Overview

The reproduction cockpit provides a unified view of herd reproduction status, heat detection alerts, insemination history, pregnancy confirmations, and calving events. It supports the daily reproduction protocol workflow.

## Key Workflows

- View animals eligible for insemination (open cows, heat-detected)
- Log insemination events (bull/semen code, technician, date)
- Record pregnancy check results (positive / negative / recheck)
- Track calving events and assign new lactation records
- Review voluntary waiting period (VWP) compliance

## Metrics

- Conception rate (21-day pregnancy rate)
- Services per conception
- Calving interval (days)
- Stillbirth rate

## Integration Points

- Heat detection alerts feed from `alerts` pipeline
- Insemination records feed into next QC/scoring run as feature inputs
- Reproduction state machine defined in `docs/reproduction_state_machine.md`

## Access Roles

- `operator`: record events, view dashboard
- `viewer`: read-only
- `admin`: full access + data export

## Status

Core reproduction event tracking implemented. Cockpit UI in `web_app/app/(protected)/` reproduction module.
