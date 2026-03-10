"""Tests for mini_app.expert_start models."""


def test_start_expert_request_model():
    """StartExpertRequest should have required fields."""
    from mini_app.expert_start import StartExpertRequest

    req = StartExpertRequest(user_id=123, expert_id="consultant", message="Подбери квартиру")
    assert req.user_id == 123
    assert req.expert_id == "consultant"
    assert req.message == "Подбери квартиру"


def test_start_expert_request_optional_message():
    """Message should be optional."""
    from mini_app.expert_start import StartExpertRequest

    req = StartExpertRequest(user_id=123, expert_id="consultant")
    assert req.message is None


def test_start_expert_response_has_start_link():
    """StartExpertResponse should return start_link for deep linking."""
    from mini_app.expert_start import StartExpertResponse

    resp = StartExpertResponse(
        start_link="https://t.me/testbot?start=q_abc123",
        expert_name="Консультант",
    )
    assert resp.start_link == "https://t.me/testbot?start=q_abc123"
    assert resp.expert_name == "Консультант"
    assert resp.status == "ok"


def test_start_expert_response_no_thread_id():
    """StartExpertResponse should NOT have thread_id (old approach removed)."""
    from mini_app.expert_start import StartExpertResponse

    resp = StartExpertResponse(
        start_link="https://t.me/testbot?start=q_abc",
        expert_name="Консультант",
    )
    assert not hasattr(resp, "thread_id")
