"""Expected state values consumed by catalog and favorites handlers."""

import pytest

from telegram_bot.observability.state_helpers import (
    _state_apartment_results,
    _state_control_message_id,
)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({}, []),
        ({"apartment_results": [{"id": 1}, None, "invalid"]}, [{"id": 1}]),
        ({"catalog_runtime": {"results": [{"id": 2}, False]}}, [{"id": 2}]),
        (
            {"apartment_results": [], "catalog_runtime": {"results": [{"id": 2}]}},
            [],
        ),
        (
            {"apartment_results": [{"id": 1}], "catalog_runtime": {"results": [{"id": 2}]}},
            [{"id": 1}],
        ),
        (
            {"apartment_results": None, "catalog_runtime": {"results": [{"id": 2}]}},
            [{"id": 2}],
        ),
        ({"catalog_runtime": None}, []),
        ({"catalog_runtime": {"results": {"id": 2}}}, []),
        ({"apartment_results": "invalid", "catalog_runtime": {}}, []),
    ],
)
def test_apartment_results(state, expected):
    assert _state_apartment_results(state) == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({}, None),
        ({"catalog_runtime": {"control_message_id": 42}, "apartment_footer_msg_id": 7}, 42),
        ({"catalog_runtime": {"control_message_id": 0}, "apartment_footer_msg_id": 7}, 0),
        ({"apartment_footer_msg_id": 7}, 7),
        ({"catalog_runtime": {"control_message_id": "42"}, "apartment_footer_msg_id": 7}, 7),
        ({"catalog_runtime": None, "apartment_footer_msg_id": 7}, 7),
        ({"catalog_runtime": {}, "apartment_footer_msg_id": "7"}, None),
        ({"catalog_runtime": {"control_message_id": None}}, None),
    ],
)
def test_control_message_id(state, expected):
    assert _state_control_message_id(state) == expected
