# Semgrep Action

[![r2c community slack](https://img.shields.io/badge/r2c_slack-join-brightgreen?style=for-the-badge&logo=slack&labelColor=4A154B)](https://join.slack.com/t/r2c-community/shared_invite/enQtNjU0NDYzMjAwODY4LWE3NTg1MGNhYTAwMzk5ZGRhMjQ2MzVhNGJiZjI1ZWQ0NjQ2YWI4ZGY3OGViMGJjNzA4ODQ3MjEzOWExNjZlNTA)

Semgrep Action is a wrapper around [Semgrep](https://github.com/returntocorp/semgrep) for running as a GitHub Action, in Gitlab, and in other CI providers and interfacing with [https://semgrep.dev](https://semgrep.dev).

It reviews only the changed files in pull requests with Semgrep whenever a new commit is added to them, and reports only issues that are newly introduced in that pull request.

## Usage

### In any environment

The project has deep integration with the CI environment of GitHub Actions and GitLab CI (see below),
but its more advanced features work anywhere if you pass a few environment variables.

To use Semgrep Action on the commandline with a default ruleset, use

```
semgrep-agent --config r/all
```

To run semgrep-agent with a customized policy of rules, email and slack notifications, and with any CI provider, use the following shell command

```
SEMGREP_REPO_URL="https://example.com/myrepo" SEMGREP_JOB_URL="https://example.com/myjob" semgrep-agent --publish-deployment=<your_deployment_id> --publish-token=<your_API_token>
```

Where the environment variables `SEMGREP_REPO_URL` and `SEMGREP_JOB_URL` are optional, but will enable more helpful notifications.

You can customize your policies, find `your_deployment_id`, and get `your_API_token` at <https://semgrep.dev/manage>

_Treat your API Token as a SECRET and do not store it in the clear!_ Save it as a secret environment variable instead.

### In GitHub

To start checking all pull requests,
add the following file at `.github/workflows/semgrep.yml`:

```yaml
name: Semgrep
on: [pull_request]
jobs:
  semgrep:
    runs-on: ubuntu-latest
    name: Check
    steps:
      - uses: actions/checkout@v1
      - name: Semgrep
        id: semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          config: p/r2c
```

Note that the `p/r2c` config value
will enable a default set of checks from [our registry](https://semgrep.live/explore).

You will probably want to configure a specific set of checks instead.
See how to do that by setting up a project on <https://semgrep.dev/manage/projects>

#### Inline PR Comments

If you would like inline PR comments to get posted by Semgrep (GitHub only), set the environment variable `GITHUB_TOKEN` as well in `.github/workflows/semgrep.yml`.
You can either use the GitHub App installation access token `secrets.GITHUB_TOKEN`, or a personal access token that has access to repositories.

```yaml
env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

To set a personal access token, go to your [developer settings](https://github.com/settings/tokens), and generate a new token with "repo" (if your repository is private) or "public_repo" (if your repository is public) checked.

## Configuration

### Selecting Rules

The `config` value lets you choose what rules and patterns semgrep should scan for.
You can set specify rules in one of the following ways:

- **semgrep.live registry ID**: `config: r/python.flask`  
  referring to a subset of the [semgrep.live registry](https://semgrep.live/r)
- **semgrep.live ruleset ID**: `config: p/r2c`  
  referring to a ruleset created on [semgrep.live's rulesets page](https://semgrep.live/rulesets)
- **semgrep.live snippet ID**: `config: s/xYz` or `config: s/john:named-rule`
  referring to a rule published from the [semgrep.live editor](https://semgrep.live)

If `config` is unset,
the default behavior is to look for rules
in the `.semgrep.yml` file in your repo,
or load the rules from the `.semgrep` folder in your repo.

If none of these provide a configuration,
the action will fail.

### Ignoring Paths

You can commit a `.semgrepignore` file
to skip scanning specific paths,
using the same syntax as `.gitignore`.

If there's no `.semgrepignore` file in your repository,
we will use a default ignore list that skips common test and dependency directories,
including `tests/`, `node_modules/`, and `vendor/`.
You can find the full list in our [`.semgrepignore` template file](https://github.com/returntocorp/semgrep-action/blob/v1/src/semgrep_agent/templates/.semgrepignore).
To override these default ignore patterns,
commit your own `.semgrepignore`.

Note that `.semgrepignore` is picked up only by the action,
and will not be honored when running `semgrep` manually.

### Audit mode

If you want to see findings from your whole repo
instead of just the changed files that would be scanned
whenever a pull request comes in,
you'd normally set up scans on pushes to your main branch.
This can prove difficult when you already have existing issues
that Semgrep finds on the main branch
— you probably don't want CI to fail all builds on the main branch
until every single finding is addressed.

For this case, we recommend using audit mode.
In audit mode, Semgrep will collect findings data for you to review,
but will never fail the build due to findings.

To enable audit mode on pushes in GitHub Actions,
set the option `auditOn: push` in your workflow file.

On the command line, set the `--audit-on event_name` flag.

The most common event names on GitHub are `push` and `pull_request`.
In other cases, you can find the correct event name
in the first few lines of the agent's log output.

## Technical details

Semgrep-action scans files in the current directory with [semgrep](https://github.com/returntocorp/semgrep), and exits with a non-zero exit code if blocking issues are found.

Findings are blocking by default. They can be [set to non-blocking](https://github.com/returntocorp/semgrep-action/issues/34) by changing the action in semgrep.dev/manage/policy.

Semgrep-action has the option to report only new issues, added since a specific commit.
When run in a continuous integration (CI) pipeline, semgrep-action determines the base commit from [environment variables](https://github.com/returntocorp/semgrep-action/blob/develop/src/semgrep_agent/meta.py), as set by GitHub, GitLab, Travis or CircleCI. The base commit can also be passed on the command line using the option --baseline-ref.

Semgrep-action determines new issues by only [scanning modified files](https://github.com/returntocorp/semgrep-action/blob/develop/src/semgrep_agent/targets.py), and scanning twice. It scans the current commit, checks out the base commit and scans that, and removes previously existing findings from the scan result. When using a semgrep config file stored in the repository itself, the old commit is scanned using the old version of the config file. [Findings are compared](https://github.com/returntocorp/semgrep-action/blob/develop/src/semgrep_agent/findings.py) on identifier, file path, code and count. If the identifier of a rule is modified in the semgrep configuration, or if the file containing the issues is renamed, all findings are considered new. Changing code that is matched by a rule will thus result in a new finding, even though the finding was previously present and the change did not introduce it.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)
