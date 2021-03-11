import json
import os
import sys
from pathlib import Path
from textwrap import dedent
from textwrap import indent
from typing import cast
from typing import List
from typing import NoReturn
from typing import Optional
from typing import TYPE_CHECKING

import click
import git as gitpython
import sh
from boltons import ecoutils
from sh.contrib import git

from semgrep_agent import constants

if TYPE_CHECKING:
    from semgrep_agent.meta import GitMeta


def debug_echo(text: str) -> None:
    """Print debug messages with context-specific debug formatting."""
    if os.getenv("SEMGREP_AGENT_DEBUG"):
        prefix = "=== [DEBUG] "
    elif os.getenv("GITHUB_ACTIONS"):
        prefix = "::debug::"
    else:
        return
    text = "\n".join(prefix + line for line in text.splitlines())
    click.echo(text, err=True)


def maybe_print_debug_info(meta: "GitMeta") -> None:
    if not os.getenv("SEMGREP_AGENT_DEBUG"):
        return

    debug_echo("\n== ecosystem profile:")
    debug_echo(json.dumps(ecoutils.get_profile(), indent=2, sort_keys=True))
    debug_echo("\n== meta info:")
    debug_echo(json.dumps(meta.to_dict(), indent=2, sort_keys=True))


def get_git_repo(path: Optional[Path] = None) -> Optional[gitpython.Repo]:  # type: ignore
    try:
        r = gitpython.Repo(str(path or Path.cwd()), search_parent_directories=True)
        return r
    except gitpython.exc.InvalidGitRepositoryError:
        return None


def zsplit(s: str) -> List[str]:
    """Split a string on null characters."""
    s = s.strip("\0")
    if s:
        return s.split("\0")
    else:
        return []


def validate_publish_token(token: str) -> bool:
    return constants.PUBLISH_TOKEN_VALIDATOR.match(token) is not None


def print_git_log(log_cmd: str) -> None:
    log = git.log(["--oneline", "--graph", log_cmd]).stdout  # type:ignore
    rr = cast(bytes, log).decode("utf-8").rstrip().split("\n")
    r = "\n|   ".join(rr)
    click.echo("|   " + r, err=True)


def print_sh_error_info(stdout: str, stderr: str, command: str, exit_code: int) -> None:
    message = f"""
    === failed command's STDOUT:

{indent(stdout, 8 * ' ')}

    === failed command's STDERR:

{indent(stderr, 8 * ' ')}

    === [ERROR] `{command}` failed with exit code {exit_code}

    This is an internal error, please file an issue at https://github.com/returntocorp/semgrep-action/issues/new/choose
    and include any log output from above.
    """
    message = dedent(message).strip()
    click.echo("", err=True)
    click.echo(message, err=True)


def exit_with_sh_error(error: sh.ErrorReturnCode) -> NoReturn:
    print_sh_error_info(
        error.stdout.decode(), error.stderr.decode(), error.full_cmd, error.exit_code
    )
    sys.exit(error.exit_code)
