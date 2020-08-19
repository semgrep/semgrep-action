import io
import json
import os
import sys
import time
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
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

import click
import requests
import sh
from boltons.iterutils import chunked_iter
from boltons.strutils import unit_len
from sh.contrib import git

from .findings import Finding
from .findings import FindingSets
from .meta import GitMeta
from .targets import TargetFileManager
from .utils import debug_echo

if TYPE_CHECKING:
    from .semgrep_app import Scan

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


@contextmanager
def get_semgrep_config(ctx: click.Context) -> Iterator[List[Union[str, Path]]]:
    if ctx.obj.config:
        rules_url = resolve_config_shorthand(ctx.obj.config)
        yield ["--config", resolve_config_shorthand(ctx.obj.config)]
    elif ctx.obj.sapp.is_configured:
        local_config_path = Path(".tmp-semgrep.yml")
        local_config_path.symlink_to(ctx.obj.sapp.download_rules())
        yield ["--config", local_config_path]
        local_config_path.unlink()
    else:
        yield []


def get_semgrepignore(scan: "Scan") -> TextIO:
    semgrepignore = io.StringIO()
    TEMPLATES_DIR = (Path(__file__).parent / "templates").resolve()

    semgrepignore_path = Path(".semgrepignore")
    if semgrepignore_path.is_file():
        click.echo("| using path ignore rules from .semgrepignore")
        semgrepignore.write(semgrepignore_path.read_text())
    else:
        click.echo(
            "| using default path ignore rules of common test and dependency directories"
        )
        semgrepignore.write((TEMPLATES_DIR / ".semgrepignore").read_text())

    if scan_patterns := scan.ignore_patterns:
        click.echo("| adding further path ignore rules configured on the web UI")
        semgrepignore.write("\n# Ignores from semgrep app\n")
        semgrepignore.write("\n".join(scan_patterns))
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


def invoke_semgrep(ctx: click.Context) -> FindingSets:
    debug_echo("=== adding semgrep configuration")

    workdir = Path.cwd()
    targets = TargetFileManager(
        base_path=workdir,
        base_commit=ctx.obj.meta.base_commit_ref,
        paths=[workdir],
        ignore_rules_file=get_semgrepignore(ctx.obj.sapp.scan),
    )

    debug_echo("=== seeing if there are any findings")
    findings = FindingSets()

    with targets.current_paths() as paths, get_semgrep_config(ctx) as config_args:
        click.echo("=== looking for current issues in " + unit_len(paths, "file"))
        for chunk in chunked_iter(paths, PATHS_CHUNK_SIZE):
            args = ["--skip-unknown-extensions", "--json", *config_args]
            for path in chunk:
                args.append(path)
            findings.current.update(
                Finding.from_semgrep_result(result, ctx)
                for result in json.loads(str(semgrep(*args)))["results"]
            )
            click.echo(f"| {unit_len(findings.current, 'current issue')} found")

    if not findings.current:
        click.echo(
            "=== not looking at pre-existing issues since there are no current issues"
        )
    else:
        with targets.baseline_paths() as paths, get_semgrep_config(ctx) as config_args:
            if paths:
                paths_with_findings = {finding.path for finding in findings.current}
                paths_to_check = set(str(path) for path in paths) & paths_with_findings
                click.echo(
                    "=== looking for pre-existing issues in "
                    + unit_len(paths_to_check, "file")
                )
                for chunk in chunked_iter(paths_to_check, PATHS_CHUNK_SIZE):
                    args = ["--json", *config_args]
                    for path in chunk:
                        args.extend(["--include", path])
                    findings.baseline.update(
                        Finding.from_semgrep_result(result, ctx)
                        for result in json.loads(str(semgrep(*args)))["results"]
                    )
                click.echo(
                    f"| {unit_len(findings.baseline, 'pre-existing issue')} found"
                )

    if os.getenv("INPUT_GENERATESARIF"):
        # FIXME: This will crash when running on thousands of files due to command length limit
        click.echo("=== re-running scan to generate a SARIF report")
        sarif_path = Path("semgrep.sarif")
        with targets.current_paths() as paths, sarif_path.open(
            "w"
        ) as sarif_file, get_semgrep_config(ctx) as config_args:
            args = ["--sarif", *config_args]
            for path in paths:
                args.extend(["--include", path])
            semgrep(*args, _out=sarif_file)
        rewrite_sarif_file(sarif_path)

    return findings


def scan(ctx: click.Context) -> Results:
    meta = ctx.obj.meta

    before = time.time()
    try:
        findings = invoke_semgrep(ctx)
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
