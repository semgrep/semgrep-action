from dataclasses import dataclass
from dataclasses import field
from typing import Optional

import click
import requests
from boltons.iterutils import chunked_iter

from .bento import Results


@dataclass
class Sapp:
    ctx: click.Context
    url: str
    token: str
    deployment_id: int
    scan_id: Optional[int] = None
    session: requests.Session = field(init=False)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.token}"

    def report_start(self) -> None:
        if self.token is None or self.deployment_id is None:
            return

        try:
            response = self.session.post(
                f"{self.url}/api/agent/deployment/{self.deployment_id}/scan",
                json={"meta": self.ctx.obj.meta.to_dict()},
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException:
            click.echo(f"Semgrep App returned this error: {response.text}", err=True)
        else:
            self.scan_id = response.json()["scan"]["id"]

    def report_results(self, results: Results) -> None:
        if self.token is None or self.deployment_id is None or self.scan_id is None:
            return

        # report findings
        for chunk in chunked_iter(results.findings, 10_000):
            try:
                response = self.session.post(
                    f"{self.url}/api/agent/scan/{self.scan_id}/findings",
                    json=chunk,
                    timeout=30,
                )
                response.raise_for_status()
            except requests.RequestException:
                click.echo(
                    f"Semgrep App returned this error: {response.text}", err=True
                )

        # mark as complete
        try:
            response = self.session.post(
                f"{self.url}/api/agent/scan/{self.scan_id}/complete",
                json={"exit_code": results.exit_code, "stats": results.stats},
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException:
            click.echo(f"Semgrep App returned this error: {response.text}", err=True)
