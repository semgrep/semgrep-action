import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import NoReturn
from typing import Optional

import click
import sh
from boltons import ecoutils
from boltons.strutils import unit_len

from semgrep_agent import constants
from semgrep_agent import formatter
from semgrep_agent import semgrep
from semgrep_agent.meta import detect_meta_environment
from semgrep_agent.meta import GitMeta
from semgrep_agent.semgrep_app import Sapp
from semgrep_agent.utils import maybe_print_debug_info


def url(string: str) -> str:
    return string.rstrip("/")


@dataclass
class CliObj:
    event_type: str
    config: str
    meta: GitMeta
    sapp: Sapp


def get_event_type() -> str:
    if "GITHUB_ACTIONS" in os.environ:
        return os.environ["GITHUB_EVENT_NAME"]
    return "push"


def get_aligned_command(title: str, subtext: str) -> str:
    return f"| {title.ljust(17)} - {subtext}"


@click.command()
@click.option(
    "--baseline-ref",
    envvar="BASELINE_REF",
    type=str,
    default=None,
    show_default="detected from CI env",
)
def main(
    baseline_ref: str,
) -> NoReturn:
    click.echo("=== detecting environment", err=True)
    click.echo(
        get_aligned_command(
            "versions",
            f"semgrep {sh.semgrep(version=True).strip()} on {sh.python(version=True).strip()}",
        ),
        err=True,
    )

    # Get Metadata
    Meta = detect_meta_environment()
    meta_kwargs = {}
    if baseline_ref:
        meta_kwargs["cli_baseline_ref"] = baseline_ref
    meta = Meta('noconfig', **meta_kwargs)
    click.echo(
        get_aligned_command(
            "environment",
            f"running in environment {meta.environment}, triggering event is '{meta.event_name}'",
        ),
        err=True,
    )
    
    committed_datetime = meta.commit.committed_datetime if meta.commit else None

    results = semgrep.cai(
        meta.base_commit_ref,
        meta.head_ref,
        semgrep.get_semgrepignore([]),
    )