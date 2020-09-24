import io
import json
import os
import sys
import time
import urllib.parse
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from textwrap import indent
from typing import Any
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import TextIO
from typing import TYPE_CHECKING
from typing import Union

import attr
import click
import requests
import sh
from boltons.iterutils import chunked_iter
from boltons.strutils import cardinalize
from boltons.strutils import unit_len
from sh.contrib import git

from semgrep_agent.findings import Finding
from semgrep_agent.findings import FindingKey
from semgrep_agent.findings import FindingSets
from semgrep_agent.meta import GitMeta
from semgrep_agent.targets import TargetFileManager
from semgrep_agent.utils import debug_echo

if TYPE_CHECKING:
    from semgrep_agent.semgrep_app import Scan

semgrep = sh.semgrep.bake(_ok_code={0, 1, 2}, _tty_out=False)

# a typical old system has 128 * 1024 as their max command length
# we assume an average ~250 characters for a path in the worst case
PATHS_CHUNK_SIZE = 500


def resolve_config_shorthand(config: str) -> str:
    maybe_prefix = config[:2]
    if maybe_prefix in {"p/", "r/"}:
        return f"https://semgrep.dev/c/{config}"
    elif maybe_prefix == "s/":
        return f"https://semgrep.dev/c/{config[2:]}"
    else:
        return config


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


@attr.s(frozen=True)
class Results(object):
    findings = attr.ib(type=FindingSets)
    total_time = attr.ib(type=float)
    new = attr.ib(type=set, init=False)

    def __attrs_post_init__(self) -> None:
        # Since class is frozen we must use object.__setattr__ (per attrs documentation)
        object.__setattr__(self, "new", self.findings.expensive_new())

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "findings": len(self.new),
            "total_time": self.total_time,
        }


def rewrite_sarif_file(sarif_path: Path) -> None:
    """Fix SARIF errors in semgrep output and pretty format the file."""

    with sarif_path.open() as sarif_file:
        sarif_results = json.load(sarif_file)

    rules_by_id = {
        rule["id"]: rule for rule in sarif_results["runs"][0]["tool"]["driver"]["rules"]
    }
    sarif_results["runs"][0]["tool"]["driver"]["rules"] = list(rules_by_id.values())

    with sarif_path.open("w") as sarif_file:
        json.dump(sarif_results, sarif_file, indent=2, sort_keys=True)


def _update_finding_set(
    result: Dict[str, Any],
    committed_datetime: Optional[datetime],
    findingsMap: Dict[FindingKey, List[Finding]],
) -> None:
    key, finding = Finding.from_semgrep_result(result, committed_datetime)
    forKey = findingsMap.get(key, [])
    forKey.append(finding)
    findingsMap[key] = forKey


def invoke_semgrep(
    config_specifier: str,
    committed_datetime: Optional[datetime],
    base_commit_ref: Optional[str],
    semgrep_ignore: TextIO,
) -> FindingSets:
    debug_echo("=== adding semgrep configuration")

    workdir = Path.cwd()
    targets = TargetFileManager(
        base_path=workdir,
        base_commit=base_commit_ref,
        paths=[workdir],
        ignore_rules_file=semgrep_ignore,
    )

    config_args = ["--config", config_specifier]

    debug_echo("=== seeing if there are any findings")
    findingSet = FindingSets()

    with targets.current_paths() as paths:
        click.echo(
            "=== looking for current issues in " + unit_len(paths, "file"), err=True
        )
        for chunk in chunked_iter(paths, PATHS_CHUNK_SIZE):
            args = ["--skip-unknown-extensions", "--json", *config_args]
            for path in chunk:
                args.append(path)
            count = 0
            for result in json.loads(str(semgrep(*args)))["results"]:
                _update_finding_set(result, committed_datetime, findingSet.current_map)
                count += 1
            click.echo(
                f"| {count} {cardinalize('current issue', count)} found", err=True
            )

    if not findingSet.current_map:
        click.echo(
            "=== not looking at pre-existing issues since there are no current issues",
            err=True,
        )
    else:
        with targets.baseline_paths() as paths:
            if paths:
                paths_with_findings = {
                    finding.path for finding in findingSet.current_map.keys()
                }
                paths_to_check = set(str(path) for path in paths) & paths_with_findings
                click.echo(
                    "=== looking for pre-existing issues in "
                    + unit_len(paths_to_check, "file"),
                    err=True,
                )
                for chunk in chunked_iter(paths_to_check, PATHS_CHUNK_SIZE):
                    args = ["--skip-unknown-extensions", "--json", *config_args]
                    for path in chunk:
                        args.append(path)
                    count = 0
                    for result in json.loads(str(semgrep(*args)))["results"]:
                        _update_finding_set(
                            result, committed_datetime, findingSet.baseline_map
                        )
                        count += 1
                click.echo(
                    f"| {count} {cardinalize('pre-existing issue', count)} found",
                    err=True,
                )

    if os.getenv("INPUT_GENERATESARIF"):
        # FIXME: This will crash when running on thousands of files due to command length limit
        click.echo("=== re-running scan to generate a SARIF report", err=True)
        sarif_path = Path("semgrep.sarif")
        with targets.current_paths() as paths, sarif_path.open("w") as sarif_file:
            args = ["--sarif", *config_args]
            for path in paths:
                args.extend(["--include", path])
            semgrep(*args, _out=sarif_file)
        rewrite_sarif_file(sarif_path)

    return findingSet


def scan(
    config_specifier: str,
    committed_datetime: Optional[datetime],
    base_commit_ref: Optional[str],
    semgrep_ignore: TextIO,
) -> Results:
    before = time.time()
    try:
        findings = invoke_semgrep(
            config_specifier, committed_datetime, base_commit_ref, semgrep_ignore
        )
    except sh.ErrorReturnCode as error:
        message = f"""
        === failed command's STDOUT:

{indent(error.stdout.decode(), 8 * ' ')}

        === failed command's STDERR:

{indent(error.stderr.decode(), 8 * ' ')}

        === [ERROR] `{error.full_cmd}` failed with exit code {error.exit_code}

        This is an internal error, please file an issue at https://github.com/returntocorp/semgrep-action/issues/new/choose
        and include any log output from above.
        """
        message = dedent(message).strip()
        click.echo("", err=True)
        click.echo(message, err=True)
        sys.exit(error.exit_code)
    after = time.time()

    return Results(findings, after - before)
