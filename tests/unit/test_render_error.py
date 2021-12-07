import json

from semgrep_agent.utils import render_error

SEMGREP_OUT = """
{
  "errors": [
    {
      "code": 3,
      "level": "warn",
      "message": "Semgrep Core WARN - Syntax error: When running javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret on frontend/src/r2components/table/DataTable.tsx: `}: DataTableProps<` was unexpected",
      "path": "frontend/src/r2components/table/DataTable.tsx",
      "rule_id": "javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret",
      "type": "Syntax error"
    },
    {
      "code": 3,
      "level": "warn",
      "message": "Semgrep Core WARN - Syntax error: When running javascript.lang.correctness.useless-eqeq.eqeq-is-bad on frontend/src/r2components/table/DataTable.tsx: `}: DataTableProps<` was unexpected",
      "path": "frontend/src/r2components/table/DataTable.tsx",
      "rule_id": "javascript.lang.correctness.useless-eqeq.eqeq-is-bad",
      "type": "Syntax error"
    },
    {
      "code": 3,
      "level": "warn",
      "message": "Semgrep Core WARN - Syntax error: When running typescript.react.security.react-markdown-insecure-html.react-markdown-insecure-html on frontend/src/r2components/table/DataTable.tsx: `}: DataTableProps<` was unexpected",
      "path": "frontend/src/r2components/table/DataTable.tsx",
      "rule_id": "typescript.react.security.react-markdown-insecure-html.react-markdown-insecure-html",
      "type": "Syntax error"
    }
  ],
  "results": []
}
"""

RENDERED_ERROR = [
    "Semgrep Core WARN - Syntax error: When running javascript.lang.correctness.useless-eqeq.eqeq-is-bad on frontend/src/r2components/table/DataTable.tsx: `}: DataTableProps<` was unexpected"
]


def test_render_error():
    data = json.loads(SEMGREP_OUT)

    assert render_error(data["errors"][1]) == RENDERED_ERROR
