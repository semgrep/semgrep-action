import itertools
import psutil
import shutil
import sys
import textwrap
from typing import Collection
from typing import Iterable
from typing import List
from typing import Optional, Pattern
from typing import Set
from typing import TextIO
import re
import click
from click.termui import secho, style
from semgrep_agent.semgrep_app import Sapp
from semgrep_agent.meta import GitMeta

class Colors:
    LINK = "bright_blue"
    ERROR = "red"
    WARNING = "yellow"
    SUCCESS = "green"

from semgrep_agent.findings import Finding

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


OSC_8 = "\x1b]8;;"
BEL = "\x07"


def is_child_process_of(pattern: Pattern) -> bool:
    """
    Returns true iff this process is a child process of a process whose name matches pattern
    """
    me = psutil.Process()
    parents = me.parents()
    matches = iter(0 for p in parents if pattern.search(p.name()))
    return next(matches, None) is not None


LINK_PRINTER_PATTERN = re.compile("(iterm2|gnome-terminal)", re.IGNORECASE)
LINK_WIDTH = 2 * len(OSC_8) + 2 * len(BEL)
DO_PRINT_LINKS = is_child_process_of(LINK_PRINTER_PATTERN)


def render_link(
    text: str,
    href: Optional[str],
    print_alternative: bool = True,
    width: Optional[int] = None,
    pipe: TextIO = sys.stdout,
) -> str:
    """
    Prints a clickable hyperlink output if in a tty; otherwise just prints a text link
    :param text: The link anchor text
    :param href: The href, if exists
    :param print_alternative: If true, only emits link if OSC8 links are supported, otherwise prints href after text
    :param width: Minimum link width
    :param pipe: The text IO via which this link will be emitted
    :return: The rendered link
    """
    is_rendered = False
    if href:  # Don't render if href is None or empty
        if pipe.isatty() and DO_PRINT_LINKS:
            text = f"{OSC_8}{href}{BEL}{text}{OSC_8}{BEL}"
            is_rendered = True
            if width:
                width += LINK_WIDTH + len(href)
        elif print_alternative:
            text = f"{text} {href}"

    if width:
        text = text.ljust(width)

    # Coloring has to occur after justification
    if is_rendered:
        text = style(text, fg=Colors.LINK)

    return text


def build_action_url(v: Finding, c: Sapp, meta: GitMeta):
    projectName = meta.repo_remote_origin
    return f'http://localhost:3000/finding/{c.deployment_id}/{v.from_policy_id}?ruleId={v.check_id}&path={v.path}&lineNum={v.line}&rulesetName={v.from_ruleset_id}&projectName={projectName}'

def dump(findings: Set[Finding], config: Sapp, meta: GitMeta) -> None:
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
            target_url = build_action_url(v, config, meta)
            target_text = '(more info)'

            hyperlink = render_link(target_text, target_url)
            lines.append(_print_error_message(v) + ' ' + hyperlink)
            lines.append(_print_path(path, v.line, v.column))

            lines += _print_violation(v, max_message_len)
            lines.append("")

    for line in lines:
        click.secho(line)
