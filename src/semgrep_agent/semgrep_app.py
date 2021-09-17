import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import cast
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import requests
from urllib3.util.retry import Retry

from semgrep_agent import constants
from semgrep_agent.exc import ActionFailure
from semgrep_agent.meta import GitMeta
from semgrep_agent.semgrep import Results
from semgrep_agent.semgrep import SemgrepError
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
    org_id: Optional[int] = None
    org_name: Optional[str] = None
    rules_str: Optional[str] = None
    policy: Optional[Dict[str, Any]] = None
    meta: Optional[GitMeta] = None
    scan: Scan = Scan()
    is_configured: bool = False
    session: requests.Session = field(init=False)

    def __post_init__(self) -> None:
        if self.token:
            self.is_configured = True

            self.session = requests.Session()
            self.session.mount("https://", RETRYING_ADAPTER)
            # self.session.headers["Authorization"] = f"Bearer {self.token}"

            if validate_token_length(self.token):
                self.get_org_config_from_token(self.token)
            else:
                raise ActionFailure(
                    f"Received invalid publish token. Length is too short."
                )

    def get_org_config_from_token(self, token: str) -> None:
        # TODO change this to the Semgrep Registry and clean up the format
        url = "https://gist.githubusercontent.com/DrewDennison/b9934d2927dbb64928466d5af815aefd/raw/a9e77e75709606f32cfb6b2e7adfd20db4047b47/DrewDennison.json"
        response = self.session.get(
            url,
            json={},
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.RequestException:
            raise ActionFailure(
                f"API server at {url} returned this error: {response.text}\n"
                "Failed to get org config"
            )
        data = response.json()
        self.org_id = data.get("org").get("id")
        self.org_name = data.get("org").get("name")
        self.policy = data.get("policy")
        self.rules_str = data.get("rules_str")

    def wrap_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload_str = json.dumps(payload)
        hmac_signature = hmac.new(
            self.token.encode(), payload_str.encode(), hashlib.sha256
        ).hexdigest()
        return {"signature": hmac_signature, "payload": payload}

    def validate_rules(self) -> str:
        """Get a YAML string with the configured semgrep rules in it."""
        if self.rules_str is None:
            raise ActionFailure("No rules returned by server for this scan.")
        parsed = yaml.load(self.rules_str)
        if not parsed["rules"]:
            raise ActionFailure("No rules returned by server for this scan.")
        else:
            return self.rules_str

    def fail_open_exit_code(self, meta: GitMeta, exit_code: int) -> int:
        policy = self.policy or {}
        default_fail_open = policy.get("defaults", {}).get("fail_open", True)
        fail_open = policy.get("repos", {}).get(meta.repo_name, default_fail_open)
        return 0 if fail_open else exit_code

    def download_rules(self) -> Tuple[Path, List[str], List[str]]:
        """Save the rules configured on semgrep app to a temporary file"""
        # hey, it's just a tiny YAML file in CI, we'll survive without cleanup
        rules_file = tempfile.NamedTemporaryFile(suffix=".yml", delete=False)  # nosem
        rules_path = Path(rules_file.name)  # nosem
        rules = self.validate_rules()
        parsed = yaml.load(rules)
        rules_path.write_text(rules)
        rule_ids = [
            r["id"] for r in parsed["rules"] if "r2c-internal-cai" not in r["id"]
        ]
        cai_ids = [r["id"] for r in parsed["rules"] if "r2c-internal-cai" in r["id"]]
        return rules_path, rule_ids, cai_ids

    def report_start(self, meta: GitMeta) -> str:
        self.meta = meta
        return (self.policy or {}).get("name", "no policy")

    def report_failure(self, stderr: str) -> int:
        # TODO give this a nice domain like collector.semgrep.dev/v1/failure etc
        url = "https://11hnyozw6a.execute-api.us-west-2.amazonaws.com/prod/v1/upload"
        debug_echo(f"=== reporting failure to semgrep app at {url}")
        payload = {
            "org": {"id": self.org_id, "name": self.org_name},
            "meta": self.meta.to_dict() if self.meta else None,
            "stderr": stderr,
        }
        response = self.session.post(
            url,
            json=self.wrap_payload(payload),
            timeout=30,
        )
        debug_echo(f"=== POST .../upload responded: {response!r}")
        try:
            response.raise_for_status()

        except requests.RequestException:
            raise ActionFailure(f"API server returned this error: {response.text}")

        return 0

    def report_results(
        self, results: Results, rule_ids: List[str], cai_ids: List[str]
    ) -> None:
        # TODO give this a nice domain like collector.semgrep.dev/v1/finding etc
        url = "https://11hnyozw6a.execute-api.us-west-2.amazonaws.com/prod/v1/upload"
        debug_echo(f"=== reporting results to semgrep app at {url}")

        fields_to_omit = constants.PRIVACY_SENSITIVE_FIELDS.copy()

        if "pr-comment-autofix" in os.getenv("SEMGREP_AGENT_OPT_IN_FEATURES", ""):
            fields_to_omit.remove("fixed_lines")
        payload = {
            "org": {"id": self.org_id, "name": self.org_name},
            "meta": self.meta.to_dict() if self.meta else None,
            "findings": [
                finding.to_dict(omit=fields_to_omit) for finding in results.findings.new
            ],
            "ignores": [finding.to_dict() for finding in results.findings.ignored],
            "searched_paths": [str(p) for p in results.findings.searched_paths],
            "rule_ids": rule_ids,
            "cai_ids": cai_ids,
            "scan": {
                "exit_code": results.findings.max_exit_code,
                "stats": results.stats,
            },
        }
        response = self.session.post(
            url,
            json=self.wrap_payload(payload),
            timeout=30,
        )
        debug_echo(f"=== POST .../upload responded: {response!r}")
        try:
            response.raise_for_status()

        except requests.RequestException:
            raise ActionFailure(f"API server returned this error: {response.text}")
