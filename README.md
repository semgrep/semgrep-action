# Semgrep Action

[![r2c community slack](https://img.shields.io/badge/r2c_slack-join-brightgreen?style=for-the-badge&logo=slack&labelColor=4A154B)](https://join.slack.com/t/r2c-community/shared_invite/enQtNjU0NDYzMjAwODY4LWE3NTg1MGNhYTAwMzk5ZGRhMjQ2MzVhNGJiZjI1ZWQ0NjQ2YWI4ZGY3OGViMGJjNzA4ODQ3MjEzOWExNjZlNTA)

This GitHub Action reviews pull requests with [Semgrep](https://github.com/returntocorp/semgrep)
whenever a new commit is added to them.
It reports as failed if there are any new bugs
that first appeared in that pull request.

## Usage

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
        config: r/all
```

Note that the `r/all` config value
will enable the hundreds of checks from [our registry](https://semgrep.live/r).
You will probably want to configure a specific set of checks,
see how to do that below.

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

## Technical details

Semgrep-action scans files in the current directory with [semgrep](https://github.com/returntocorp/semgrep), and exits with a non-zero exit code if blocking issues are found.

Findings are blocking by default. They can be [set to non-blocking](https://github.com/returntocorp/semgrep-action/issues/34) by changing the action in semgrep.dev, or setting the metadata field `dev.semgrep.actions` to something other than `block`.

Semgrep-action has the option to report only new issues, added since a specific commit.
When ran in a continuous integration (CI) pipeline, semgrep-action determines the base commit from [environment variables](https://github.com/returntocorp/semgrep-action/blob/develop/src/semgrep_agent/meta.py), as set by GitHub, GitLab, Travis or CircleCI. The base commit can also be passed on the command line.

Semgrep-action determines new issues by only [scanning modified files](https://github.com/returntocorp/semgrep-action/blob/develop/src/semgrep_agent/targets.py), and scanning twice. It scans the current commit, checks out the base commit and scans that, and removes previously existing findings from the scan result. When using a semgrep config file stored in the repository itself, the old commit is scanned using the old version of the config file. [Findings are compared](https://github.com/returntocorp/semgrep-action/blob/develop/src/semgrep_agent/findings.py) on identifier, file path, code and count. If the identifier of a rule is modified in the semgrep configuration, or the file containing the issues is renamed, all findings are considered new. For new issues that don't differ on identifier, file path, and code, the issues most at the bottom of the file are reported. Changing code that is matched by a rule will result in a new finding, even though the finding was previously present and the change did not introduce it.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)
