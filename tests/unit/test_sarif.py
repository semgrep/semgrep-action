import json
from pathlib import Path
from typing import Any
from typing import Dict

import pytest
from jsonschema import validate

from semgrep_agent.semgrep import rewrite_sarif_file


@pytest.fixture
def sarif_schema():
    with (Path(__file__).parent / "sarif-schema-2.1.0.json").open() as fd:
        schema = json.load(fd)
    return schema


def test_rewrite_empty_sarif_file(tmp_path: Path, sarif_schema):
    sarif_output: Dict[str, Any] = {}
    sarif_path = tmp_path / "semgrep.sarif"

    rewrite_sarif_file(sarif_output, sarif_path)

    with sarif_path.open() as fd:
        data = json.load(fd)

    validate(instance=data, schema=sarif_schema)
