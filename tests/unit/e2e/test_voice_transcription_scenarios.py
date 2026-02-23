"""Unit checks for voice-transcription E2E scenario catalog (#538)."""

from scripts.e2e import test_scenarios as scenarios


def test_voice_transcription_group_has_three_scenarios():
    group_scenarios = scenarios.get_scenarios_by_group(scenarios.TestGroup.VOICE_TRANSCRIPTION)
    assert len(group_scenarios) == 3


def test_voice_transcription_scenarios_have_expected_ids():
    group_scenarios = scenarios.get_scenarios_by_group(scenarios.TestGroup.VOICE_TRANSCRIPTION)
    scenario_ids = {s.id for s in group_scenarios}
    assert scenario_ids == {"8.1", "8.2", "8.3"}
