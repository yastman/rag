from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class StartupSeverity(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass(slots=True)
class StartupSignal:
    source: str
    severity: StartupSeverity
    summary: str
    remediation: str | None = None


@dataclass(slots=True)
class StartupReport:
    signals: list[StartupSignal] = field(default_factory=list)

    def add(self, signal: StartupSignal) -> None:
        self.signals.append(signal)

    def merge(self, other: StartupReport | None) -> None:
        if other is None:
            return
        self.signals.extend(other.signals)

    @property
    def final_severity(self) -> StartupSeverity:
        if any(signal.severity is StartupSeverity.FAILED for signal in self.signals):
            return StartupSeverity.FAILED
        if any(signal.severity is StartupSeverity.DEGRADED for signal in self.signals):
            return StartupSeverity.DEGRADED
        return StartupSeverity.OK

    def render(self) -> str:
        lines = [f"Startup verdict: {self.final_severity.value}"]
        if not self.signals:
            lines.append("- startup checks passed")
            return "\n".join(lines)

        for signal in self.signals:
            line = f"- {signal.source}: {signal.summary}"
            if signal.remediation:
                line = f"{line} | remediation: {signal.remediation}"
            lines.append(line)
        return "\n".join(lines)


class DependencyCheckResult(dict[str, bool]):
    """Dict-like dependency result with attached startup report."""

    def __init__(
        self,
        results: Mapping[str, bool] | None = None,
        *,
        report: StartupReport | None = None,
    ) -> None:
        super().__init__(results or {})
        self.report = report or StartupReport()
