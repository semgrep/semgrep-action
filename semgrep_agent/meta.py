import json
import os
from pathlib import Path

from boltons.cacheutils import cachedproperty
import click
from glom import glom
import git
import sh

from dataclasses import dataclass


@dataclass
class Meta:
    ctx: click.Context

    def glom_event(self, spec):
        return glom(self.event, spec, default=None)

    @cachedproperty
    def event(self):
        if value := os.getenv("GITHUB_EVENT_PATH"):
            return json.loads(Path(value).read_text())

    @cachedproperty
    def repo(self):
        return git.Repo()

    @cachedproperty
    def repo_name(self):
        if value := os.getenv("GITHUB_REPOSITORY"):
            return value

    @cachedproperty
    def repo_url(self):
        if self.repo_name:
            return f"https://github.com/{self.repo_name}"

    @cachedproperty
    def commit_sha(self):
        if value := os.getenv("GITHUB_SHA"):
            return value
        return self.repo.head.commit.hexsha

    @cachedproperty
    def commit(self) -> git.Commit:
        return self.repo.commit(self.commit_sha)

    @cachedproperty
    def commit_ref(self):
        if value := os.getenv("GITHUB_REF"):
            return value

    @cachedproperty
    def ci_actor(self):
        if value := os.getenv("GITHUB_ACTOR"):
            return value

    @cachedproperty
    def ci_url(self):
        if self.repo_url and (value := os.getenv("GITHUB_RUN_ID")):
            return f"{self.repo_url}/actions/runs/{value}"

    @cachedproperty
    def ci_event_name(self):
        if value := os.getenv("GITHUB_EVENT_NAME"):
            return value

    def to_dict(self):
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
