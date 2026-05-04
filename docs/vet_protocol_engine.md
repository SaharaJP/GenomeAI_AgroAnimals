# Vet Protocol Engine

Describes the veterinary protocol engine in GenomeAI AgroAnimals.

## Overview

The vet protocol engine manages structured veterinary workflows: disease monitoring, treatment protocols, milk withholding tracking, and health event recording. It supports the `vet` role with specialised views and decision support.

## Key Workflows

- Define and activate treatment protocols per diagnosis category
- Record health events (mastitis, lameness, metabolic disorders)
- Track milk withholding periods and withdrawal compliance
- Generate vet visit schedules based on risk scores
- Export health event history for herd health reporting

## Protocol Types

- `mastitis_protocol`: detection → treatment → resolution → monitoring
- `lameness_protocol`: scoring (0-5) → treatment → follow-up
- `metabolic_protocol`: ketosis / hypocalcaemia / displaced abomasum
- `reproductive_protocol`: links to reproduction cockpit

## Integration Points

- Health events feed into QC as animal feature flags
- Genomic risk scores (mastitis resistance, SCC stability) visible in protocol context
- Antibiotic use audit trail feeds compliance reporting

## Access Roles

- `vet`: full protocol management, event recording, withholding tracking
- `operator`: view health events, record basic observations
- `admin`: full access + protocol configuration

## Status

Health event recording implemented. Protocol engine UI accessible in `web_app/app/(protected)/` vet module.
