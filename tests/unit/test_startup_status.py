from telegram_bot.startup_status import StartupReport, StartupSeverity, StartupSignal


def test_report_is_failed_when_critical_signal_present() -> None:
    report = StartupReport()
    report.add(
        StartupSignal(
            source="redis",
            severity=StartupSeverity.FAILED,
            summary="Redis unavailable",
            remediation="start redis",
        )
    )

    assert report.final_severity is StartupSeverity.FAILED


def test_report_renders_single_compact_summary_block() -> None:
    report = StartupReport()
    report.add(
        StartupSignal(
            source="history",
            severity=StartupSeverity.DEGRADED,
            summary="/history disabled",
            remediation="restore qdrant history collection",
        )
    )

    text = report.render()

    assert "Startup verdict: DEGRADED" in text
    assert "/history disabled" in text
