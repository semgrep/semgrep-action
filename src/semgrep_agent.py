#!/usr/bin/env python
import os
import subprocess
import sys
import textwrap


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


def adapt_environment() -> list[str]:
    """Update env vars and return CLI flags for compatibility with latest Semgrep."""
    ENV_MAPPINGS: dict[str, str] = {
        "INPUT_CONFIG": "SEMGREP_RULES",
        "BASELINE_REF": "SEMGREP_BASELINE_COMMIT",
        "SEMGREP_BASELINE_REF": "SEMGREP_BASELINE_COMMIT",
        "INPUT_PUBLISHTOKEN": "SEMGREP_APP_TOKEN",
        "INPUT_PUBLISHURL": "SEMGREP_APP_URL",
        "REWRITE_RULE_IDS": "SEMGREP_REWRITE_RULE_IDS",
        "SEMGREP_JSON_OUTPUT": "SEMGREP_REWRITE_RULE_IDS",
        "INPUT_AUDITON": "SEMGREP_AUDIT_ON",
    }

    for old_var, new_var in ENV_MAPPINGS.items():
        if old_var in os.environ:
            os.environ[new_var] = os.environ.pop(old_var)

    FLAG_MAPPINGS: dict[str, str] = {
        "REWRITE_RULE_IDS": "--rewrite-rule-ids",
        "SEMGREP_JSON_OUTPUT": "--json",
        "SEMGREP_GITLAB_JSON": "--gitlab-sast",
        "SEMGREP_GITLAB_SECRETS_JSON": "--gitlab-secrets",
    }

    return [flag for envvar, flag in FLAG_MAPPINGS.items() if envvar in os.environ]


def run_sarif_scan() -> None:
    cmd = ["semgrep", "scan", "--sarif", "--output=semgrep.sarif"]

    if os.environ.get("SEMGREP_APP_TOKEN"):
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

    os.execvp("semgrep", ["semgrep", "ci", *flags])


if __name__ == "__main__":
    main()
