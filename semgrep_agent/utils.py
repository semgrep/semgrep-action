import os

import click


def debug_echo(text: str) -> None:
    """Print debug messages with context-specific debug formatting."""
    if os.getenv("GITHUB_ACTIONS"):
        text = "\n".join("::debug::" + line for line in text.splitlines())
        click.echo(text)
