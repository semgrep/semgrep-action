import json
from pathlib import Path
from jsonschema import validate

def test_gitlab_output(run_semgrep_agent,get_test_root):
    gitlab_output = run_semgrep_agent(config=str(Path(get_test_root / "rules/eqeq.yaml")), output_format="gitlab")
    schema_path = str(Path(get_test_root/ "resources" / "gitlab_schema.json").resolve())
    with open(schema_path) as f:
        gitlab_schema = json.load(f)
        validate(gitlab_output,schema=gitlab_schema)