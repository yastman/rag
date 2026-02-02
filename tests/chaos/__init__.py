"""Chaos tests for graceful degradation.

Tests verify the system handles service failures gracefully:
- Qdrant timeouts and connection failures
- Redis disconnection and unavailability
- LLM API failures and fallback chain
"""
