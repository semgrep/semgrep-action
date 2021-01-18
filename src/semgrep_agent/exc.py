class ActionFailure(Exception):
    """
    Indicates that Semgrep failed and should abort, but prevents a stack trace
    """

    def __init__(self, message: str) -> None:
        self.message = message
