import sys

import click

from semgrep_agent.main import main
from semgrep_agent.utils import ActionFailure


def error_guard() -> None:
    try:
        main()
    except ActionFailure as ex:
        click.secho(ex.message, fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    error_guard()
