import json
from pathlib import Path

from jsonschema import validate


def test_gitlab_secret_output(run_semgrep_agent, get_test_root):
    gitlab_secrets_output = run_semgrep_agent(
        config="assets/rules/eqeq.yaml", output_format="gitlab-secrets"
    )
    schema_path = str(
        Path(get_test_root / "assets/resources/gitlab_secrets_schema.json").resolve()
    )
    with open(schema_path) as f:
        gitlab_secrets_schema = json.load(f)
        validate(gitlab_secrets_output, schema=gitlab_secrets_schema)
