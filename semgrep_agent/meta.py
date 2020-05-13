import os

from dataclasses import dataclass


@dataclass
class Meta:
    @property
    def repo_name(self):
        return os.environ["GITHUB_REPOSITORY"]

    @property
    def repo_sha(self):
        return os.environ["GITHUB_SHA"]

    @property
    def repo_ref(self):
        return os.environ["GITHUB_REF"]

    @property
    def repo_url(self):
        return f"https://github.com/{self.repo_name}"

    @property
    def ci_actor(self):
        return os.environ["GITHUB_ACTOR"]

    @property
    def ci_url(self):
        return f"{self.repo_url}/actions/runs/{os.environ['GITHUB_RUN_ID']}"

    @property
    def ci_event(self):
        return os.environ["GITHUB_EVENT_NAME"]

    def to_dict(self):
        return {
            "repository": self.repo_name,
            "commit": self.repo_sha,
            "on": self.ci_event,
            "branch": self.repo_ref,
        }
