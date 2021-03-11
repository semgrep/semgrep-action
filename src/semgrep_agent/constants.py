import re


SUPPORT_EMAIL = "support@r2c.dev"

PRIVACY_SENSITIVE_FIELDS = {"syntactic_context", "fixed_lines"}

PUBLISH_TOKEN_VALIDATOR = re.compile(r"\w{64,}")
