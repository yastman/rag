# tests/unit/voice/test_sip_setup.py
"""Tests for SIP trunk provisioning (lifecell Ukraine)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


livekit = pytest.importorskip("livekit")


class TestSetupLifecellTrunk:
    """Test setup_lifecell_trunk() provisioning."""

    @pytest.fixture(autouse=True)
    def _env_vars(self, monkeypatch):
        """Set required env vars for all tests."""
        monkeypatch.setenv("LIVEKIT_URL", "http://localhost:7880")
        monkeypatch.setenv("LIVEKIT_API_KEY", "testkey")
        monkeypatch.setenv("LIVEKIT_API_SECRET", "testsecret")
        monkeypatch.setenv("LIFECELL_SIP_USER", "sipuser")
        monkeypatch.setenv("LIFECELL_SIP_PASS", "sippass")
        monkeypatch.setenv("LIFECELL_SIP_NUMBER", "+380123456789")

    async def test_success_returns_trunk_id(self, monkeypatch):
        """Successful provisioning returns trunk ID string."""
        mock_result = MagicMock()
        mock_result.sip_trunk_id = "trunk_abc123"

        mock_sip = MagicMock()
        mock_sip.create_sip_outbound_trunk = AsyncMock(return_value=mock_result)

        mock_api = MagicMock()
        mock_api.sip = mock_sip
        mock_api.aclose = AsyncMock()

        with patch("src.voice.sip_setup.api.LiveKitAPI", return_value=mock_api):
            from src.voice.sip_setup import setup_lifecell_trunk

            trunk_id = await setup_lifecell_trunk()

        assert trunk_id == "trunk_abc123"
        mock_api.aclose.assert_awaited_once()

    async def test_missing_sip_user_raises(self, monkeypatch):
        """Missing LIFECELL_SIP_USER raises ValueError."""
        monkeypatch.setenv("LIFECELL_SIP_USER", "")

        mock_api = MagicMock()
        mock_api.aclose = AsyncMock()

        with patch("src.voice.sip_setup.api.LiveKitAPI", return_value=mock_api):
            from src.voice.sip_setup import setup_lifecell_trunk

            with pytest.raises(ValueError, match="LIFECELL_SIP_USER"):
                await setup_lifecell_trunk()

    async def test_missing_sip_pass_raises(self, monkeypatch):
        """Missing LIFECELL_SIP_PASS raises ValueError."""
        monkeypatch.setenv("LIFECELL_SIP_PASS", "")

        mock_api = MagicMock()
        mock_api.aclose = AsyncMock()

        with patch("src.voice.sip_setup.api.LiveKitAPI", return_value=mock_api):
            from src.voice.sip_setup import setup_lifecell_trunk

            with pytest.raises(ValueError, match="LIFECELL_SIP_PASS"):
                await setup_lifecell_trunk()

    async def test_invalid_trunk_id_raises(self, monkeypatch):
        """Empty trunk ID from LiveKit raises RuntimeError."""
        mock_result = MagicMock()
        mock_result.sip_trunk_id = ""

        mock_sip = MagicMock()
        mock_sip.create_sip_outbound_trunk = AsyncMock(return_value=mock_result)

        mock_api = MagicMock()
        mock_api.sip = mock_sip
        mock_api.aclose = AsyncMock()

        with patch("src.voice.sip_setup.api.LiveKitAPI", return_value=mock_api):
            from src.voice.sip_setup import setup_lifecell_trunk

            with pytest.raises(RuntimeError, match="invalid trunk id"):
                await setup_lifecell_trunk()

    async def test_trunk_created_with_correct_address(self, monkeypatch):
        """SIP trunk uses lifecell address and credentials."""
        mock_result = MagicMock()
        mock_result.sip_trunk_id = "trunk_xyz"

        mock_sip = MagicMock()
        mock_sip.create_sip_outbound_trunk = AsyncMock(return_value=mock_result)

        mock_api = MagicMock()
        mock_api.sip = mock_sip
        mock_api.aclose = AsyncMock()

        with patch("src.voice.sip_setup.api.LiveKitAPI", return_value=mock_api):
            from src.voice.sip_setup import setup_lifecell_trunk

            await setup_lifecell_trunk()

        call_args = mock_sip.create_sip_outbound_trunk.call_args
        request = call_args[0][0]
        assert request.trunk.address == "csbc.lifecell.ua:5061"
        assert request.trunk.auth_username == "sipuser"
        assert request.trunk.auth_password == "sippass"
        assert request.trunk.numbers == ["+380123456789"]

    async def test_no_number_uses_empty_list(self, monkeypatch):
        """When LIFECELL_SIP_NUMBER is empty, numbers list is empty."""
        monkeypatch.setenv("LIFECELL_SIP_NUMBER", "")

        mock_result = MagicMock()
        mock_result.sip_trunk_id = "trunk_no_num"

        mock_sip = MagicMock()
        mock_sip.create_sip_outbound_trunk = AsyncMock(return_value=mock_result)

        mock_api = MagicMock()
        mock_api.sip = mock_sip
        mock_api.aclose = AsyncMock()

        with patch("src.voice.sip_setup.api.LiveKitAPI", return_value=mock_api):
            from src.voice.sip_setup import setup_lifecell_trunk

            trunk_id = await setup_lifecell_trunk()

        assert trunk_id == "trunk_no_num"
        call_args = mock_sip.create_sip_outbound_trunk.call_args
        request = call_args[0][0]
        assert request.trunk.numbers == []
