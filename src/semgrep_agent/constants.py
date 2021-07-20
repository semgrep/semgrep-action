import re


SUPPORT_EMAIL = "support@r2c.dev"

PRIVACY_SENSITIVE_FIELDS = {"syntactic_context", "fixed_lines"}

PUBLISH_TOKEN_VALIDATOR = re.compile(r"\w{64,}")

ERROR_EXIT_CODE = 2
FINDING_EXIT_CODE = 1
NO_RESULT_EXIT_CODE = 0
