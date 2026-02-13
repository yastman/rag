"""One-time SIP trunk provisioning for lifecell Ukraine."""

import asyncio
import os
from typing import cast

from livekit import api
from livekit.protocol.sip import CreateSIPOutboundTrunkRequest, SIPOutboundTrunkInfo


async def setup_lifecell_trunk() -> str:
    """Create lifecell outbound SIP trunk. Returns trunk ID."""
    lk = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL", "http://localhost:7880"),
        api_key=os.getenv("LIVEKIT_API_KEY", "devkey"),
        api_secret=os.getenv("LIVEKIT_API_SECRET", "secret"),
    )

    sip_user = os.getenv("LIFECELL_SIP_USER", "")
    sip_pass = os.getenv("LIFECELL_SIP_PASS", "")
    sip_number = os.getenv("LIFECELL_SIP_NUMBER", "")

    if not sip_user or not sip_pass:
        raise ValueError("LIFECELL_SIP_USER and LIFECELL_SIP_PASS required")

    trunk = SIPOutboundTrunkInfo(
        name="lifecell-ukraine-outbound",
        address="csbc.lifecell.ua:5061",
        numbers=[sip_number] if sip_number else [],
        auth_username=sip_user,
        auth_password=sip_pass,
    )

    result = await lk.sip.create_sip_outbound_trunk(CreateSIPOutboundTrunkRequest(trunk=trunk))
    trunk_id = result.sip_trunk_id
    if not isinstance(trunk_id, str) or not trunk_id:
        raise RuntimeError("LiveKit SIP trunk creation returned invalid trunk id")
    print(f"Created lifecell trunk: {trunk_id}")

    await lk.aclose()
    return trunk_id


if __name__ == "__main__":
    asyncio.run(setup_lifecell_trunk())
