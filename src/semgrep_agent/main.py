import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import cast
from typing import NoReturn
from typing import Sequence

import click
import sh
from boltons.strutils import unit_len
from git import InvalidGitRepositoryError

from semgrep_agent import formatter
from semgrep_agent import semgrep
from semgrep_agent.constants import FINDING_EXIT_CODE
from semgrep_agent.constants import GIT_SH_TIMEOUT
from semgrep_agent.constants import LONG_RUNNING_SECONDS
from semgrep_agent.constants import NO_RESULT_EXIT_CODE
from semgrep_agent.exc import ActionFailure
from semgrep_agent.meta import generate_meta_from_environment
from semgrep_agent.meta import GitMeta
from semgrep_agent.semgrep import SemgrepError
from semgrep_agent.semgrep_app import Sapp
from semgrep_agent.utils import get_aligned_command
from semgrep_agent.utils import maybe_print_debug_info
from semgrep_agent.utils import print_sh_error_info

ALL_MANUAL_ENV_VARS = {
    "SEMGREP_BRANCH": "The scanned branch ref",
    "SEMGREP_COMMIT": "The scanned commit SHA",
    "SEMGREP_JOB_URL": "The URL of the CI job that ran this scan, if any",
    "SEMGREP_PR_ID": "The pull or merge request ID, if any",
    "SEMGREP_PR_TITLE": "The pull or merge request title, if any",
    "SEMGREP_REPO_NAME": "The name of this repository",
    "SEMGREP_REPO_URL": "This URL at which this repository's code is located",
}


ENV_VAR_HELP_TEXT = "\n        ".join(
    f"{k}: {v}\n" for k, v in ALL_MANUAL_ENV_VARS.items()
)

LOG_FILE = os.path.expanduser("~/.semgrep/semgrep_agent_logs")


def url(string: str) -> str:
    return string.rstrip("/")


@click.command(
    help=f"""
    Scans a repository for findings using Semgrep rules configured here or on semgrep.dev.

    In its most basic form, semgrep-agent is used by calling:

    $ semgrep-agent --config p/security-audit --config p/secrets

    which will scan a repository using the security-audit and secrets rulesets.

    For more usage and how to configure rules on semgrep.dev, see https://semgrep.dev/docs/semgrep-ci.

    In addition to the options below, the following environment variables can be used to configure the data sent by
    semgrep-agent to semgrep.dev:

        {ENV_VAR_HELP_TEXT}
"""
)
@click.option(
    "--config",
    envvar=["INPUT_CONFIG", "SEMGREP_RULES"],
    type=str,
    help="Define a rule, ruleset, or snippet used to scan this repository (only needed if NOT using semgrep app). You can pass in multiple `--config`s.",
    multiple=True,
)
@click.option(
    "--baseline-ref",
    envvar=["BASELINE_REF", "SEMGREP_BASELINE_REF"],
    type=str,
    default=None,
    help="Only show findings introduced since this Git ref. If not specified, will be detected from CI environment.",
)
@click.option(
    "--publish-token",
    envvar=["INPUT_PUBLISHTOKEN", "SEMGREP_APP_TOKEN"],
    type=str,
    help="Your secret semgrep.dev API token (only needed if using Semgrep App)",
)
@click.option(
    "--publish-deployment",
    envvar=["INPUT_PUBLISHDEPLOYMENT", "SEMGREP_APP_DEPLOYMENT_ID"],
    type=int,
    help="DEPRECATED: your semgrep.dev deployment ID. Now, --publish-token is sufficient. You can remove this from your CI config.",
    hidden=True,
)
@click.option(
    "--enable-metrics/--disable-metrics",
    envvar="SEMGREP_SEND_METRICS",
    default=True,
    is_flag=True,
    help="Enable (default) or disable anonymized metrics used to improve Semgrep",
)
@click.option(
    "--rewrite-rule-ids/--no-rewrite-rule-ids",
    envvar="REWRITE_RULE_IDS",
    default=True,
    is_flag=True,
    help="Specify whether semgrep should or should not rewrite rule-ids based on directory structure (MAY BE DEPRECATED ONCE ANY ARBITRARY SEMGREP CLI FLAG CAN BE PASSED IN)",
    hidden=True,
)
@click.option(
    "--publish-url",
    envvar=["INPUT_PUBLISHURL", "SEMGREP_APP_URL"],
    type=url,
    default="https://semgrep.dev",
    help="The URL of the Semgrep app",
    hidden=True,
)
@click.option(
    "--json", "json_output", envvar="SEMGREP_JSON_OUTPUT", hidden=True, is_flag=True
)
@click.option(
    "--gitlab-json",
    "gitlab_output",
    envvar="SEMGREP_GITLAB_JSON",
    is_flag=True,
)
@click.option(
    "--gitlab-secrets-json",
    "gitlab_secrets_output",
    envvar="SEMGREP_GITLAB_SECRETS_JSON",
    is_flag=True,
)
@click.option(
    "--audit-on",
    envvar=["INPUT_AUDITON", "SEMGREP_AUDIT_ON"],
    multiple=True,
    type=str,
    hidden=True,
)
@click.option(
    "--timeout",
    envvar="SEMGREP_TIMEOUT",
    default=1800,
    type=int,
    help="Maximum number of seconds to allow Semgrep to run (per file batch; default is 1800 seconds; set to 0 to disable)",
    hidden=True,
)
@click.option(
    "--scan-environment",
    default="",
    type=str,
    hidden=True,
)
def main(
    config: str,
    baseline_ref: str,
    publish_url: str,
    publish_token: str,
    publish_deployment: int,
    enable_metrics: bool,
    rewrite_rule_ids: bool,
    json_output: bool,
    gitlab_output: bool,
    gitlab_secrets_output: bool,
    audit_on: Sequence[str],
    timeout: int,
    scan_environment: str,
) -> NoReturn:
    logging.basicConfig(
        filename=(LOG_FILE),
        filemode="w",
        format="%(asctime)s === %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )

    click.echo(
        get_aligned_command(
            "versions",
            f"semgrep {sh.semgrep(version=True).strip()} on {sh.python(version=True).strip()}",
        ),
        err=True,
    )
    # Get metadata from environment variables
    if publish_deployment:
        click.secho(
            "DEPRECATED flag --publish-deployment is no longer used and can be removed from your CI config",
            err=True,
            fg="yellow",
        )
    meta = generate_meta_from_environment(baseline_ref, scan_environment)
    sapp = Sapp(url=publish_url, token=publish_token)
    # Everything below here is covered by fail-open feature
    try:
        protected_main(**locals())
    except SemgrepError as error:
        print_sh_error_info(error.stdout, error.stderr, error.command, error.exit_code)
        _handle_error(error.stderr, error.exit_code, sapp, meta)
    except sh.TimeoutException as error:
        click.secho(
            f"Semgrep took longer than {timeout} seconds to run or a git command took longer than {GIT_SH_TIMEOUT} seconds; canceling this run",
            err=True,
            fg="red",
        )
        _handle_error(str(error), 2, sapp, meta)
    except ActionFailure as error:
        click.secho(str(error), err=True, fg="red")
        _handle_error(str(error), 2, sapp, meta)
    except InvalidGitRepositoryError as error:
        click.secho("Current directory is not a git repository", err=True, fg="red")
        _handle_error(str(error), 2, sapp, meta)
    except Exception as error:
        # Handles all other errors like FileNotFound, EOF, etc.
        # https://docs.python.org/3.9/library/exceptions.html#exception-hierarchy
        click.secho(f"An unexpected error occurred", err=True, fg="red")
        logging.exception(error)  # TODO will I need to change this?
        _handle_error(str(error), 2, sapp, meta)
    # Should never get here, as all sub-functions contain a sys.exit
    sys.exit(0)


def protected_main(
    config: Sequence[str],
    baseline_ref: str,
    publish_url: str,
    publish_token: str,
    publish_deployment: int,
    enable_metrics: bool,
    rewrite_rule_ids: bool,
    json_output: bool,
    gitlab_output: bool,
    gitlab_secrets_output: bool,
    audit_on: Sequence[str],
    timeout: int,
    scan_environment: str,
    sapp: Sapp,
    meta: GitMeta,
) -> NoReturn:
    meta.initialize_repo()
    maybe_print_debug_info(meta)
    click.echo(
        get_aligned_command(
            "environment",
            f"running in environment {meta.environment}, triggering event is '{meta.event_name}'",
        ),
        err=True,
    )

    if not enable_metrics:
        click.echo(
            get_aligned_command("metrics", "disabled"),
            err=True,
        )

    # Setup URL/Token
    if sapp.is_configured:
        policy = sapp.report_start(meta)
        to_server = "" if publish_url == "https://semgrep.dev" else f" to {publish_url}"
        click.echo(
            get_aligned_command(
                "manage",
                f"authenticated{to_server} as the organization '{sapp.deployment_name}'",
            ),
            err=True,
        )
        click.echo(get_aligned_command("policy", f"using {policy}"), err=True)
    else:
        click.echo(get_aligned_command("manage", f"not logged in"), err=True)

    for env_var in ALL_MANUAL_ENV_VARS.keys():
        if os.getenv(env_var):
            click.echo(get_aligned_command(env_var, str(os.getenv(env_var))), err=True)

    # Setup Config
    click.echo("=== setting up agent configuration", err=True)
    rule_ids: Sequence[str] = []
    cai_ids: Sequence[str] = []
    if config:
        if sapp.is_configured:
            message = """
            === [ERROR] Detected config flag while logged in

            Semgrep will only run rules with the Semgrep Cloud features
            if they are in your policy (see semgrep.dev/manage/policies).
            If you intended to use Semgrep Cloud, please remove the config
            flag and add rules/rulesets to your policies instead.
            """
            message = dedent(message).strip()
            click.secho(message, err=True, fg="red")
            sys.exit(1)
        resolved_config = []
        for conf in config:
            resolved = semgrep.resolve_config_shorthand(conf)
            resolved_config.append(resolved)
            click.echo(f"| using semgrep rules from {resolved}", err=True)
        config = resolved_config
    elif sapp.is_configured:
        local_config_path, rule_ids, cai_ids = sapp.download_rules()
        if len(rule_ids) + len(cai_ids) == 0:
            message = """
            === [ERROR] This policy will not run any rules

            Semgrep will only run rules in your policy that
            have an action associated with them (notify or block).
            We have a logging-only option coming soon, but in
            the mean time, you can accomplish this by selecting
            "notify" on the policy tab and not configuring any
            channels on the notifications tab
            """
            message = dedent(message).strip()
            click.secho(message, err=True, fg="red")
            sys.exit(1)
        config = (str(local_config_path),)
        click.echo(
            f"| using {len(rule_ids)} semgrep rules configured on the web UI", err=True
        )
        click.echo(f"| using {len(cai_ids)} code asset inventory rules", err=True)
    elif Path(".semgrep.yml").is_file():
        click.echo("| using semgrep rules from the committed .semgrep.yml", err=True)
        config = (".semgrep.yml",)
    elif Path(".semgrep").is_dir():
        click.echo(
            "| using semgrep rules from the committed .semgrep/ directory", err=True
        )
        config = (".semgrep/",)
    else:
        message = """
            == [ERROR] you didn't configure what rules semgrep should scan with.

            Please either set a config or pass in a token to connect to Semgrep App.
            Detailed explanation and examples are at
            https://semgrep.dev/docs/semgrep-ci/configuration-reference/.
        """
        message = dedent(message).strip()
        click.echo(message, err=True)
        sys.exit(1)

    committed_datetime = meta.commit.committed_datetime if meta.commit else None
    start_time = datetime.now()
    scan_context = semgrep.RunContext(
        config_specifier=config,
        committed_datetime=committed_datetime,
        base_ref=meta.base_commit_ref,
        head_ref=meta.head_ref,
        semgrep_ignore=semgrep.get_semgrepignore(sapp.scan.ignore_patterns),
        rewrite_rule_ids=(rewrite_rule_ids and not sapp.is_configured),
        enable_metrics=enable_metrics,
        timeout=(timeout if timeout > 0 else None),
    )
    results = semgrep.scan(scan_context)
    end_time = datetime.now()

    new_findings = results.findings.new
    errors = results.findings.errors

    blocking_findings = {finding for finding in new_findings if finding.is_blocking()}
    if json_output:
        # Output all new findings as json
        json_contents = [f.to_dict(omit=set()) for f in new_findings]
        click.echo(json.dumps(json_contents))
    elif gitlab_output:
        # output all new findings in Gitlab format
        gitlab_contents = {
            "$schema": "https://gitlab.com/gitlab-org/security-products/security-report-schemas/-/blob/master/dist/sast-report-format.json",
            "version": "2.0",
            "vulnerabilities": [f.to_gitlab() for f in new_findings],
        }
        click.echo(json.dumps(gitlab_contents))
    elif gitlab_secrets_output:
        # schema https://gitlab.com/gitlab-org/security-products/security-report-schemas/-/blob/master/dist/secret-detection-report-format.json
        # output all new findings in Gitlab secret detection format
        gitlab_contents = {
            "version": "14.0.0",
            "vulnerabilities": [f.to_gitlab_secrets() for f in new_findings],
            "remediations": [],
            "scan": {
                "scanner": {
                    "id": "semgrep_agent",
                    "name": "Semgrep Agent",
                    "url": "https://github.com/returntocorp/semgrep-action",
                    "vendor": {"name": "returntocorp"},
                    "version": "v1",
                },
                "type": "secret_detection",
                "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "success" if not errors else "failed",
            },
        }
        click.echo(json.dumps(gitlab_contents))
    else:
        # Print out blocking findings
        formatter.dump(blocking_findings)

    non_blocking_findings = {
        finding for finding in new_findings if not finding.is_blocking()
    }
    if non_blocking_findings:
        inventory_findings_len = 0
        for finding in non_blocking_findings:
            if finding.is_cai_finding():
                inventory_findings_len += 1
        click.echo(
            f"| {unit_len(range(len(non_blocking_findings)-inventory_findings_len), 'non-blocking finding')} hidden in output",
            err=True,
        )
        if inventory_findings_len > 0:
            click.echo(
                f"| Detected technologies for rule recommendation engine",
                err=True,
            )

    results.service_report(min(timeout, LONG_RUNNING_SECONDS))

    if sapp.is_configured:
        sapp.report_results(results, rule_ids, cai_ids)

    audit_mode = meta.event_name in audit_on
    if blocking_findings and audit_mode:
        click.echo(
            f"| audit mode is on for {meta.event_name}, so the findings won't cause failure",
            err=True,
        )

    if sapp.is_configured:
        click.echo(
            f"| to see your findings in the app, go to {publish_url}/orgs/{sapp.deployment_name}/findings?repo={meta.repo_name}",
            err=True,
        )

    exit_code = (
        NO_RESULT_EXIT_CODE
        if audit_mode
        else (FINDING_EXIT_CODE if blocking_findings else NO_RESULT_EXIT_CODE)
    )
    click.echo(
        f"=== exiting with {'failing' if exit_code == 1 else 'success'} status",
        err=True,
    )
    sys.exit(exit_code)


def _handle_error(stderr: str, exit_code: int, sapp: Sapp, meta: GitMeta) -> None:
    # If logged in handle exception
    if sapp.is_configured:
        new_exit_code = (
            sapp.report_failure(stderr, exit_code)
            if sapp.scan.id > 0
            else sapp.fail_open_exit_code(meta, exit_code)
        )
        if new_exit_code == 0:
            click.echo(
                f"Semgrep returned an error (return code {exit_code}). However, this project on {sapp.url} is configured to pass the build on Semgrep errors (fail open). Exiting with a successful return code 0.",
                err=True,
            )
        sys.exit(new_exit_code)
    else:
        sys.exit(exit_code)
