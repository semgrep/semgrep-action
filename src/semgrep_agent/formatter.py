import itertools
import shutil
import sys
import textwrap
from typing import Collection
from typing import Iterable
from typing import List
from typing import Optional
from typing import Set
from typing import TextIO

import click

from .findings import Finding

PRINT_WIDTH = 80
BOLD = "\033[1m"
END = "\033[0m"

PIPE = click.style("│", dim=True)
CONTEXT_HEADER = f"     {click.style('╷', dim=True)}"
CONTEXT_FOOTER = f"     {click.style('╵', dim=True)}"
NOTE_LEADER = f"     = "
LEADER_LEN = len(NOTE_LEADER)
MESSAGE_OVERFLOW_LEADER = "".ljust(len(NOTE_LEADER), " ")
MIN_MESSAGE_LEN = 40


def path_of(violation: Finding) -> str:
    return violation.path


def by_path(findings: Iterable[Finding]) -> Iterable[Finding]:
    return sorted(findings, key=(lambda v: v.path))


def _print_path(path: str, line: int, col: int) -> str:
    fpos = click.style(f"{path}:{line}")
    return f"     > {fpos}"


def _print_violation(violation: Finding, max_message_len: int) -> List[str]:
    message_lines = textwrap.wrap(violation.message.strip(), width=max_message_len)

    out = []

    # Strip so trailing newlines are not printed out
    stripped = violation.syntactic_context.rstrip()
    context = [line.rstrip() for line in stripped.split("\n")]

    if stripped:
        out.append(CONTEXT_HEADER)
        for offset, line in enumerate(context):
            line_no = click.style(f"{violation.line + offset:>4d}", dim=True)
            out.append(f" {line_no}{PIPE}   {line}")
        out.append(CONTEXT_FOOTER)

    out.append(f"{NOTE_LEADER}{click.style(message_lines[0], dim=True)}")
    for mline in message_lines[1:]:
        out.append(f"{MESSAGE_OVERFLOW_LEADER}{click.style(mline, dim=True)}")

    return out


def _print_error_message(violation: Finding) -> str:
    rule = f"{violation.check_id}".strip()

    return f"{BOLD}{rule}{END}"


def dump(findings: Set[Finding]) -> None:
    if not findings:
        return

    lines = []
    violations = by_path(findings)
    max_message_len = min(
        max((len(v.message) for v in violations), default=0), PRINT_WIDTH - LEADER_LEN,
    )

    if sys.stdout.isatty():
        terminal_width, _ = shutil.get_terminal_size((PRINT_WIDTH, 0))
        max_message_len = max(
            min(max_message_len, terminal_width - LEADER_LEN), MIN_MESSAGE_LEN,
        )

    ordered: List[Finding] = sorted(violations, key=path_of)

    for path, vv in itertools.groupby(ordered, path_of):
        for v in sorted(vv, key=lambda v: (v.line, v.column, v.message)):
            lines.append(_print_error_message(v))
            lines.append(_print_path(path, v.line, v.column))

            lines += _print_violation(v, max_message_len)
            lines.append("")

    for line in lines:
        click.secho(line)
