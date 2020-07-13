import json
import os
from typing import TYPE_CHECKING

import click
from boltons import ecoutils

if TYPE_CHECKING:
    from .meta import GitMeta


def debug_echo(text: str) -> None:
    """Print debug messages with context-specific debug formatting."""
    if os.getenv("GITHUB_ACTIONS"):
        prefix = "::debug::"
    elif os.getenv("SEMGREP_AGENT_DEBUG"):
        prefix = "== [DEBUG] "
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
