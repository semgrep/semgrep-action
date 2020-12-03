import os
import tempfile
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import cast
from typing import List
from typing import Optional

import requests
from glom import glom
from glom import T

from semgrep_agent import constants
from semgrep_agent.meta import GitMeta
from semgrep_agent.semgrep import Results
from semgrep_agent.utils import ActionFailure
from semgrep_agent.utils import debug_echo


@dataclass
class Scan:
    id: int = -1
    config: str = "r/all"
    ignore_patterns: List[str] = field(default_factory=list)

    @property
    def is_loaded(self) -> bool:
        return self.id != -1


@dataclass
class Sapp:
    url: str
    token: str
    deployment_id: int
    scan: Scan = Scan()
    is_configured: bool = False
    session: requests.Session = field(init=False)

    def __post_init__(self) -> None:
        # Get deployment from token
        #
        if self.token and self.deployment_id:
            self.is_configured = True
        if self.is_configured and len(self.token) < constants.PUBLISH_TOKEN_LENGTH:
            raise ActionFailure(
                f"Expected token length {constants.PUBLISH_TOKEN_LENGTH}, received length {len(self.token)}. "
                f"Please check your publish token."
            )
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.token}"

    def report_start(self, meta: GitMeta) -> Optional[str]:
        if not self.is_configured:
            debug_echo("=== no semgrep app config, skipping report_start")
            return None
        debug_echo(f"=== reporting start to semgrep app at {self.url}")

        response = self.session.post(
            f"{self.url}/api/agent/deployment/{self.deployment_id}/scan",
            json={"meta": meta.to_dict()},
            timeout=30,
        )
        debug_echo(f"=== POST .../scan responded: {response!r}")
        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(
                f"API server at {self.url} returned this error: {response.text}"
            )
        else:
            body = response.json()
            self.scan = Scan(
                id=glom(body, T["scan"]["id"]),
                config=glom(body, T["scan"]["meta"].get("config")),
                ignore_patterns=glom(body, T["scan"]["meta"].get("ignored_files", [])),
            )
            debug_echo(f"=== Our scan object is: {self.scan!r}")
            return cast(Optional[str], glom(body, T["policy"], default=None))

    def fetch_rules_text(self) -> str:
        """Get a YAML string with the configured semgrep rules in it."""
        if not self.scan.is_loaded:
            raise ActionFailure(
                f"The API server at {self.url} is not working properly. "
                f"Please contact {constants.SUPPORT_EMAIL} for assistance."
            )

        response = self.session.get(
            f"{self.url}/api/agent/scan/{self.scan.id}/rules.yaml",
            timeout=30,
        )
        debug_echo(f"=== POST .../rules.yaml responded: {response!r}")

        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(
                f"API server at {self.url} returned this error: {response.text}\n"
                "Failed to get configured rules"
            )
        else:
            return response.text

    def download_rules(self) -> Path:
        """Save the rules configured on semgrep app to a temporary file"""
        # hey, it's just a tiny YAML file in CI, we'll survive without cleanup
        rules_file = tempfile.NamedTemporaryFile(suffix=".yml", delete=False)  # nosem
        rules_path = Path(rules_file.name)
        rules_path.write_text(self.fetch_rules_text())
        return rules_path

    def report_results(self, results: Results) -> None:
        if not self.is_configured or not self.scan.is_loaded:
            debug_echo("=== no semgrep app config, skipping report_results")
            return
        debug_echo(f"=== reporting results to semgrep app at {self.url}")

        response: Optional["requests.Response"] = None

        response = self.session.post(
            f"{self.url}/api/agent/scan/{self.scan.id}/findings",
            json={
                "token": os.getenv("GITHUB_TOKEN"),
                "findings": [
                    finding.to_dict(omit=constants.PRIVACY_SENSITIVE_FIELDS)
                    for finding in results.findings.new
                ],
            },
            timeout=30,
        )
        debug_echo(f"=== POST .../findings responded: {response!r}")
        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(f"API server returned this error: {response.text}")

        response = self.session.post(
            f"{self.url}/api/agent/scan/{self.scan.id}/ignores",
            json={
                "findings": [
                    finding.to_dict(omit=constants.PRIVACY_SENSITIVE_FIELDS)
                    for finding in results.findings.ignored
                ],
            },
            timeout=30,
        )
        debug_echo(f"=== POST .../ignores responded: {response!r}")
        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(f"API server returned this error: {response.text}")

        # mark as complete
        response = self.session.post(
            f"{self.url}/api/agent/scan/{self.scan.id}/complete",
            json={"exit_code": -1, "stats": results.stats},
            timeout=30,
        )
        debug_echo(f"=== POST .../complete responded: {response!r}")

        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(
                f"API server at {self.url} returned this error: {response.text}"
            )
