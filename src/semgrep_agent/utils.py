import json
import os
import urllib.parse
from pathlib import Path
from typing import List
from typing import Optional
from typing import TYPE_CHECKING

import click
import git as gitpython
from boltons import ecoutils
from sh.contrib import git

from semgrep_agent import constants

if TYPE_CHECKING:
    from semgrep_agent.meta import GitMeta


class ActionFailure(Exception):
    """
    Indicates that Semgrep failed and should abort, but prevents a stack trace
    """

    def __init__(self, message: str) -> None:
        self.message = message


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
