import os
import pty
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Tuple

import yaml
from _pytest.python import Metafunc

ALL_TESTS = [
    d.name
    for d in Path(__file__).parent.resolve().iterdir()
    if d.is_dir() and (d / "commands.yaml").exists()
]

REPO_ROOT = str(Path(__file__).parent.parent.parent.resolve())

BRANCH_COMMIT = re.compile(r"^(commit|\s+?\*) ([0-9a-f]+)", re.MULTILINE)
DATE_STR = re.compile(r"^Date:   (.*)$", re.MULTILINE)
BRANCH_MERGE = re.compile(r"^Merge: (.*)$", re.MULTILINE)
ENV_VERSIONS = re.compile(
    r"^(\s+?versions\s+?- semgrep ).+?( on python ).+?$", re.MULTILINE
)
JSON_VERSION = re.compile(r'"version": "[0-9]+?[.][0-9]+?[.][0-9]+?"')
START_TIME = re.compile(r'"start_time": "\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"')
END_TIME = re.compile(r'"end_time": "\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"')
GITHUB_ACTIONS_DEBUG = re.compile(r"^::debug::.*?\n", re.MULTILINE)
NEW_VERSION_AVAILABLE = re.compile(
    r"\nA new version of Semgrep is available.*\n", re.MULTILINE
)

PIPE_OUTPUT: Mapping[str, Callable[[subprocess.CompletedProcess], str]] = {
    "expected_out": lambda r: cast(str, r.stdout),
    "expected_err": lambda r: cast(str, r.stderr),
}
SYMLINK_SKIP_MSG = re.compile(
    r"Skipping .*bar/foo since it is a symlink to a directory: .*foo", re.MULTILINE
)


def write_expected_file(filename: str, output: str) -> None:
    with open(filename, "w") as file:
        file.write(clean_output(output))


CLEANING_FUNCS: Sequence[Callable[[str], str]] = [
    lambda s: "\n".join(line.rstrip() for line in s.splitlines()) + "\n",
    lambda s: re.sub(BRANCH_COMMIT, r"\1 aaaaaaa", s),
    lambda s: re.sub(DATE_STR, r"Date:   YYYY-MM-DD", s),
    lambda s: re.sub(BRANCH_MERGE, r"Merge: aaaaaaa bbbbbbb", s),
    lambda s: re.sub(ENV_VERSIONS, r"\1x.y.z\2x.y.z", s),
    lambda s: re.sub(JSON_VERSION, r'"version": "x.y.z"', s),
    lambda s: re.sub(START_TIME, r'"start_time": "YYYY-MM-DD-THH:MM:SS"', s),
    lambda s: re.sub(END_TIME, r'"end_time": "YYYY-MM-DD-THH:MM:SS"', s),
    lambda s: re.sub(GITHUB_ACTIONS_DEBUG, "", s),
    lambda s: re.sub(NEW_VERSION_AVAILABLE, "", s),
    lambda s: re.sub(
        SYMLINK_SKIP_MSG,
        "Skipping bar/foo since it is a symlink to a directory: foo",
        s,
    ),
]


def clean_output(output: str) -> str:
    for clean in CLEANING_FUNCS:
        output = clean(output)
    return output


def show_first_differing_line(a: str, b: str) -> Tuple[int, str, str]:
    """Return line number and line contents where the strings start to differ.

    The line number is zero-based.
    """
    alines = a.split("\n")
    blines = b.split("\n")
    alen = len(alines)
    blen = len(blines)
    min_len = min(alen, blen)
    for i in range(min_len):
        if alines[i] != blines[i]:
            return (i, alines[i], blines[i])
    aline = alines[min_len] if alen > min_len else ""
    bline = blines[min_len] if blen > min_len else ""
    return (min_len, aline, bline)


def match_expected(output: str, expected_raw: str) -> bool:
    """Checks that OUTPUT matches EXPECTED

    Checks that OUTPUT and EXPECTED are exact
    matches ignoring trailing whitespace

    """
    output = clean_output(output)

    actual = output.strip()
    expected = expected_raw.strip()
    if actual != expected:
        print("==== EXPECTED ====")
        print(expected)
        print("==== ACTUAL ====")
        print(output)
        pos, expected_line, actual_line = show_first_differing_line(expected, actual)
        print(
            f"=============================================================\n"
            f"Expected and actual output differ on line {pos+1}:\n"
            f"expected: {expected_line}\n"
            f"actual  : {actual_line}\n"
        )
    return output.strip() == expected.strip()


def check_command(step: Any, pwd: str, target: str, rewrite: bool) -> None:
    """Runs COMMAND in with cwd=PWD and checks that the returncode, stdout, and stderr
    match their respective expected values.

    If rewrite is True, overwrites expected files with output of running step, skipping
    output match verification
    """
    command = step["command"]
    if isinstance(command, str):
        command = command.split(" ")

    test_identifier = f"Target:{target} Step:{step['name']}"
    env = os.environ.copy()
    substituted = [part.replace("__REPO_ROOT__", REPO_ROOT) for part in command]

    print(f"======= {test_identifier} ========")

    # In order to test behavior with a stdin, we create a pseudoterminal for the command here.
    # To test behavior _without_ a stdin, set the "command" as:
    # command:
    #   - bash
    #   - -c
    #   - ": | <command>"
    master_fd, slave_fd = pty.openpty()

    runned = subprocess.run(
        substituted,
        cwd=pwd,
        env=env,
        stdin=slave_fd,
        capture_output=True,
        encoding="utf-8",
    )

    print("Command return code:", runned.returncode)

    if "returncode" in step:
        expected_returncode = step["returncode"]
        if runned.returncode != expected_returncode:
            print(f"Run stdout: {runned.stdout}")
            print(f"Run stderr: {runned.stderr}")
        assert runned.returncode == expected_returncode, test_identifier

    for pipe in ["expected_out", "expected_err"]:
        if pipe in step:
            expectation_file = step.get(pipe)
            if rewrite and expectation_file is not None:
                write_expected_file(
                    f"tests/acceptance/{target}/{expectation_file}",
                    PIPE_OUTPUT[pipe](runned),
                )
            else:
                if expectation_file is None:
                    expectation = ""
                else:
                    with open(f"tests/acceptance/{target}/{expectation_file}") as file:
                        expectation = file.read()

                assert match_expected(
                    PIPE_OUTPUT[pipe](runned), expectation
                ), f"{test_identifier}: {pipe}"


def expand_include(step: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    include = step["include"]
    with open(f"tests/acceptance/{include}") as file:
        return cast(Sequence[Mapping[str, Any]], yaml.safe_load(file))


def run_repo(
    target: str, pre: Optional[Callable[[Path], None]] = None, rewrite: bool = False
) -> None:
    """
    Runs commands for a repository definition file.

    :param target: Subdirectory where the repository's commands are stored
    :param pre: A setup function to run after the repository is checked out, but prior to running commands
    """
    with open(f"tests/acceptance/{target}/commands.yaml") as file:
        info = yaml.safe_load(file)

    target_repo = info.get("target_repo")
    target_hash = info.get("target_hash")
    steps = info["steps"]
    steps = [i for s in steps for i in (expand_include(s) if "include" in s else [s])]

    with tempfile.TemporaryDirectory() as target_dir:

        if target_repo:
            subprocess.run(
                ["git", "clone", target_repo, target_dir],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "checkout", target_hash],
                cwd=target_dir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "clean", "-xdf"],
                cwd=target_dir,
                capture_output=True,
                check=True,
            )

        if pre:
            pre(Path(target_dir))

        for step in steps:
            check_command(step, target_dir, target, rewrite)


def pytest_generate_tests(metafunc: Metafunc) -> None:
    metafunc.parametrize("repo", ALL_TESTS)


def test_repo(repo: str) -> None:
    run_repo(repo)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        to_run = sys.argv[1:]
    else:
        to_run = ALL_TESTS

    for t in to_run:
        run_repo(t, rewrite=True)
