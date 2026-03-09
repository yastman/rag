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
