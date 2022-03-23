#!/usr/bin/env python
import os
import subprocess
import sys
import textwrap


def print_deprecation_notice(message: str) -> None:
    print(
        textwrap.dedent(
            f"""
                =========== DEPRECATION WARNING ===========

                {textwrap.dedent(message).strip()}

                For questions or support, please reach out at https://r2c.dev/slack
            """
        ).strip()
        + "\n\n",
        file=sys.stderr,
    )


def run_sarif_scan() -> None:
    cmd = ["semgrep", "scan", "--sarif", "--output=semgrep.sarif"]

    if os.environ.get("SEMGREP_APP_TOKEN"):
        cmd.append("--config=policy")

    print_deprecation_notice(
        """
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
    if os.environ.get("INPUT_GENERATESARIF", "0") == "1":
        run_sarif_scan()

    if os.environ.get("INPUT_AUDITON", ""):
        print_deprecation_notice(
            """
            Semgrep's audit mode setting will be removed by 2022 May.

            Please update your CI configuration. Your CI script should run this command to ignore findings:
                $ semgrep ci || true

            We recommend setting up separate CI jobs for pull request and push events, so that you can ignore findings only on push events.
            """
        )

    os.execvp("semgrep", ["semgrep", "ci"])


if __name__ == "__main__":
    main()
