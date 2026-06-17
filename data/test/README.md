# Test Data

## Purpose

Fixtures for evaluation and component tests that need plain-text test payloads.

## Files

- `sample_articles.json` — text/article fixture used by offline ingestion/evaluation helpers.
- `voice_note_sample.ogg` — synthetic OGG/Opus fixture for the Telegram voice-note E2E contract
  tests (`tests/contract/test_e2e_voice_note_fixture_contract.py`). Used by Telethon trace gate
  scenarios when the `voice` compose profile is active. Non-secret; 407 bytes.

## Parent

- [Data directory](../README.md)
