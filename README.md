# Semgrep Action

[![r2c community slack](https://img.shields.io/badge/r2c_slack-join-brightgreen?style=for-the-badge&logo=slack&labelColor=4A154B)](https://join.slack.com/t/r2c-community/shared_invite/enQtNjU0NDYzMjAwODY4LWE3NTg1MGNhYTAwMzk5ZGRhMjQ2MzVhNGJiZjI1ZWQ0NjQ2YWI4ZGY3OGViMGJjNzA4ODQ3MjEzOWExNjZlNTA)

This GitHub Action reviews pull requests with [Semgrep](https://github.com/returntocorp/semgrep)
whenever a new commit is added to them.
It reports as failed if there are any new bugs
that first appeared in that pull request.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)
