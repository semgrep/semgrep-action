import os

import click
import git

from dataclasses import dataclass


@dataclass
class Meta:
    ctx: click.Context

    @property
    def repo(self):
        return git.Repo()

    @property
    def repo_name(self):
        if value := os.getenv("GITHUB_REPOSITORY"):
            return value

    @property
    def repo_url(self):
        if self.repo_name:
            return f"https://github.com/{self.repo_name}"

    @property
    def commit_sha(self):
        if value := os.getenv("GITHUB_SHA"):
            return value
        return self.repo.head.commit.hexsha

    @property
    def commit(self) -> git.Commit:
        return self.repo.commit(self.commit_sha)

    @property
    def commit_ref(self):
        if value := os.getenv("GITHUB_REF"):
            return value

    @property
    def ci_actor(self):
        if value := os.getenv("GITHUB_ACTOR"):
            return value

    @property
    def ci_url(self):
        if self.repo_url and (value := os.getenv("GITHUB_RUN_ID")):
            return f"{self.repo_url}/actions/runs/{value}"

    @property
    def ci_event(self):
        if value := os.getenv("GITHUB_EVENT_NAME"):
            return value

    @property
    def pr_id(self):
        if (ref := os.environ.get("GITHUB_REF")).startswith("refs/pull/"):
            return int(ref.split("/")[2])

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
            "on": self.ci_event,
            "branch": self.commit_ref,
            "pull_request_id": self.pr_id,
        }
