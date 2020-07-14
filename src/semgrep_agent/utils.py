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

if TYPE_CHECKING:
    from .meta import GitMeta


def debug_echo(text: str) -> None:
    """Print debug messages with context-specific debug formatting."""
    if os.getenv("GITHUB_ACTIONS"):
        prefix = "::debug::"
    elif os.getenv("SEMGREP_AGENT_DEBUG"):
        prefix = "=== [DEBUG] "
    else:
        return
    text = "\n".join(prefix + line for line in text.splitlines())
    click.echo(text)


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
    if s := s.strip("\0"):
        return s.split("\0")
    else:
        return []
