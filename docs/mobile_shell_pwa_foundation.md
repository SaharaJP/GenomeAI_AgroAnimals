# Mobile Shell & PWA Foundation

Describes the mobile application shell and Progressive Web App foundation in GenomeAI AgroAnimals.

## Overview

The mobile surface is implemented as a native Android app (`mobile_android/`) complemented by a Progressive Web App (PWA) fallback. The mobile shell provides offline-first field access to worklists, animal profiles, and health event recording.

## Android App

- Target: Android 9+ (API 28+)
- Architecture: MVVM with Kotlin Coroutines / Flow
- Offline sync: SQLite local store + background sync queue
- Auth: JWT session token stored in Android Keystore

### Key Screens

- `TodayWorklistsScreen`: daily animal worklist with priority sorting
- `AlertsNowScreen`: active alerts requiring immediate action
- Animal detail: genomic scores + decision recording (offline-capable)
- Sync status indicator with conflict resolution

## PWA Fallback

- Built with Next.js 15 App Router (`web_app/`)
- Service worker for offline asset caching
- Manifest for home-screen installation
- Mobile-first responsive layout with touch-optimised controls

## Offline Sync Architecture

- Event queue: local SQLite table `sync_queue_v1`
- Sync policy: defined in `SyncQueuePolicy.kt`
- Conflict resolution: server-wins with local conflict log
- Background sync via `WorkManager` (Android)

## Integration Points

- Backend API: `apps/api/` (target) / `web_cabinet/` (current fallback)
- Offline data pack sourced from `pack_zip` artifact
- Auth tokens shared between PWA and Android via secure storage

## Status

Android foundation screens (T32-08) and offline sync contract (T32-08A) implemented. PWA service worker in progress.
