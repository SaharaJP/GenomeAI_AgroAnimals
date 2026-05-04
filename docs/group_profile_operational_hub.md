# Group Profile Operational Hub

Describes the group profile surface used as an operational hub for farm management in GenomeAI AgroAnimals.

## Overview

The group profile aggregates herd or pen-level statistics, enabling managers to track group performance, identify underperforming subsets, and plan interventions.

## Key Workflows

- View herd summary: average genomic index, culling rate, reproduction efficiency
- Drill down from group to individual animal profiles
- Track decisions applied across a group (ACCEPT / DEFER / REJECT ratios)
- Compare current period vs. prior period performance

## Displayed Metrics

- Average EBV (Estimated Breeding Value) by trait
- Lactation yield distribution (P10/P50/P90)
- Health event frequency per 100 animals
- Open days and pregnancy rate

## Access Roles

- `operator`: read access + bulk decision initiation
- `admin`: full access including export

## Status

Implemented in `web_app/app/(protected)/profiles/` group view.
