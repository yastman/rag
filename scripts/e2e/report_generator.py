"""Report generator for E2E test results."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from .claude_judge import JudgeResult
from .test_scenarios import TestScenario


@dataclass
class TestResult:
    """Single test result."""

    scenario: TestScenario
    bot_response: str
    response_time_ms: int
    judge_result: JudgeResult
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Check if test passed."""
        return self.judge_result.passed if self.judge_result else False


@dataclass
class TestReport:
    """Full test report."""

    timestamp: datetime
    bot_username: str
    results: list[TestResult]
    total_duration_ms: int

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def passed_tests(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_tests(self) -> int:
        return self.total_tests - self.passed_tests

    @property
    def average_score(self) -> float:
        scores = [r.judge_result.total_score for r in self.results if r.judge_result]
        return sum(scores) / len(scores) if scores else 0.0

    @property
    def pass_rate(self) -> float:
        return (self.passed_tests / self.total_tests * 100) if self.total_tests else 0.0


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E2E Test Report - {{ report.timestamp.strftime('%Y-%m-%d %H:%M') }}</title>
    <style>
        :root {
            --pass: #22c55e;
            --fail: #ef4444;
            --bg: #1a1a2e;
            --card: #16213e;
            --text: #e8e8e8;
            --muted: #8b8b8b;
        }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: var(--card);
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
        }
        .header h1 { margin: 0 0 8px 0; }
        .header .meta { color: var(--muted); }
        .stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat {
            background: var(--card);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat .value { font-size: 32px; font-weight: bold; }
        .stat .label { color: var(--muted); font-size: 14px; }
        .stat.pass .value { color: var(--pass); }
        .stat.fail .value { color: var(--fail); }
        .results { background: var(--card); border-radius: 12px; overflow: hidden; }
        .result {
            padding: 16px 24px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            cursor: pointer;
        }
        .result:hover { background: rgba(255,255,255,0.05); }
        .result-header {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .status { width: 24px; height: 24px; border-radius: 50%; }
        .status.pass { background: var(--pass); }
        .status.fail { background: var(--fail); }
        .result-id { color: var(--muted); font-family: monospace; }
        .result-name { flex: 1; }
        .result-score { font-weight: bold; }
        .result-details {
            display: none;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        .result.expanded .result-details { display: block; }
        .criteria {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
            margin-bottom: 16px;
        }
        .criterion {
            background: rgba(0,0,0,0.2);
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }
        .criterion .name { font-size: 12px; color: var(--muted); }
        .criterion .score { font-size: 20px; font-weight: bold; }
        .query, .response {
            background: rgba(0,0,0,0.2);
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 12px;
            font-family: monospace;
            white-space: pre-wrap;
            font-size: 13px;
        }
        .label-tag { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>E2E Test Report</h1>
            <div class="meta">
                Bot: {{ report.bot_username }} |
                {{ report.timestamp.strftime('%Y-%m-%d %H:%M:%S') }} |
                Duration: {{ "%.1f"|format(report.total_duration_ms / 1000) }}s
            </div>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="value">{{ report.total_tests }}</div>
                <div class="label">Total Tests</div>
            </div>
            <div class="stat pass">
                <div class="value">{{ report.passed_tests }}</div>
                <div class="label">Passed</div>
            </div>
            <div class="stat fail">
                <div class="value">{{ report.failed_tests }}</div>
                <div class="label">Failed</div>
            </div>
            <div class="stat">
                <div class="value">{{ "%.1f"|format(report.average_score) }}</div>
                <div class="label">Avg Score</div>
            </div>
        </div>

        <div class="results">
            {% for result in report.results %}
            <div class="result" onclick="this.classList.toggle('expanded')">
                <div class="result-header">
                    <div class="status {{ 'pass' if result.passed else 'fail' }}"></div>
                    <span class="result-id">{{ result.scenario.id }}</span>
                    <span class="result-name">{{ result.scenario.name }}</span>
                    <span class="result-score">{{ "%.1f"|format(result.judge_result.total_score) }}</span>
                </div>
                <div class="result-details">
                    <div class="criteria">
                        <div class="criterion">
                            <div class="name">Relevance</div>
                            <div class="score">{{ result.judge_result.relevance.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">Completeness</div>
                            <div class="score">{{ result.judge_result.completeness.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">Filters</div>
                            <div class="score">{{ result.judge_result.filter_accuracy.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">Tone</div>
                            <div class="score">{{ result.judge_result.tone_format.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">No Halluc.</div>
                            <div class="score">{{ result.judge_result.no_hallucination.score }}</div>
                        </div>
                    </div>
                    <div class="label-tag">Query:</div>
                    <div class="query">{{ result.scenario.query }}</div>
                    <div class="label-tag">Response ({{ result.response_time_ms }}ms):</div>
                    <div class="response">{{ result.bot_response[:500] }}{% if result.bot_response|length > 500 %}...{% endif %}</div>
                    <div class="label-tag">Judge Summary:</div>
                    <div class="response">{{ result.judge_result.summary }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>"""


class ReportGenerator:
    """Generate test reports."""

    def __init__(self, reports_dir: str = "reports"):
        """Initialize generator."""
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, report: TestReport) -> tuple[Path, Path]:
        """Generate JSON and HTML reports.

        Returns:
            Tuple of (json_path, html_path)
        """
        timestamp = report.timestamp.strftime("%Y-%m-%d_%H-%M-%S")

        # JSON report
        json_path = self.reports_dir / f"e2e_{timestamp}.json"
        json_data = {
            "timestamp": report.timestamp.isoformat(),
            "bot_username": report.bot_username,
            "total_tests": report.total_tests,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "average_score": report.average_score,
            "pass_rate": report.pass_rate,
            "total_duration_ms": report.total_duration_ms,
            "results": [
                {
                    "scenario_id": r.scenario.id,
                    "scenario_name": r.scenario.name,
                    "query": r.scenario.query,
                    "bot_response": r.bot_response,
                    "response_time_ms": r.response_time_ms,
                    "passed": r.passed,
                    "judge_result": {
                        "total_score": r.judge_result.total_score,
                        "relevance": asdict(r.judge_result.relevance),
                        "completeness": asdict(r.judge_result.completeness),
                        "filter_accuracy": asdict(r.judge_result.filter_accuracy),
                        "tone_format": asdict(r.judge_result.tone_format),
                        "no_hallucination": asdict(r.judge_result.no_hallucination),
                        "summary": r.judge_result.summary,
                    },
                    "error": r.error,
                }
                for r in report.results
            ],
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        # HTML report
        html_path = self.reports_dir / f"e2e_{timestamp}.html"
        template = Template(HTML_TEMPLATE)
        html_content = template.render(report=report)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return json_path, html_path
