import io
import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterator
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Set
from typing import TextIO
from typing import Tuple

import attr
import click
import sh
from boltons.iterutils import chunked_iter
from boltons.iterutils import get_path
from boltons.strutils import unit_len
from sh.contrib import git

from semgrep_agent.constants import GIT_SH_TIMEOUT
from semgrep_agent.constants import LOG_FOLDER
from semgrep_agent.exc import ActionFailure
from semgrep_agent.findings import Finding
from semgrep_agent.findings import FindingSets
from semgrep_agent.targets import TargetFileManager
from semgrep_agent.utils import debug_echo
from semgrep_agent.utils import get_git_repo
from semgrep_agent.utils import print_git_log
from semgrep_agent.utils import render_error

ua_environ = {"SEMGREP_USER_AGENT_APPEND": "(Agent)", **os.environ}
semgrep_exec = sh.semgrep.bake(_ok_code={0, 1}, _tty_out=False, _env=ua_environ)

SEMGREP_SAVE_FILE = LOG_FOLDER + "/semgrep_agent_output"

# a typical old system has 128 * 1024 as their max command length
# we assume an average ~250 characters for a path in the worst case
PATHS_CHUNK_SIZE = 500


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
    # Ignore file text stream
    semgrep_ignore: TextIO
    # If true, rewrites rule IDs in findings to a shorter value
    rewrite_rule_ids: bool
    # If True, sends metrics; also currently sends metrics if False
    enable_metrics: bool
    # If present, Semgrep run is aborted after this many seconds
    timeout: Optional[int]


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
            self.target_data, key=lambda i: sum(i.get("run_times", [])), reverse=True
        )
        return ordered[0:n]

    def rules_with_times(self) -> Sequence[Mapping[str, Any]]:
        """
        Annotates the rules list with total run times
        """
        rule_indices = range(len(self.rule_list))
        empty_times: Sequence[float] = [0.0 for _ in rule_indices]

        def combine(memo: Sequence[float], el: Mapping[str, Any]) -> Sequence[float]:
            rt = el.get("run_times", [])
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
            f"=== Semgrep may be taking longer than expected to run (took {self.total_time:0.2f} s)."
        )
        click.echo(
            "| These files are taking the most time. Consider adding them to .semgrepignore or\n"
            "| ignoring them in your Semgrep.dev policy."
        )
        for t in self.run_stats.longest_targets(10):
            rt = sum(t.get("run_times", []))
            click.echo(f"|   - {rt:0.2f} s: {t.get('path', '')}")
        click.echo(
            "| These rules are taking the most time. Consider removing them from your config."
        )
        for r in self.run_stats.longest_rules(10):
            rt = r["run_time"]
            click.echo(f"|   - {rt:0.2f} s: {r.get('id', '')}")


def rewrite_sarif_file(sarif_output: Dict[str, Any], sarif_path: Path) -> None:
    """Fix SARIF errors in semgrep output and pretty format the file."""
    # If no files are scanned by invoke_semgrep_sarif then sarif_output is {}. Just write empty sarif for now
    if not sarif_output:
        with sarif_path.open("w") as sarif_file:
            json.dump(sarif_output, sarif_file, indent=2)
        return

    rules_by_id = {
        rule["id"]: rule for rule in sarif_output["runs"][0]["tool"]["driver"]["rules"]
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

    rewrite_args: Sequence[str] = (
        [] if context.rewrite_rule_ids else ["--no-rewrite-rule-ids"]
    )
    metrics_args: Sequence[str] = ["--enable-metrics"] if context.enable_metrics else []

    with _fix_head_for_github(context.base_ref, context.head_ref) as base_ref:
        workdir = Path.cwd()
        targets = TargetFileManager(
            base_path=workdir,
            base_commit=base_ref,
            all_paths=[workdir],
            ignore_rules_file=context.semgrep_ignore,
        )

        config_args = []
        # Keep track of which config specifiers are local files/dirs
        local_configs: Set[str] = set()
        for conf in context.config_specifier:
            if Path(conf).exists():
                local_configs.add(conf)
            config_args.extend(["--config", conf])
        debug_echo("=== seeing if there are any findings")

        findings, stats = _get_head_findings(
            context, [*config_args, *metrics_args, *rewrite_args], targets
        )

    _update_baseline_findings(context, findings, local_configs, rewrite_args, targets)

    if os.getenv("INPUT_GENERATESARIF"):
        click.echo("=== re-running scan to generate a SARIF report", err=True)
        sarif_path = Path("semgrep.sarif")
        with targets.current_paths() as paths:
            args = [*rewrite_args, *config_args]
            _, sarif_output = invoke_semgrep_sarif(
                args, [str(p) for p in paths], timeout=context.timeout
            )
        rewrite_sarif_file(sarif_output, sarif_path)

    return findings, stats


def _get_head_findings(
    context: RunContext, extra_args: Sequence[str], targets: TargetFileManager
) -> Tuple[FindingSets, RunStats]:
    """
    Gets findings for the project's HEAD git commit

    :param context: The Semgrep run context object
    :param extra_args: Extra arguments to pass to Semgrep
    :param targets: This run's target manager
    :return: A findings object with existing head findings and empty baseline findings
    """
    with targets.current_paths() as paths:
        click.echo(
            "=== looking for current issues in " + unit_len(paths, "file"), err=True
        )

        for path in paths:
            debug_echo(f"searching {str(path)}")

        args = [
            "--skip-unknown-extensions",
            "--disable-nosem",
            "--json",
            "--autofix",
            "--dryrun",
            "--time",
            "--timeout-threshold",
            "3",
            *extra_args,
        ]
        exit_code, semgrep_output = invoke_semgrep(
            args, [str(p) for p in paths], timeout=context.timeout
        )
        findings = FindingSets(
            exit_code,
            searched_paths=set(targets.searched_paths),
            errors=semgrep_output.errors,
        )

        stats = RunStats(
            rule_list=semgrep_output.timing.rules,
            target_data=semgrep_output.timing.targets,
        )

        findings.current.update_findings(
            Finding.from_semgrep_result(result, context.committed_datetime)
            for result in semgrep_output.results
            if not result["extra"].get("is_ignored")
        )
        findings.ignored.update_findings(
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
        for finding in findings.current:
            if finding.is_cai_finding():
                inventory_findings_len += 1
        click.echo(
            f"| {unit_len(range(len(findings.current) - inventory_findings_len), 'current issue')} found",
            err=True,
        )
        click.echo(
            f"| {unit_len(findings.ignored, 'issue')} muted with nosemgrep comment",
            err=True,
        )
    return findings, stats


def _update_baseline_findings(
    context: RunContext,
    findings: FindingSets,
    local_configs: Set[str],
    extra_args: Sequence[str],
    targets: TargetFileManager,
) -> None:
    """
    Updates findings.baseline with findings from the baseline git commit

    :param context: Semgrep run context
    :param findings: Findings structure from running on the head git commit
    :param local_configs: Any local semgrep.yml configs
    :param extra_args: Extra Semgrep arguments
    :param targets: File targets from head commit
    """
    if not findings.current and not findings.ignored:
        click.echo(
            "=== not looking at pre-existing issues since there are no current issues",
            err=True,
        )
    else:
        with targets.baseline_paths() as paths:
            paths_with_findings = {
                finding.path for finding in findings.current.union(findings.ignored)
            }
            paths_to_check = list(
                set(str(path) for path in paths) & paths_with_findings
            )
            if not paths_to_check:
                click.echo(
                    "=== not looking at pre-existing issues since all files with current issues are newly created",
                    err=True,
                )
            else:
                config_args = []
                for conf in context.config_specifier:
                    # If a local config existed with initial scan but doesn't exist
                    # in baseline, treat as if no issues found in baseline with that config
                    if conf in local_configs and not Path(conf).exists():
                        click.echo(
                            f"=== {conf} file not found in baseline, skipping scanning for baseline",
                            err=True,
                        )
                        continue
                    config_args.extend(["--config", conf])

                if not config_args:
                    click.echo(
                        "=== not looking at pre-exiting issues since after filtering out local files that don't exist in baseline, no configs left to run",
                        err=True,
                    )
                else:
                    click.echo(
                        "=== looking for pre-existing issues in "
                        + unit_len(paths_to_check, "file"),
                        err=True,
                    )

                    args = [
                        "--skip-unknown-extensions",
                        "--disable-nosem",
                        "--json",
                        *extra_args,
                        *config_args,
                    ]

                    # If possible, disable metrics so that we get metrics only once per semgrep-action run
                    # However, if run with config auto we must allow metrics to be sent
                    if "auto" not in config_args:
                        args.extend(["--metrics", "off"])

                    _, semgrep_output = invoke_semgrep(
                        args, paths_to_check, timeout=context.timeout
                    )
                    findings.baseline.update_findings(
                        Finding.from_semgrep_result(result, context.committed_datetime)
                        for result in semgrep_output.results
                    )
                    inventory_findings_len = 0
                    for finding in findings.baseline:
                        if finding.is_cai_finding():
                            inventory_findings_len += 1
                    click.echo(
                        f"| {unit_len(range(len(findings.baseline) - inventory_findings_len), 'pre-existing issue')} found",
                        err=True,
                    )


@attr.s(auto_attribs=True)
class SemgrepTiming:
    rules: Sequence[Mapping[str, str]]
    targets: Sequence[Mapping[str, Any]]


@attr.s(auto_attribs=True)
class SemgrepOutput:
    results: Sequence[Any]
    errors: Sequence[Any]
    timing: SemgrepTiming


def invoke_semgrep(
    semgrep_args: List[str], targets: List[str], *, timeout: Optional[int]
) -> Tuple[int, SemgrepOutput]:
    """
    Call semgrep passing in semgrep_args + targets as the arguments

    Returns json output of semgrep as dict object
    """
    max_exit_code = 0
    output = SemgrepOutput([], [], SemgrepTiming([], []))

    for chunk in chunked_iter(targets, PATHS_CHUNK_SIZE):
        with open(SEMGREP_SAVE_FILE, "w+") as output_json_file:
            args = semgrep_args.copy()
            args.extend(["--debug"])
            args.extend(
                [
                    "-o",
                    output_json_file.name,
                ]
            )
            for c in chunk:
                args.append(c)

            debug_echo(f"== Invoking semgrep with { len(args) } args")

            exit_code = semgrep_exec(*args, _timeout=timeout, _err=debug_echo).exit_code
            max_exit_code = max(max_exit_code, exit_code)

            debug_echo(f"== Semgrep finished with exit code { exit_code }")

            with open(output_json_file.name) as f:
                parsed_output = json.load(f)

            output.results = [*output.results, *parsed_output["results"]]
            output.errors = [*output.errors, *parsed_output["errors"]]
            parsed_timing = parsed_output.get("time", {})
            output.timing = SemgrepTiming(
                parsed_timing.get("rules", output.timing.rules),
                [*output.timing.targets, *parsed_timing.get("targets", [])],
            )

    return max_exit_code, output


def invoke_semgrep_sarif(
    semgrep_args: List[str], targets: List[str], *, timeout: Optional[int]
) -> Tuple[int, Dict[str, List[Any]]]:
    """
    Call semgrep passing in semgrep_args + targets as the arguments

    Returns sarif output of semgrep as dict object
    """
    output: Dict[str, List[Any]] = {}

    max_exit_code = 0

    for chunk in chunked_iter(targets, PATHS_CHUNK_SIZE):
        with tempfile.NamedTemporaryFile("w") as output_json_file:
            args = semgrep_args.copy()
            args.extend(["--debug", "--sarif"])
            args.extend(
                [
                    "-o",
                    output_json_file.name,  # nosem: python.lang.correctness.tempfile.flush.tempfile-without-flush
                ]
            )
            for c in chunk:
                args.append(c)

            exit_code = semgrep_exec(*args, _timeout=timeout, _err=debug_echo).exit_code
            max_exit_code = max(max_exit_code, exit_code)

            with open(
                output_json_file.name  # nosem: python.lang.correctness.tempfile.flush.tempfile-without-flush
            ) as f:
                parsed_output = json.load(f)

            if len(output) == 0:
                output = parsed_output
            else:
                output["runs"][0]["results"].extend(parsed_output["runs"][0]["results"])
                output["runs"][0]["tool"]["driver"]["rules"].extend(
                    parsed_output["runs"][0]["tool"]["driver"]["rules"]
                )

    return max_exit_code, output


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
