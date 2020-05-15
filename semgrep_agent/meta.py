import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union

import click
import git
import sh
from boltons.cacheutils import cachedproperty
from glom import glom

from .utils import debug_echo


@dataclass
class Meta:
    ctx: click.Context

    def glom_event(self, spec: str) -> Optional[str]:
        return glom(self.event, spec, default=None)

    @cachedproperty
    def event(self) -> Optional[Dict[str, Any]]:
        if value := os.getenv("GITHUB_EVENT_PATH"):
            debug_echo(f"found github event data at {value}")
            return json.loads(Path(value).read_text())  # type: ignore
        return None

    @cachedproperty
    def repo(self) -> git.Repo:  # type: ignore
        repo = git.Repo()
        debug_echo(f"found repo: {repo!r}")
        return repo

    @cachedproperty
    def repo_name(self) -> Optional[str]:
        if value := os.getenv("GITHUB_REPOSITORY"):
            return value
        return None

    @cachedproperty
    def repo_url(self) -> Optional[str]:
        if self.repo_name:
            return f"https://github.com/{self.repo_name}"
        return None

    @cachedproperty
    def commit_sha(self) -> Optional[str]:
        if value := os.getenv("GITHUB_SHA"):
            return value
        return self.repo.head.commit.hexsha  # type: ignore

    @cachedproperty
    def commit(self) -> git.Commit:  # type: ignore
        commit = self.repo.commit(self.commit_sha)
        debug_echo(f"found commit: {commit!r}")
        return commit

    @cachedproperty
    def commit_ref(self) -> Optional[str]:
        if value := os.getenv("GITHUB_REF"):
            return value
        return None

    @cachedproperty
    def ci_actor(self) -> Optional[str]:
        if value := os.getenv("GITHUB_ACTOR"):
            return value
        return None

    @cachedproperty
    def ci_url(self) -> Optional[str]:
        if self.repo_url and (value := os.getenv("GITHUB_RUN_ID")):
            return f"{self.repo_url}/actions/runs/{value}"
        return None

    @cachedproperty
    def ci_event_name(self) -> Optional[str]:
        if value := os.getenv("GITHUB_EVENT_NAME"):
            return value
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repository": self.repo_name,
            "commit": self.commit_sha,
            "commit_committer_email": git.Repo().head.commit.committer.email,
            "commit_timestamp": self.commit.committed_datetime.isoformat(),
            "commit_author_email": git.Repo().head.commit.author.email,
            "commit_authored_timestamp": self.commit.authored_datetime.isoformat(),
            "commit_title": self.commit.summary,
            "config": self.ctx.obj.config,
            "on": self.ci_event_name,
            "branch": self.commit_ref,
            "pull_request_timestamp": self.glom_event("pull_request.created_at"),
            "pull_request_author_name": self.glom_event("pull_request.user.name"),
            "pull_request_id": self.glom_event("pull_request.number"),
            "pull_request_title": self.glom_event("pull_request.title"),
            "semgrep_version": sh.semgrep(version=True).strip(),
            "bento_version": sh.bento(version=True).strip(),
            "python_version": sh.python(version=True).strip(),
        }
