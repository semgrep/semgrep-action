import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterator
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Union

import attr
import click
import sh
from boltons.iterutils import get_path
from boltons.strutils import unit_len
from sh.contrib import git

from semgrep_agent.constants import GIT_SH_TIMEOUT
from semgrep_agent.constants import LOG_FOLDER
from semgrep_agent.exc import ActionFailure
from semgrep_agent.findings import Finding
from semgrep_agent.findings import FindingSets
from semgrep_agent.ignores import yield_exclude_args
from semgrep_agent.utils import debug_echo
from semgrep_agent.utils import get_git_repo
from semgrep_agent.utils import print_git_log
from semgrep_agent.utils import render_error

os.environ["SEMGREP_USER_AGENT_APPEND"] = "(Agent)"
semgrep_exec = sh.semgrep.bake(_ok_code={0, 1}, _tty_out=False, _err=sys.stderr)

SEMGREP_SAVE_FILE = LOG_FOLDER + "/semgrep_agent_output"

SemgrepArgs = Sequence[str]
SemgrepKwargs = Mapping[str, Union[bool, str, int, float]]


@attr.s(auto_attribs=True, frozen=True)
class RunContext:
    # This scan's config specifiers (e.g. p/ci, semgrep.yml, etc.)
    config_specifier: Sequence[str]
    # This commits timestamp (for time-stamping findings)
    committed_datetime: Optional[datetime]
    # The baseline ref; if absent, no baselining is performed
    base_ref: Optional[str]
    # The head ref; Semgrep checks for findings on this ref
    head_ref: Optional[str]
    # If true, rewrites rule IDs in findings to a shorter value
    rewrite_rule_ids: bool
    # If True, sends metrics; also currently sends metrics if False
    enable_metrics: bool
    # If present, Semgrep run is aborted after this many seconds
    timeout: Optional[int]
    # Ignore patterns configured on the semgrep app UI
    requested_excludes: Sequence[str]
    # api key used by semgrep to download policy
    api_key: Optional[str]
    # used by semgrep to download policy
    repo_name: Optional[str]


@attr.s(auto_attribs=True, frozen=True)
class RunStats:
    # Rules
    rule_list: Sequence[Mapping[str, str]]
    # Target match times
    target_data: Sequence[Mapping[str, Any]]

    def longest_targets(self, n: int) -> Sequence[Mapping[str, Any]]:
        """
        Returns the n longest-running files and their associated timing data
        """
        ordered = sorted(
            self.target_data, key=lambda i: i.get("run_time", 0.0), reverse=True
        )
        return ordered[0:n]

    def rules_with_times(self) -> Sequence[Mapping[str, Any]]:
        """
        Annotates the rules list with total run times
        """
        rule_indices = range(len(self.rule_list))
        empty_times: Sequence[float] = [0.0 for _ in rule_indices]

        def combine(memo: Sequence[float], el: Mapping[str, Any]) -> Sequence[float]:
            rt = el.get("match_times", [])
            return [memo[ix] + get_path(rt, (ix,), 0.0) for ix in rule_indices]

        rule_times = reduce(combine, self.target_data, empty_times)
        rules_with_times: Sequence[Mapping[str, Any]] = [
            {**self.rule_list[ix], "run_time": rule_times[ix]} for ix in rule_indices
        ]
        return rules_with_times

    def longest_rules(self, n: int) -> Sequence[Mapping[str, Any]]:
        """
        Returns the longest-running rules
        """
        ordered = sorted(
            self.rules_with_times(), key=lambda i: float(i["run_time"]), reverse=True
        )
        return ordered[0:n]


def resolve_config_shorthand(config: str) -> str:
    maybe_prefix = config[:2]
    if maybe_prefix in {"p/", "r/", "s/"}:
        return f"https://semgrep.dev/c/{config}"
    return config


@dataclass
class Results:
    findings: FindingSets
    run_stats: RunStats
    total_time: float

    def stats(self, *, n_heavy_targets: int) -> Dict[str, Any]:
        return {
            "findings": len(self.findings.new),
            "errors": self.findings.errors,
            "longest_targets": self.run_stats.longest_targets(n_heavy_targets),
            "rules": self.run_stats.rules_with_times(),
            "total_time": self.total_time,
        }

    def service_report(self, run_time_threshold: float) -> None:
        """
        Echoes a user-friendly debugging report for long-running scans
        """
        if self.total_time < run_time_threshold:
            return

        click.echo(
            f"=== Semgrep may be taking longer than expected to run (took {self.total_time:0.2f} s).",
            err=True,
        )
        click.echo(
            "| These files are taking the most time. Consider adding them to .semgrepignore or\n"
            "| ignoring them in your Semgrep.dev policy.",
            err=True,
        )
        for t in self.run_stats.longest_targets(10):
            rt = t.get("run_time", 0.0)
            click.echo(f"|   - {rt:0.2f} s: {t.get('path', '')}", err=True)
        click.echo(
            "| These rules are taking the most time. Consider removing them from your config.",
            err=True,
        )
        for r in self.run_stats.longest_rules(10):
            rt = r["run_time"]
            click.echo(f"|   - {rt:0.2f} s: {r.get('id', '')}", err=True)


def rewrite_sarif_file(sarif_output: Dict[str, Any], sarif_path: Path) -> None:
    """Fix SARIF errors in semgrep output and pretty format the file."""
    # If no files are scanned by invoke_semgrep_sarif then sarif_output is {}. Just write empty sarif for now
    sarif_output.setdefault("runs", [])
    sarif_output.setdefault("version", "2.1.0")

    if sarif_output["runs"]:
        rules_by_id = {
            rule["id"]: rule
            for rule in sarif_output["runs"][0]["tool"]["driver"]["rules"]
        }
        sarif_output["runs"][0]["tool"]["driver"]["rules"] = list(rules_by_id.values())

    with sarif_path.open("w") as sarif_file:
        json.dump(sarif_output, sarif_file, indent=2, sort_keys=True)


def _get_findings(context: RunContext) -> Tuple[FindingSets, RunStats]:
    """
    Gets head and baseline findings for this run

    :param context: This scan's run context object
    :return: This project's findings
    """
    debug_echo("=== adding semgrep configuration")
    exclude_args: SemgrepArgs = list(yield_exclude_args(context.requested_excludes))
    rewrite_kwargs: SemgrepKwargs = (
        {} if context.rewrite_rule_ids else {"no_rewrite_rule_ids": True}
    )
    metrics_kwargs: SemgrepKwargs = (
        {"enable_metrics": True} if context.enable_metrics else {}
    )

    with _fix_head_for_github(context.base_ref, context.head_ref) as base_ref:
        workdir = Path.cwd()
        debug_echo(f"Workdir: {str(workdir)}")

        config_args = []
        # Keep track of which config specifiers are local files/dirs
        for conf in context.config_specifier:
            config_args.extend(["--config", conf])
        debug_echo("=== seeing if there are any findings")

        semgrep_kwargs = {**rewrite_kwargs, **metrics_kwargs}
        if base_ref is not None:
            semgrep_kwargs["baseline_commit"] = base_ref

        findings, stats = _get_new_findings(
            context, [*config_args, *exclude_args], semgrep_kwargs
        )

    if os.getenv("INPUT_GENERATESARIF"):
        click.echo("=== re-running scan to generate a SARIF report", err=True)
        sarif_path = Path("semgrep.sarif")
        _, sarif_output = invoke_semgrep_sarif(
            [*config_args, *exclude_args],
            rewrite_kwargs,
            api_key=context.api_key,
            repo_name=context.repo_name,
            timeout=context.timeout,
        )
        rewrite_sarif_file(sarif_output, sarif_path)

    return findings, stats


def _get_new_findings(
    context: RunContext, semgrep_args: SemgrepArgs, semgrep_kwargs: SemgrepKwargs
) -> Tuple[FindingSets, RunStats]:
    """
    Gets findings for the project's HEAD git commit

    :param context: The Semgrep run context object
    :param semgrep_args: Extra arguments to pass to Semgrep
    :param semgrep_kwargs: Extra arguments to pass to Semgrep
    :param targets: This run's target manager
    :return: A findings object with existing head findings and empty baseline findings
    """
    click.echo("=== looking for new issues", err=True)
    semgrep_kwargs = {
        "skip_unknown_extensions": True,
        "disable_nosem": True,
        "json": True,
        "autofix": True,
        "dryrun": True,
        "time": True,
        "timeout_threshold": 3,
        **semgrep_kwargs,
    }

    exit_code, semgrep_output = invoke_semgrep(
        semgrep_args=semgrep_args,
        semgrep_kwargs=semgrep_kwargs,
        timeout=context.timeout,
        api_key=context.api_key,
        repo_name=context.repo_name,
    )
    findings = FindingSets(
        exit_code,
        searched_paths=set(semgrep_output.searched_paths),
        errors=semgrep_output.errors,
    )

    stats = RunStats(
        rule_list=semgrep_output.timing.rules,
        target_data=semgrep_output.timing.targets,
    )

    findings.new.update_findings(
        Finding.from_semgrep_result(result, context.committed_datetime)
        for result in semgrep_output.results
        if not result["extra"].get("is_ignored")
    )
    findings.new_ignored.update_findings(
        Finding.from_semgrep_result(result, context.committed_datetime)
        for result in semgrep_output.results
        if result["extra"].get("is_ignored")
    )
    if findings.errors:
        click.echo(
            f"| Semgrep exited with {unit_len(findings.errors, 'error')}:",
            err=True,
        )
        for e in findings.errors:
            for s in render_error(e):
                click.echo(f"|    {s}", err=True)
    inventory_findings_len = 0
    for finding in findings.new:
        if finding.is_cai_finding():
            inventory_findings_len += 1
    click.echo(
        f"| {unit_len(range(len(findings.new) - inventory_findings_len), 'current issue')} found",
        err=True,
    )
    if len(findings.new_ignored) > 0:
        click.echo(
            f"| {unit_len(findings.new_ignored, 'issue')} muted with nosemgrep comment (not counted as current)",
            err=True,
        )
    return (
        findings,
        stats,
    )


@attr.s(auto_attribs=True)
class SemgrepTiming:
    rules: Sequence[Mapping[str, str]]
    targets: Sequence[Mapping[str, Any]]


@attr.s(auto_attribs=True)
class SemgrepOutput:
    results: Sequence[Any]
    searched_paths: Sequence[str]
    errors: Sequence[Any]
    timing: SemgrepTiming


def invoke_semgrep(
    semgrep_args: SemgrepArgs,
    semgrep_kwargs: SemgrepKwargs,
    api_key: Optional[str],
    repo_name: Optional[str],
    *,
    timeout: Optional[int],
) -> Tuple[int, SemgrepOutput]:
    """
    Call semgrep passing in semgrep_args + targets as the arguments
    Also, save semgrep output as a list of json blobs in SEMGREP_SAVE_FILE
    to help debugging. Baseline scan output will be saved separately with
    the "_baseline" suffix.

    Returns json output of semgrep as dict object
    """
    env = {}
    if api_key and repo_name:
        env["SEMGREP_LOGIN_TOKEN"] = api_key
        env["SEMGREP_REPO_NAME"] = repo_name

    with tempfile.NamedTemporaryFile("w") as output_json_file:
        output_json_file.flush()
        args = [*semgrep_args, "."]
        kwargs = {
            # nosemgrep: python.lang.correctness.tempfile.flush.tempfile-without-flush
            "output": output_json_file.name,
            "debug": True,
            **semgrep_kwargs,
        }

        debug_echo(f"== Invoking semgrep with {args} and {kwargs}")

        exit_code = semgrep_exec(
            *args,
            **kwargs,
            _timeout=timeout,
            _err=debug_echo,
            _env=env,
        ).exit_code

        debug_echo(f"== Semgrep finished with exit code {exit_code}")

        # nosemgrep: python.lang.correctness.tempfile.flush.tempfile-without-flush
        with open(output_json_file.name) as f:
            semgrep_output = f.read()
    with open(SEMGREP_SAVE_FILE, "w+") as semgrep_save_file:
        semgrep_save_file.write(f"[{semgrep_output}]")

    parsed_output = json.loads(semgrep_output)
    parsed_timing = parsed_output.get("time", {})

    timing = SemgrepTiming(parsed_timing["rules"], parsed_timing["targets"])
    output = SemgrepOutput(
        parsed_output["results"],
        parsed_output["paths"]["scanned"],
        parsed_output["errors"],
        timing,
    )

    return exit_code, output


def invoke_semgrep_sarif(
    semgrep_args: SemgrepArgs,
    semgrep_kwargs: SemgrepKwargs,
    api_key: Optional[str],
    repo_name: Optional[str],
    *,
    timeout: Optional[int],
) -> Tuple[int, Dict[str, List[Any]]]:
    """
    Call semgrep passing in semgrep_args + targets as the arguments

    Returns sarif output of semgrep as dict object
    """
    env = {}
    if api_key and repo_name:
        env["SEMGREP_LOGIN_TOKEN"] = api_key
        env["SEMGREP_REPO_NAME"] = repo_name

    with tempfile.NamedTemporaryFile("w") as output_json_file:
        output_json_file.flush()
        args = [*semgrep_args, "."]
        kwargs = {
            # nosemgrep: python.lang.correctness.tempfile.flush.tempfile-without-flush
            "output": output_json_file.name,
            "debug": True,
            "sarif": True,
            **semgrep_kwargs,
        }

        debug_echo(f"== Invoking semgrep with {args} and {kwargs}")

        exit_code = semgrep_exec(
            *args, **kwargs, _timeout=timeout, _err=debug_echo, _env=env
        ).exit_code

        debug_echo(f"== Semgrep SARIF scan finished with exit code {exit_code}")

        # nosemgrep: python.lang.correctness.tempfile.flush.tempfile-without-flush
        with open(output_json_file.name) as f:
            semgrep_output = f.read()

    return exit_code, json.loads(semgrep_output)


class SemgrepError(Exception):
    def __init__(self, error: sh.ErrorReturnCode):
        self._exit_code = error.exit_code
        self._stdout = error.stdout.decode()
        self._stderr = error.stderr.decode()
        self._command = error.full_cmd

    @property
    def exit_code(self) -> int:
        return self._exit_code

    @property
    def stdout(self) -> str:
        return self._stdout

    @property
    def stderr(self) -> str:
        return self._stderr

    @property
    def command(self) -> str:
        return self._command


def scan(context: RunContext) -> Results:
    """
    Return results object of a scan. Main function exposed by this file
    """
    before = time.time()
    try:
        findings, stats = _get_findings(context)
    except sh.ErrorReturnCode as error:
        raise SemgrepError(error)
    after = time.time()

    return Results(findings, stats, after - before)


@contextmanager
def _fix_head_for_github(
    base_ref_name: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> Iterator[Optional[str]]:
    """
    GHA can checkout the incorrect commit for a PR (it will create a fake merge commit),
    so we need to reset the head to the actual PR branch head before continuing.

    Note that this code is written in a generic manner, so that it becomes a no-op when
    the CI system has not artifically altered the HEAD ref.

    :return: The baseline ref as a commit hash
    """
    debug_echo(
        f"Called _fix_head_for_github with base_ref_name: {base_ref_name} head_ref: {head_ref}"
    )

    stashed_rev: Optional[str] = None
    base_ref: Optional[str] = base_ref_name

    if get_git_repo() is None:
        debug_echo("Yielding base_ref since get_git_repo was None")
        yield base_ref
        return

    if base_ref:
        # Preserve location of head^ after we possibly change location below
        try:
            debug_echo(f"Calling git rev-parse {base_ref}")
            process = git(["rev-parse", base_ref])
            base_ref = process.stdout.decode("utf-8").rstrip()
        except sh.ErrorReturnCode as ex:
            raise ActionFailure(f"There is a problem with your git project:{ex}")

    if head_ref:
        debug_echo("Calling git branch --show-current")
        stashed_rev = git(["branch", "--show-current"]).stdout.decode("utf-8").rstrip()
        debug_echo(f"stashed_rev: {stashed_rev}")
        if not stashed_rev:
            debug_echo("Calling git rev-parse HEAD")
            rev_parse = git(["rev-parse", "HEAD"])
            debug_echo(rev_parse.stderr.decode("utf-8").rstrip())
            stashed_rev = rev_parse.stdout.decode("utf-8").rstrip()
            debug_echo(f"stashed_rev: {stashed_rev}")

        click.echo(f"| not on head ref {head_ref}; checking that out now...", err=True)
        git.checkout(
            [head_ref], _timeout=GIT_SH_TIMEOUT, _out=debug_echo, _err=debug_echo
        )
        debug_echo(f"checked out {head_ref}")

    try:
        if base_ref is not None:
            merge_base = git("merge-base", base_ref, "HEAD").rstrip()
            # fmt:off
            click.echo("| reporting findings introduced by these commits:", err=True)
            print_git_log(f"{merge_base}..HEAD")
            if merge_base != git("rev-parse", base_ref).rstrip():
                click.echo("| also reporting findings fixed by these commits from the baseline branch:", err=True)
                print_git_log(f"{merge_base}..{base_ref}")
                click.echo("| to exclude these latter commits, run with", err=True)
                click.echo(f"|   --baseline-ref $(git merge-base {base_ref_name} HEAD)", err=True)
            # fmt: on
        debug_echo(f"yielding {base_ref}")
        yield base_ref
    finally:
        if stashed_rev is not None:
            click.echo(f"| returning to original head revision {stashed_rev}", err=True)
            git.checkout([stashed_rev], _timeout=GIT_SH_TIMEOUT)
