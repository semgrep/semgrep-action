import os
from pathlib import Path

from bento.target_file_manager import TargetFileManager
import click
import sh


def scan_into_sarif(ctx: click.Context):
    if not os.getenv("INPUT_GENERATESARIF"):
        return

    if ctx.obj.config:
        config = f"https://sgrep.live/c/{ctx.obj.config}"
    elif (Path(".bento") / "semgrep.yml").is_file():
        config = ".bento/semgrep.yml"
    else:
        return

    paths = [Path(".")]
    if Path(".bentoignore").is_file():
        targets = TargetFileManager(
            base_path=Path(".").resolve(),
            paths=[Path(".").resolve()],
            staged=False,
            ignore_rules_file_path=Path(".bentoignore"),
        )
        paths = targets._target_paths

    sarif_path = Path(os.environ["GITHUB_WORKSPACE"]) / "semgrep.sarif"
    with sarif_path.open("w") as sarif_file:
        sh.semgrep(*paths, config=config, sarif=True, _out=sarif_file)
