from unittest import mock
from unittest.mock import Mock

from semgrep_agent.semgrep_app import Sapp

TEST_URL = "https://nonexist.semgrep.dev"
DEPLOYMENT_ID = 0
SCAN_ID = 5
FAIL_MESSAGE = (
    "Failed to send notifications for findings: no notification channels are enabled"
)


def mock_request_post(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code != 200:
                raise Exception

        def json(self):
            return self.json_data

    if args[0] == f"{TEST_URL}/api/agent/scan/{SCAN_ID}/findings":
        return MockResponse(
            {
                "result": "error",
                "errors": [
                    {
                        "type": "NoNotificationChannel",
                        "message": FAIL_MESSAGE,
                    }
                ],
            },
            200,
        )
    else:
        return MockResponse({"result": "ok"}, 200)


def test_no_notification(capfd):
    dummy_token = "a" * 64
    sapp = Sapp(url=TEST_URL, token=dummy_token, deployment_id=DEPLOYMENT_ID)

    sapp.scan = Mock()
    sapp.scan.id = SCAN_ID

    sapp.session = Mock()
    sapp.session.post = mock_request_post

    results = Mock()
    results.findings.new = []
    results.findings.ignored = []
    results.findings.searched_paths = []

    sapp.report_results(results, [], [])

    # Check Stdout
    out, err = capfd.readouterr()

    assert err == f"Server returned following warning: {FAIL_MESSAGE}\n"
