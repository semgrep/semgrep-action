import json
import os
import tempfile
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import cast
from typing import List
from typing import Optional
from typing import Tuple

import click
import requests
from glom import glom
from glom import T
from ruamel.yaml import YAML  # type: ignore

from semgrep_agent import constants
from semgrep_agent.meta import GitMeta
from semgrep_agent.semgrep import Results
from semgrep_agent.utils import ActionFailure
from semgrep_agent.utils import debug_echo
from semgrep_agent.utils import validate_publish_token

yaml = YAML(typ="rt")


@dataclass
class Scan:
    id: int = -1
    ignore_patterns: List[str] = field(default_factory=list)


@dataclass
class Sapp:
    url: str
    token: str
    deployment_id: int
    scan: Scan = Scan()
    is_configured: bool = False
    session: requests.Session = field(init=False)

    def __post_init__(self) -> None:
        if self.token and self.deployment_id:
            self.is_configured = True
        if self.is_configured and not validate_publish_token(self.token):
            raise ActionFailure(
                f"Received invalid publish token, token length {len(self.token)}. "
                f"Please check your publish token."
            )
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.token}"

    def report_start(self, meta: GitMeta) -> str:
        """
        Get scan id and file ignores

        returns name of policy used to scan
        """
        debug_echo(f"=== reporting start to semgrep app at {self.url}")

        response = self.session.post(
            f"{self.url}/api/agent/deployment/{self.deployment_id}/scan",
            json={"meta": meta.to_dict()},
            timeout=30,
        )

        debug_echo(f"=== POST .../scan responded: {response!r}")

        if response.status_code == 404:
            raise ActionFailure(
                "Failed to create a scan with given token and deployment_id."
                "Please make sure they have been set correctly."
                f"API server at {self.url} returned this response: {response.text}"
            )

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
                ignore_patterns=glom(body, T["scan"]["meta"].get("ignored_files", [])),
            )
            debug_echo(f"=== Our scan object is: {self.scan!r}")
            return cast(str, glom(body, T["policy"]))

    def fetch_rules_text(self) -> str:
        """Get a YAML string with the configured semgrep rules in it."""
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

        # Can remove once server guarantees will always have at least one rule
        parsed = yaml.load(response.text)
        if not parsed["rules"]:
            raise ActionFailure(
                "No rules returned by server for this scan. Note that if a rule is not set to notify or block it is not returned by the server."
            )
        else:
            return response.text

    def download_rules(self) -> Tuple[Path, int]:
        """Save the rules configured on semgrep app to a temporary file"""
        # hey, it's just a tiny YAML file in CI, we'll survive without cleanup
        rules_file = tempfile.NamedTemporaryFile(suffix=".yml", delete=False)  # nosem
        rules_path = Path(rules_file.name)  # nosem
        rules = self.fetch_rules_text()
        parsed = yaml.load(rules)
        rules_path.write_text(rules)
        return rules_path, len(parsed["rules"])

    def report_results(self, results: Results) -> None:
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

            errors = response.json()["errors"]
            for error in errors:
                message = error["message"]
                click.echo(f"Server returned following warning: {message}", err=True)

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
