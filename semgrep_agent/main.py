import os
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import NoReturn

import click
import sh

from . import bento
from . import semgrep
from .meta import detect_meta_environment
from .meta import GitMeta
from .semgrep_app import Sapp


def url(string: str) -> str:
    return string.rstrip("/")


@dataclass
class CliObj:
    event_type: str
    config: str
    meta: GitMeta
    sapp: Sapp


def get_event_type() -> str:
    if "GITHUB_ACTIONS" in os.environ:
        return os.environ["GITHUB_EVENT_NAME"]

    return "push"


@click.command()
@click.option("--config", envvar="INPUT_CONFIG", type=str)
@click.option(
    "--publish-url", envvar="INPUT_PUBLISHURL", type=url, default="https://semgrep.live"
)
@click.option("--publish-token", envvar="INPUT_PUBLISHTOKEN", type=str)
@click.option("--publish-deployment", envvar="INPUT_PUBLISHDEPLOYMENT", type=int)
@click.pass_context
def main(
    ctx: click.Context,
    config: str,
    publish_url: str,
    publish_token: str,
    publish_deployment: int,
) -> NoReturn:
    click.echo(
        f"== action's environment: semgrep/{sh.semgrep(version=True).strip()}, {sh.bento(version=True).strip()}, {sh.python(version=True).strip()}"
    )

    Meta = detect_meta_environment()

    obj = ctx.obj = CliObj(
        event_type=get_event_type(),
        config=config,
        meta=Meta(ctx=ctx),
        sapp=Sapp(
            ctx=ctx,
            url=publish_url,
            token=publish_token,
            deployment_id=publish_deployment,
        ),
    )

    obj.sapp.report_start()

    if not config and not (Path(".bento") / "semgrep.yml").is_file():
        if obj.sapp.is_configured:
            obj.sapp.download_rules()
        else:
            message = """
                == [WARNING] you didn't configure what rules semgrep should scan for.

                Please either set a config in the action's configuration according to
                https://github.com/returntocorp/semgrep-action#configuration
                or commit your own rules at the default path of .bento/semgrep.yml
            """
            message = dedent(message).strip()
            click.echo(message, err=True)

    results = bento.scan(ctx)
    semgrep.scan_into_sarif(ctx)

    obj.sapp.report_results(results)

    sys.exit(results.exit_code)
