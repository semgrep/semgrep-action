#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path

# compat mappings
ENV_TO_ENV: dict[str, str] = {
    "INPUT_CONFIG": "SEMGREP_RULES",
    "BASELINE_REF": "SEMGREP_BASELINE_COMMIT",
    "SEMGREP_BASELINE_REF": "SEMGREP_BASELINE_COMMIT",
    "INPUT_PUBLISHTOKEN": "SEMGREP_APP_TOKEN",
    "INPUT_PUBLISHURL": "SEMGREP_APP_URL",
    "REWRITE_RULE_IDS": "SEMGREP_REWRITE_RULE_IDS",
    "INPUT_AUDITON": "SEMGREP_AUDIT_ON",
}
FLAG_TO_ENV: dict[str, str] = {
    "--publish-url": "SEMGREP_APP_URL",
    "--publish-deployment": "_",  # unused, but we don't want to fail if this is set
    "--publish-token": "SEMGREP_APP_TOKEN",
    "--config": "SEMGREP_RULES",
    "--baseline-ref": "SEMGREP_BASELINE_COMMIT",
    "--timeout": "SEMGREP_TIMEOUT",
    "--audit-on": "SEMGREP_AUDIT_ON",
}
MULTI_VALUED_ENV = ["SEMGREP_AUDIT_ON", "SEMGREP_RULES"]

FLAG_TO_FLAG: dict[str, str] = {
    "--enable-metrics": "--enable-metrics",
    "--disable-metrics": "--disable-metrics",
    "--rewrite-rule-ids": "--rewrite-rule-ids",
    "--no-rewrite-rule-ids": "--no-rewrite-rule-ids",
    "--json": "--json",
    "--gitlab-json": "--gitlab-sast",
    "--gitlab-secrets-json": "--gitlab-secrets",
}
ENV_TO_FLAG: dict[str, str] = {
    "REWRITE_RULE_IDS": "--rewrite-rule-ids",
    "SEMGREP_JSON_OUTPUT": "--json",
    "SEMGREP_GITLAB_JSON": "--gitlab-sast",
    "SEMGREP_GITLAB_SECRETS_JSON": "--gitlab-secrets",
    "SEMGREP_CI_DRY_RUN": "--dry-run",
}

ENV_VARS_TO_LOG = {*ENV_TO_ENV.values(), *FLAG_TO_ENV.values()}
ENV_VARS_TO_LOG.remove("SEMGREP_APP_TOKEN")
ENV_VARS_TO_LOG.remove("_")


class ForwardAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs) -> None:  # type: ignore
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, _, namespace, values, option_string=None) -> None:  # type: ignore
        envvar = FLAG_TO_ENV.get(option_string)
        if envvar:
            if envvar in MULTI_VALUED_ENV and envvar in os.environ:
                os.environ[envvar] += " " + values
            else:
                os.environ[envvar] = values

        new_flag = FLAG_TO_FLAG.get(option_string)
        if new_flag:
            if not hasattr(namespace, "new_flags"):
                namespace.new_flags = set()
            namespace.new_flags.add(new_flag)


def print_deprecation_notice(message: str) -> None:
    print(
        textwrap.dedent(
            """
                =========== DEPRECATION WARNING ===========

                {}

                For questions or support, please reach out at https://r2c.dev/slack
            """
        )
        .strip()
        .format(textwrap.dedent(message).strip())
        + "\n\n",
        file=sys.stderr,
    )


def adapt_environment() -> set[str]:
    """Update env vars and return CLI flags for compatibility with latest Semgrep."""

    for old_var, new_var in ENV_TO_ENV.items():
        if os.getenv(old_var):
            os.environ[new_var] = os.environ.pop(old_var)

    parser = argparse.ArgumentParser()
    for flag in FLAG_TO_ENV:
        parser.add_argument(flag, action=ForwardAction)
    for flag in FLAG_TO_FLAG:
        parser.add_argument(flag, nargs=0, action=ForwardAction)
    args = parser.parse_args()

    new_flags = {flag for envvar, flag in ENV_TO_FLAG.items() if os.getenv(envvar)}
    if hasattr(args, "new_flags"):
        new_flags.update(args.new_flags)

    if not os.getenv("SEMGREP_APP_TOKEN"):
        if Path(".semgrep.yml").exists():
            os.environ["SEMGREP_RULES"] = ".semgrep.yml"
        if Path(".semgrep").exists():
            os.environ["SEMGREP_RULES"] = ".semgrep"

    return new_flags


def run_sarif_scan() -> None:
    cmd = ["semgrep", "scan", "--sarif", "--output=semgrep.sarif"]

    if os.environ.get("SEMGREP_APP_TOKEN"):
        os.environ["SEMGREP_REPO_NAME"] = os.environ.get("GITHUB_REPOSITORY", "")
        cmd.append("--config=policy")

    print_deprecation_notice(
        f"""
        Semgrep's SARIF file generation is changing by 2022 May.
        Please update your CI configuration. Your CI script should run this command to get a SARIF file:
            $ {' '.join(cmd)}

        The above command will always succeed, even if there are findings.
        To report pull request failures and optionally push findings to semgrep.dev, add a separate job that runs:
            $ semgrep ci
        """
    )

    envvars = [f"{k}={v} " for k, v in os.environ.items() if k in ENV_VARS_TO_LOG]
    print(
        "=== Running: " + "".join(envvars) + " ".join(cmd),
        file=sys.stderr,
    )
    subprocess.run(cmd)


def main() -> None:
    flags = adapt_environment()

    if os.environ.get("INPUT_GENERATESARIF", "0") == "1":
        run_sarif_scan()

    if os.environ.get("SEMGREP_AUDIT_ON", ""):
        print_deprecation_notice(
            """
            Semgrep's audit mode setting will be removed by 2022 May.

            Please update your CI configuration. Your CI script should run this command to ignore findings:
                $ semgrep ci || true

            We recommend setting up separate CI jobs for pull request and push events, so that you can ignore findings only on push events.
            """
        )

    if "--json" in flags:
        print(
            textwrap.dedent(
                """
                    =========== WARNING ===========

                    The --json flag has recently changed and is now using
                    a format consistent with Semgrep itself.

                    If you rely on the old format, please pin your Docker image to:
                      returntocorp/semgrep-agent:legacy

                    This legacy image will keep working until May 2022.

                    For questions or support, please reach out at https://r2c.dev/slack
                """
            ).strip()
            + "\n\n",
            file=sys.stderr,
        )

    envvars = [f"{k}={v} " for k, v in os.environ.items() if k in ENV_VARS_TO_LOG]
    cmd = ["semgrep", "ci", *flags]
    print(
        "=== Running: " + "".join(envvars) + " ".join(cmd),
        file=sys.stderr,
    )

    os.execvp("semgrep", cmd)


if __name__ == "__main__":
    main()
