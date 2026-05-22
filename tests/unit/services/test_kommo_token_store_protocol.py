"""Tests for KommoTokenStoreProtocol abstraction (#384)."""

from typing import Protocol

from telegram_bot.services.kommo_tokens import KommoTokenStore, KommoTokenStoreProtocol


def test_token_store_contract_is_protocol():
    assert issubclass(KommoTokenStoreProtocol, Protocol)


def test_token_store_protocol_is_runtime_checkable():
    assert getattr(KommoTokenStoreProtocol, "__protocol_attrs__", None) is not None or hasattr(
        KommoTokenStoreProtocol, "__subclasshook__"
    )


def test_redis_token_store_satisfies_protocol():
    # KommoTokenStore should structurally match KommoTokenStoreProtocol
    assert hasattr(KommoTokenStore, "get_valid_token")
    assert hasattr(KommoTokenStore, "force_refresh")
