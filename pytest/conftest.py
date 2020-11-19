import pytest
import json
import subprocess

from pathlib import Path
from typing import List
from typing import Optional
from typing import Union

TESTS_PATH = Path(__file__).parent
MASKED_KEYS = [
    "tool.driver.semanticVersion",
    "results.extra.metavars.*.unique_id.md5sum",
]


def mark_masked(obj, path):
    _mark_masked(obj, path.split("."))


def _mark_masked(obj, path_items):
    key = path_items[0]
    if len(path_items) == 1 and key in obj:
        obj[key] = "<masked in tests>"
    else:
        if key == "*":
            next_obj = list(obj.values())
        else:
            next_obj = obj.get(key)
        if next_obj is None:
            next_objs = []
        elif not isinstance(next_obj, list):
            next_objs = [next_obj]
        else:
            next_objs = next_obj
        for o in next_objs:
            _mark_masked(o, path_items[1:])


def _clean_output_json(output_json: str) -> str:
    """Make semgrep's output deterministic and nicer to read."""
    output = json.loads(output_json)
    for path in MASKED_KEYS:
        mark_masked(output, path)

    return json.dumps(output, indent=2, sort_keys=True)


def _run_semgrep_agent(
    config: Optional[Union[str, Path, List[str]]] = None,
    *,
    target_name: str = "basic",
    options: Optional[List[Union[str, Path]]] = None,
    output_format: str = "json",
    stderr: bool = False,
    strict: bool = True,
):
    if options is None:
        options = []

    if config is not None:
        if isinstance(config, list):
            for conf in config:
                options.extend(["--config", conf])
        else:
            options.extend(["--config", config])

    if output_format == "gitlab":
        options.append("--gitlab")

    process = subprocess.Popen(
        ["python3", "-m", "semgrep_agent", *options],
        encoding="utf-8",
        stderr=subprocess.STDOUT if stderr else subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    process.wait()
    output,error = process.communicate()

    if output_format in {"json", "gitlab"} and not stderr:
        output = _clean_output_json(output)

    return output


@pytest.fixture
def run_semgrep_agent():
    yield _run_semgrep_agent

@pytest.fixture
def get_test_root():
    yield Path(TESTS_PATH).resolve()