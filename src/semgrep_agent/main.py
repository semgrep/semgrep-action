import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import NoReturn
from typing import Optional

import click
import requests
import sh
from boltons import ecoutils
from boltons.strutils import unit_len

from semgrep_agent import constants
from semgrep_agent import formatter
from semgrep_agent import semgrep
from semgrep_agent.meta import detect_meta_environment
from semgrep_agent.meta import GitMeta
from semgrep_agent.semgrep_app import Sapp
from semgrep_agent.utils import maybe_print_debug_info


def url(string: str) -> str:
    return string.rstrip("/")


@dataclass
class CliObj:
    event_type: str
    config: str
    meta: GitMeta
    sapp: Sapp


def get_event_type() -> str:
    if "GITHUB_ACTIONS" in os.environ:
        return os.environ["GITHUB_EVENT_NAME"]

    return "push"


@click.command()
@click.option("--config", envvar="INPUT_CONFIG", type=str)
@click.option(
    "--baseline-ref",
    envvar="BASELINE_REF",
    type=str,
    default=None,
    show_default="detected from CI env",
)
@click.option(
    "--publish-url", envvar="INPUT_PUBLISHURL", type=url, default="https://semgrep.dev"
)
@click.option("--publish-token", envvar="INPUT_PUBLISHTOKEN", type=str)
@click.option("--publish-deployment", envvar="INPUT_PUBLISHDEPLOYMENT", type=int)
@click.option("--json", "json_output", hidden=True, is_flag=True)
# @click.option("--comment-token", envvar="INPUT_COMMENTTOKEN", type=str)
def main(
    config: str,
    baseline_ref: str,
    publish_url: str,
    publish_token: str,
    publish_deployment: int,
    json_output: bool,
    # comment_token: str,
) -> NoReturn:
    click.echo("=== detecting environment", err=True)
    click.echo(
        f"| versions    - "
        f"semgrep {sh.semgrep(version=True).strip()} on "
        f"{sh.python(version=True).strip()}",
        err=True,
    )

    # Get Metadata
    Meta = detect_meta_environment()
    meta_kwargs = {}
    if baseline_ref:
        meta_kwargs["cli_baseline_ref"] = baseline_ref
    meta = Meta(config, **meta_kwargs)
    click.echo(
        f"| environment - "
        f"running in {meta.environment}, "
        f"triggering event is '{meta.event_name}'",
        err=True,
    )

    # Setup URL/Token
    sapp = Sapp(url=publish_url, token=publish_token, deployment_id=publish_deployment)
    maybe_print_debug_info(meta)
    sapp.report_start(meta)
    if sapp.is_configured:
        click.echo(
            f"| semgrep.dev - logged in as deployment #{sapp.deployment_id}", err=True,
        )
    else:
        click.echo("| semgrep.dev - not logged in", err=True)

    # Setup Config
    click.echo("=== setting up agent configuration", err=True)
    if config:
        config = semgrep.resolve_config_shorthand(config)
        click.echo(f"| using semgrep rules from {config}", err=True)
    elif sapp.is_configured:
        local_config_path = sapp.download_rules()
        config = str(local_config_path)
        click.echo("| using semgrep rules configured on the web UI", err=True)
    elif Path(".semgrep.yml").is_file():
        click.echo("| using semgrep rules from the committed .semgrep.yml", err=True)
        config = ".semgrep.yml"
    elif Path(".semgrep").is_dir():
        click.echo(
            "| using semgrep rules from the committed .semgrep/ directory", err=True
        )
        config = ".semgrep/"
    else:
        message = """
            == [ERROR] you didn't configure what rules semgrep should scan for.

            Please either set a config in the CI configuration according to
            https://github.com/returntocorp/semgrep-action#configuration
            or commit your own rules at the default path of `.semgrep.yml`
        """
        message = dedent(message).strip()
        click.echo(message, err=True)
        sys.exit(1)

    committed_datetime = meta.commit.committed_datetime if meta.commit else None
    results = semgrep.scan(
        config,
        committed_datetime,
        meta.base_commit_ref,
        semgrep.get_semgrepignore(sapp.scan.ignore_patterns),
    )
    new_findings = results.findings.new

    blocking_findings = {finding for finding in new_findings if finding.is_blocking()}

    if json_output:
        # Output all new findings as json
        output = [
            f.to_dict(omit=constants.PRIVACY_SENSITIVE_FIELDS) for f in new_findings
        ]
        click.echo(json.dumps(output))
    else:
        # Print out blocking findings
        formatter.dump(blocking_findings)

    non_blocking_findings = {
        finding for finding in new_findings if not finding.is_blocking()
    }
    if non_blocking_findings:
        click.echo(
            f"| {unit_len(non_blocking_findings, 'non-blocking finding')} hidden in output",
            err=True,
        )

    sapp.report_results(results)
    # send comments to github here?
    if os.getenv("GITHUB_ACTIONS") == "true":
        github_session = requests.Session()
        try:
            github_session.headers[
                "Authorization"
            ] = f"Bearer {os.getenv('GITHUB_TOKEN')}"
            url = f"https://api.github.com/repos/{meta.repo_name}/pulls/{meta.to_dict()['pull_request_id']}/comments"
            for finding in new_findings:
                location_msg = f"{finding.path}:{finding.line}"
                if finding.end_line:
                    location = {
                        "start_line": finding.line,
                        "line": finding.end_line,
                        "start_side": "RIGHT",
                    }
                    location_msg += f"-{finding.end_line}"
                else:
                    location = {"line": finding.line}
                if finding.severity == 2:
                    severity_msg = ":x: Error :x:"
                elif finding.severity == 1:
                    severity_msg = ":warning: Warning :warning:"
                else:
                    severity_msg = ":information_source: Info :information_source:"
                click.echo(finding.message)
                body = f"#### Semgrep Report"
                resp = github_session.post(
                    url,
                    json={
                        "body": body,
                        "commit_id": meta.commit_sha,
                        "path": finding.path,
                        **location,
                        "side": "RIGHT",
                    },
                    timeout=30,
                )
                click.echo(resp)
        except Exception as e:
            click.echo(f"Error getting github token/sending request: {e}")

    exit_code = 1 if blocking_findings else 0
    click.echo(
        f"=== exiting with {'failing' if exit_code == 1 else 'success'} status",
        err=True,
    )
    sys.exit(exit_code)
