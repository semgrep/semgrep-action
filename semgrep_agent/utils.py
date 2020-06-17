import os

import click


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
