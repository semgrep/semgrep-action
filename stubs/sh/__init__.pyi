from typing import Any, Callable, Union

class ErrorReturnCode(Exception):
    @property
    def full_cmd(self) -> str: ...
    @property
    def exit_code(self) -> int: ...

class BentoSubcommandsMixin:

    # bento subcommands
    @property
    def init(self) -> Command: ...
    @property
    def check(self) -> Command: ...

class GitSubcommandsMixin:

    # git subcommands
    @property
    def checkout(self) -> Command: ...
    @property
    def fetch(self) -> Command: ...
    @property
    def status(self) -> Command: ...

class Command(BentoSubcommandsMixin, GitSubcommandsMixin):
    def __call__(self, *args: Any, **kwargs: Any) -> RunningCommand: ...
    def bake(self, *args: Any, **kwargs: Any) -> Command: ...

class RunningCommand(str, BentoSubcommandsMixin, GitSubcommandsMixin):
    @property
    def stdout(self) -> bytes: ...
    @property
    def stderr(self) -> bytes: ...
    @property
    def exit_code(self) -> int: ...

bento: Command
semgrep: Command
python: Command
