import io
import json
import os
import sys
import time
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from textwrap import indent
from typing import Any
from typing import cast
from typing import Dict
from typing import Generator
from typing import Iterator
from typing import List
from typing import Optional
from typing import TextIO
from typing import Tuple
from typing import TYPE_CHECKING
from typing import Union

import attr
import click
import requests
import sh
from boltons.iterutils import chunked_iter
from boltons.strutils import unit_len
from sh.contrib import git

from semgrep_agent.findings import Finding
from semgrep_agent.findings import FindingSets
from semgrep_agent.meta import GitMeta
from semgrep_agent.targets import TargetFileManager
from semgrep_agent.utils import debug_echo
from semgrep_agent.utils import get_git_repo


def get_semgrepignore(ignore_patterns: List[str]) -> TextIO:
    semgrepignore = io.StringIO()
    TEMPLATES_DIR = (Path(__file__).parent / "templates").resolve()

    semgrepignore_path = Path(".semgrepignore")
    if semgrepignore_path.is_file():
        click.echo("| using path ignore rules from .semgrepignore", err=True)
        semgrepignore.write(semgrepignore_path.read_text())
    else:
        click.echo(
            "| using default path ignore rules of common test and dependency directories",
            err=True,
        )
        semgrepignore.write((TEMPLATES_DIR / ".semgrepignore").read_text())

    if ignore_patterns:
        click.echo(
            "| adding further path ignore rules configured on the web UI", err=True
        )
        semgrepignore.write("\n# Ignores from semgrep app\n")
        semgrepignore.write("\n".join(ignore_patterns))
        semgrepignore.write("\n")

    return semgrepignore


@dataclass
class Results:
    findings: FindingSets
    total_time: float

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "findings": len(self.findings.new),
            "total_time": self.total_time,
        }


@contextmanager
def fix_head_for_github(
    base_commit_ref: Optional[str], head_ref: Optional[str]
) -> Iterator[Optional[str]]:
    """
    GHA can checkout the incorrect commit for a PR (it will create a fake merge commit),
    so we need to reset the head to the actual PR branch head before continuing.

    Note that this code is written in a generic manner, so that it becomes a no-op when
    the CI system has not artifically altered the HEAD ref.

    :return: The baseline ref as a commit hash
    """

    stashed_rev: Optional[str] = None
    base_ref: Optional[str] = base_commit_ref

    if get_git_repo() is None:
        yield base_ref
        return

    if base_ref:
        # Preserve location of head^ after we possibly change location below
        base_ref = git(["rev-parse", base_ref]).stdout.decode("utf-8").rstrip()

    if head_ref:
        stashed_rev = git(["branch", "--show-current"]).stdout.decode("utf-8").rstrip()
        if not stashed_rev:
            stashed_rev = git(["rev-parse", "HEAD"]).stdout.decode("utf-8").rstrip()
        click.echo(f"| not on head ref {head_ref}; checking that out now...", err=True)
        git.checkout([head_ref])

    try:
        if base_ref is not None:
            click.echo("| scanning only the following commits:", err=True)
            # fmt:off
            log = git.log(["--oneline", "--graph", f"{base_ref}..HEAD"]).stdout  # type:ignore
            # fmt: on
            rr = cast(bytes, log).decode("utf-8").rstrip().split("\n")
            r = "\n|   ".join(rr)
            click.echo("|   " + r, err=True)

        yield base_ref
    finally:
        if stashed_rev is not None:
            click.echo(f"| returning to original head revision {stashed_rev}", err=True)
            git.checkout([stashed_rev])


def compare_lockfiles(a_text: Optional[str], b_text: str) -> Dict[str, Any]:
    REMOTE_URL = "https://deps.semgrep.dev/semgrepdep"
    LOCAL_URL = "http://localhost:5000/semgrepdep"
    TARGET_URL = REMOTE_URL
    print(f"posting to {TARGET_URL}...")
    output = requests.post(
        TARGET_URL,
        json={
            "old": a_text,
            "new": b_text,
        },
        timeout=600,
    )
    res: Dict[str, Any] = output.json()
    print(res)
    return res
    # if res['status'] == 1:
    #    print(res)


TARGET_FILENAMES = ["pipfile.lock"]


def get_files_matching_name_insensitive_case(
    paths: List[Path],
) -> Generator[Path, None, None]:
    for target_file in TARGET_FILENAMES:
        for path in paths:
            if path.name.lower() == target_file.lower():
                yield path


def invoke_semgrep(
    base_commit_ref: Optional[str],
    head_ref: Optional[str],
    semgrep_ignore: TextIO,
) -> None:
    debug_echo("=== adding semgrep configuration")

    with fix_head_for_github(base_commit_ref, head_ref) as base_ref:
        workdir = Path.cwd()

        targets = TargetFileManager(
            base_path=workdir,
            base_commit=base_ref,
            paths=[workdir],
            ignore_rules_file=semgrep_ignore,
        )
        old_targets = []
        new_targets = []
        old_targets_text = {}
        new_targets_text = {}
        with targets.current_paths() as current_paths:
            new_targets = list(get_files_matching_name_insensitive_case(current_paths))
            for t in new_targets:
                new_targets_text[t] = t.read_text()

        with targets.baseline_paths() as baseline_paths:
            old_targets = list(get_files_matching_name_insensitive_case(baseline_paths))
            for t in old_targets:
                old_targets_text[t] = t.read_text()

        # we only care about new things or things that changed
        changed_targets = {
            t: (old_targets_text[t], text)
            for t, text in new_targets_text.items()
            if t in old_targets_text
        }
        introduced_targets = {
            t: text for t, text in new_targets_text.items() if t not in old_targets_text
        }

        print("changed", changed_targets.keys())
        print("introduced", introduced_targets.keys())

        res = {}
        for a, b in changed_targets.values():
            res = compare_lockfiles(a, b)
        for a in introduced_targets.values():
            res = compare_lockfiles(None, a)

        output_file = os.environ.get("GITHUB_ENV")
        print(f"output file is {output_file}")
        if output_file is not None:
            with open(output_file, "w") as fout:
                fout.write("MARKDOWN_COMMENT<<EOF")
                fout.write(str(res))
                fout.write("EOF")
        print("::set-output name=semgrepdepoutput::this is custom text")


def cai(
    base_commit_ref: Optional[str], head_ref: Optional[str], semgrep_ignore: TextIO
) -> None:
    invoke_semgrep(base_commit_ref, head_ref, semgrep_ignore)
