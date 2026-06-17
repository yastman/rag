# Init

## Purpose
Navigation index for the folder. Use this page to quickly find files and route into this part of the project.

## Scope
docker/postgres/init

## Contents
- 00-init-databases.sql
- 02-cocoindex.sql
- 03-unified-ingestion-alter.sql
- 05-realestate-schema.sql
- 08-user-favorites.sql
- 09-drop-orphaned-scheduler-voice-tables.sql

## Notes
- 04-voice-schema.sql: deleted after ARCH-02 (#2598) voice archival
- 06-lead-scoring-sync.sql: deleted after ARCH-12 (#2625) CRM archival
- 07-nurturing-funnel-analytics.sql: deleted after ARCH-12 (#2625) CRM archival
- 09-drop-orphaned-scheduler-voice-tables.sql: ARCH-11 (#2608) — drops tables whose writers were archived; run only after backup and human approval

## Parent
- [..](..)
