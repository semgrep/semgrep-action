import os
import re


SUPPORT_EMAIL = "support@r2c.dev"

PRIVACY_SENSITIVE_FIELDS = {"syntactic_context", "fixed_lines"}

PUBLISH_TOKEN_VALIDATOR = re.compile(r"\w{64,}")

GIT_SH_TIMEOUT = 500

ERROR_EXIT_CODE = 2
FINDING_EXIT_CODE = 1
NO_RESULT_EXIT_CODE = 0

# Scans that take longer than LONG_RUNNING_SECONDS will emit a service report
LONG_RUNNING_SECONDS = float(os.environ.get("SEMGREP_LONG_RUNNING_SECONDS", "300.0"))
