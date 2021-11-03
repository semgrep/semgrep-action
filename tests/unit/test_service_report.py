import json
from pathlib import Path

from _pytest.capture import CaptureFixture

from semgrep_agent.findings import FindingSets
from semgrep_agent.semgrep import Results
from semgrep_agent.semgrep import RunStats
from semgrep_agent.semgrep import SemgrepTiming


def test_service_report(capsys: CaptureFixture[str]):
    with (Path(__file__).parent / "timing-out.json").open() as fd:
        data = json.load(fd)
    timing = SemgrepTiming(rules=data["rules"], targets=data["targets"])
    results = Results(FindingSets(0), RunStats(timing.rules, timing.targets), 600.0)
    results.service_report(100.0)
    stdout = capsys.readouterr().out
    with (Path(__file__).parent / "service-report.out").open() as fd:
        expected = fd.read()
    assert stdout == expected
