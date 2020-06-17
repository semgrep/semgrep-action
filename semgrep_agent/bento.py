import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import TYPE_CHECKING

import click
import requests
import sh
from sh.contrib import git

from .meta import GitMeta
from .utils import debug_echo

if TYPE_CHECKING:
    from .semgrep_app import Scan

bento = sh.bento.bake(
    agree=True,
    email="semgrep-agent@returntocorp.com",
    _ok_code={0, 1, 2},
    _tty_out=False,
)


@dataclass
class Results:
    exit_code: int
    findings: Optional[List[Dict[str, Any]]]
    total_time: float

    @classmethod
    def from_sh_command(
        cls, sh_command: sh.RunningCommand, meta: GitMeta, elapsed: float
    ) -> "Results":
        commit_date = meta.commit.committed_datetime.isoformat()

        findings = None
        if sh_command.stdout:
            findings = json.loads(sh_command.stdout.decode())
            # Augment each findings result with commit date for slicing purposes
            for f in findings:
                f["commit_date"] = commit_date

        return cls(
            exit_code=sh_command.exit_code, findings=findings, total_time=elapsed,
        )

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "findings": len(self.findings) if self.findings else None,
            "total_time": self.total_time,
        }


def configure_bento(scan: "Scan") -> None:
    TEMPLATES_DIR = (Path(__file__).parent / "templates").resolve()

    Path(".bento").mkdir(exist_ok=True)

    bentoignore_path = Path(".bentoignore").resolve()
    if not bentoignore_path.is_file():
        debug_echo(f"creating bentoignore at {bentoignore_path}")
        bentoignore_path.write_text((TEMPLATES_DIR / ".bentoignore").read_text())

    with bentoignore_path.open("a") as bentoignore_file:
        bentoignore_file.write("\n# Ignores from semgrep app\n")
        bentoignore_file.write("\n".join(scan.ignore_patterns))
        bentoignore_file.write("\n")

    bento_config_path = (Path(".bento") / "config.yml").resolve()
    if not bento_config_path.is_file():
        debug_echo(f"creating bento config at {bento_config_path}")
        bento_config_path.write_text((TEMPLATES_DIR / "config.yml").read_text())


def scan_github_pull_request(ctx: click.Context) -> sh.RunningCommand:
    env = os.environ.copy()
    if ctx.obj.config:
        env["BENTO_REGISTRY"] = ctx.obj.config

    # the github ref would be `refs/pull/<pr #>/merge` which isn't known by name here
    # the github sha seems to refer to the base on re-runs
    # so we keep our own head ref around
    real_head_sha = git("rev-parse", "HEAD").stdout.strip()

    debug_echo(
        "== [1/4] going to go back to the commit you based your pull request on…"
    )
    git.checkout(os.environ["GITHUB_BASE_REF"])
    debug_echo(git.status("--branch", "--short").stdout.decode())

    debug_echo("== [2/4] …now adding your pull request's changes back…")
    git.checkout(real_head_sha, "--", ".")
    debug_echo(git.status("--branch", "--short").stdout.decode())

    debug_echo("== [3/4] …adding the bento configuration…")
    configure_bento(ctx.obj.sapp.scan)

    debug_echo("== [4/4] …and seeing if there are any new findings!")
    human_run = bento.check(tool="semgrep", _env=env, _out=sys.stdout, _err=sys.stderr)

    if not ctx.obj.sapp.is_configured:
        return human_run

    return bento.check(tool="semgrep", _env=env, formatter="json")


def scan_gitlab_merge_request(ctx: click.Context) -> sh.RunningCommand:
    env = os.environ.copy()
    if ctx.obj.config:
        env["BENTO_REGISTRY"] = ctx.obj.config

    git.fetch(
        os.environ["CI_MERGE_REQUEST_PROJECT_URL"],
        os.environ["CI_MERGE_REQUEST_TARGET_BRANCH_NAME"],
    )
    merge_base = git("merge-base", "--all", "HEAD", "FETCH_HEAD").stdout.decode()
    debug_echo(
        "== [1/4] going to go back to the commit you based your pull request on…"
    )
    git.checkout(merge_base)
    debug_echo(git.status("--branch", "--short").stdout.decode())

    debug_echo("== [2/4] …now adding your pull request's changes back…")
    git.checkout(os.environ["CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"], "--", ".")
    debug_echo(git.status("--branch", "--short").stdout.decode())

    debug_echo("== [3/4] …adding the bento configuration…")
    configure_bento(ctx.obj.sapp.scan)

    debug_echo("== [4/4] …and seeing if there are any new findings!")
    human_run = bento.check(tool="semgrep", _env=env, _out=sys.stdout, _err=sys.stderr)

    if not ctx.obj.sapp.is_configured:
        return human_run

    return bento.check(tool="semgrep", _env=env, formatter="json")


def scan_all(ctx: click.Context) -> sh.RunningCommand:
    debug_echo("== adding the bento configuration")
    configure_bento(ctx.obj.sapp.scan)

    if ctx.obj.config and ctx.obj.config.startswith("r/"):
        resp = requests.get(f"https://semgrep.live/c/{ctx.obj.config}", timeout=10)
        with Path(".bento/semgrep.yml").open("w") as fd:
            fd.write(resp.content.decode("utf-8"))

    debug_echo("== seeing if there are any findings")
    human_run = bento.check(tool="semgrep", all=True, _out=sys.stdout, _err=sys.stderr)

    if not ctx.obj.sapp.is_configured:
        return human_run

    return bento.check(tool="semgrep", all=True, formatter="json")


def scan(ctx: click.Context) -> Results:
    meta = ctx.obj.meta
    debug_echo(f"== triggered by a {meta.environment} {meta.event_name} event")

    before = time.time()
    try:
        if meta.environment == "github-actions" and meta.event_name == "pull_request":
            results = scan_github_pull_request(ctx)
        elif (
            meta.environment == "gitlab-ci" and meta.event_name == "merge_request_event"
        ):
            results = scan_gitlab_merge_request(ctx)
        else:
            results = scan_all(ctx)
    except sh.ErrorReturnCode as error:
        log_path = Path.home() / ".bento" / "last.log"
        if log_path.exists():
            click.echo(log_path.read_text(), err=True)
        else:  # it's from a git command
            click.echo(error.stderr)
        message = f"""
        == [ERROR] `{error.full_cmd}` failed with exit code {error.exit_code}

        This is an internal error, please file an issue at https://github.com/returntocorp/semgrep/issues/new/choose
        and include any log output from above.
        """
        message = dedent(message).strip()
        click.echo(message, err=True)
        sys.exit(error.exit_code)
    after = time.time()

    return Results.from_sh_command(results, meta, after - before)
