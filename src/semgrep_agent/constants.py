import re


SUPPORT_EMAIL = "support@r2c.dev"

PRIVACY_SENSITIVE_FIELDS = {"syntactic_context"}

PUBLISH_TOKEN_VALIDATOR = re.compile(r"\w{64,}")
