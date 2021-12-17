import json
import os
import tempfile
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import cast
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

import click
import requests
from glom import glom
from glom import T
from urllib3.util.retry import Retry

from semgrep_agent import constants
from semgrep_agent.exc import ActionFailure
from semgrep_agent.main import SEMGREP_RULES_FILE
from semgrep_agent.meta import GitMeta
from semgrep_agent.semgrep import Results
from semgrep_agent.utils import debug_echo
from semgrep_agent.utils import validate_token_length
from semgrep_agent.yaml import yaml

# 4, 8, 16 seconds
RETRYING_ADAPTER = requests.adapters.HTTPAdapter(
    max_retries=Retry(
        total=3,
        backoff_factor=4,
        method_whitelist=["GET", "POST"],
        status_forcelist=(413, 429, 500, 502, 503),
    ),
)


@dataclass
class Scan:
    id: int = -1
    ignore_patterns: List[str] = field(default_factory=list)


@dataclass
class Sapp:
    url: str
    token: str
    deployment_id: Optional[int] = None
    deployment_name: Optional[str] = None
    scan: Scan = Scan()
    is_configured: bool = False
    session: requests.Session = field(init=False)

    def __post_init__(self) -> None:
        if self.token:
            self.is_configured = True

            self.session = requests.Session()
            self.session.mount("https://", RETRYING_ADAPTER)
            self.session.headers["Authorization"] = f"Bearer {self.token}"

            if validate_token_length(self.token):
                self.get_deployment_from_token(self.token)
            else:
                raise ActionFailure(
                    f"Received invalid publish token. Length is too short."
                )

    def get_deployment_from_token(self, token: str) -> None:
        response = self.session.get(
            f"{self.url}/api/agent/deployment",
            json={},
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(
                f"API server at {self.url} returned this error: {response.text}\n"
                "Failed to get deployment"
            )
        data = response.json()
        self.deployment_id = data.get("deployment").get("id")
        self.deployment_name = data.get("deployment").get("name")

    def fail_open_exit_code(self, meta: GitMeta, exit_code: int) -> int:
        response = self.session.get(
            f"{self.url}/api/agent/deployment/{self.deployment_id}/repos/{meta.repo_name}",
            json={},
            timeout=30,
        )
        repo_data = response.json()
        fail_open = repo_data.get("repo").get("fail_open")
        return 0 if fail_open else exit_code

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
            raise ActionFailure("No rules returned by server for this scan.")
        else:
            return response.text

    def download_rules(self) -> Tuple[Path, List[str], List[str]]:
        """Save the rules configured on semgrep app to a file in .semgrep_logs"""
        """so that it persists for debugging """
        rules_file = SEMGREP_RULES_FILE
        rules_path = Path(rules_file)
        rules = self.fetch_rules_text()
        parsed = yaml.load(rules)
        rules_path.write_text(rules)
        rule_ids = [
            r["id"] for r in parsed["rules"] if "r2c-internal-cai" not in r["id"]
        ]
        cai_ids = [r["id"] for r in parsed["rules"] if "r2c-internal-cai" in r["id"]]
        return rules_path, rule_ids, cai_ids

    def report_failure(self, stderr: str, exit_code: int) -> int:
        """
        Send semgrep cli non-zero exit code information to server
        and return what exit code semgrep should exit with.
        """
        debug_echo(f"=== sending failure information to semgrep app")

        response = self.session.post(
            f"{self.url}/api/agent/scan/{self.scan.id}/error",
            json={
                "exit_code": exit_code,
                "stderr": stderr,
            },
            timeout=30,
        )

        debug_echo(f"=== POST .../error responded: {response!r}")
        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(f"API server returned this error: {response.text}")

        exit_code = int(response.json()["exit_code"])
        return exit_code

    def report_results(
        self, results: Results, rule_ids: Sequence[str], cai_ids: Sequence[str]
    ) -> None:
        debug_echo(f"=== reporting results to semgrep app at {self.url}")

        fields_to_omit = constants.PRIVACY_SENSITIVE_FIELDS.copy()

        if "pr-comment-autofix" in os.getenv("SEMGREP_AGENT_OPT_IN_FEATURES", ""):
            fields_to_omit.remove("fixed_lines")

        response = self.session.post(
            f"{self.url}/api/agent/scan/{self.scan.id}/findings",
            json={
                # send a backup token in case the app is not available
                "token": os.getenv("GITHUB_TOKEN"),
                "gitlab_token": os.getenv("GITLAB_TOKEN"),
                "findings": [
                    finding.to_dict(omit=fields_to_omit)
                    for finding in results.findings.new
                ],
                "searched_paths": [str(p) for p in results.findings.searched_paths],
                "rule_ids": rule_ids,
                "cai_ids": cai_ids,
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
                    finding.to_dict() for finding in results.findings.new_ignored
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
        # In order to not overload our app database, we truncate target stats to the 20 heaviest hitters. This adds
        # approximately 80 kB of database load per scan when using p/ci.
        response = self.session.post(
            f"{self.url}/api/agent/scan/{self.scan.id}/complete",
            json={
                "exit_code": results.findings.max_exit_code,
                "stats": results.stats(n_heavy_targets=20),
            },
            timeout=30,
        )
        debug_echo(f"=== POST .../complete responded: {response!r}")

        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(
                f"API server at {self.url} returned this error: {response.text}"
            )
