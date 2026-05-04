# Animal Profile Daily Use

Describes the daily operational use of the animal profile surface in GenomeAI AgroAnimals.

## Overview

The animal profile provides a unified view of an animal's current status, genomic scores, lactation history, health events, and pending decisions. It is the primary entry point for field operators performing daily management tasks.

## Key Workflows

- View current genomic ranking and recommendation type (PRIORITY / STANDARD / MONITOR)
- Review lactation performance vs. herd benchmark
- Record management decisions (ACCEPT / DEFER / REJECT)
- Access reproduction status and event timeline
- Navigate to related animals (dam, offspring)

## Access Roles

- `operator`: full read/write including decision recording
- `viewer`: read-only; cannot record decisions
- `admin`: full access including audit trail

## Integration Points

- Feeds into `decisions` workflow for batch processing
- Linked from daily worklist surface for prioritised animals
- Score data sourced from latest `scoring_run` artifact

## Status

Surface implemented in `web_app/app/(protected)/profiles/` and `mobile_android` animal detail screens.
