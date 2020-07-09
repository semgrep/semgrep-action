import os
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import NoReturn
from typing import Optional

import click
import sh
from boltons import ecoutils

from . import formatter
from . import semgrep
from .meta import detect_meta_environment
from .meta import GitMeta
from .semgrep_app import Sapp
from .utils import maybe_print_debug_info


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
    "--baseline-ref",
    envvar="BASELINE_REF",
    type=str,
    default=None,
    show_default="detected from CI env",
)
@click.option(
    "--publish-url", envvar="INPUT_PUBLISHURL", type=url, default="https://semgrep.live"
)
@click.option("--publish-token", envvar="INPUT_PUBLISHTOKEN", type=str)
@click.option("--publish-deployment", envvar="INPUT_PUBLISHDEPLOYMENT", type=int)
@click.pass_context
def main(
    ctx: click.Context,
    config: str,
    baseline_ref: str,
    publish_url: str,
    publish_token: str,
    publish_deployment: int,
) -> NoReturn:
    click.echo(
        f"== agent's environment: "
        f"semgrep/{sh.semgrep(version=True).strip()}, "
        f"{sh.python(version=True).strip()}"
    )

    Meta = detect_meta_environment()
    meta_kwargs = {}
    if baseline_ref:
        meta_kwargs["cli_baseline_ref"] = baseline_ref

    obj = ctx.obj = CliObj(
        event_type=get_event_type(),
        config=config,
        meta=Meta(ctx, **meta_kwargs),
        sapp=Sapp(
            ctx=ctx,
            url=publish_url,
            token=publish_token,
            deployment_id=publish_deployment,
        ),
    )

    maybe_print_debug_info(obj.meta)

    obj.sapp.report_start()

    if not (obj.config or obj.sapp.is_configured or Path(".semgrep.yml").is_file()):
        message = """
            == [ERROR] you didn't configure what rules semgrep should scan for.

            Please either set a config in the CI configuration according to
            https://github.com/returntocorp/semgrep-action#configuration
            or commit your own rules at the default path of `.semgrep.yml`
        """
        message = dedent(message).strip()
        click.echo(message, err=True)
        sys.exit(1)

    results = semgrep.scan(ctx)

    formatter.dump(results.findings.new)
    obj.sapp.report_results(results)

    sys.exit(1 if results.findings.new else 0)
