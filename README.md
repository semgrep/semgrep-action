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
will enable all 160+ checks from [our registry](https://semgrep.live/r).
You will probably want to configure a specific set of checks,
see how to do that below.

## Configuration

### Selecting Rules

The `config` value lets you choose what rules and patterns semgrep should scan for.
You can set specify rules in one of the following ways:

- **semgrep.live registry ID**: `config: r/python.flask`  
  referring to a subset of the [semgrep.live registry](https://semgrep.live/r)
- **semgrep.live rule ID**: `config: xYz`  
  referring to a rule published from the [semgrep.live editor](https://semgrep.live)

If `config` is unset,
the default behavior is to look for rules
at the `.bento/semgrep.yml` path in your repo.

If this path does not exist,
Semgrep will run with a sample rule that searches for the `$X == $X` pattern.

### Slack Notifications

The Semgrep Action can notify you on Slack about findings.

1. [Create a new incoming webhook](https://slack.com/apps/A0F7XDUAZ-incoming-webhooks)
   on your Slack workspace,
   and set the channel in which you'd like to receive notifications.
2. [Add that URL as an encrypted secret](https://help.github.com/en/actions/configuring-and-managing-workflows/creating-and-storing-encrypted-secrets)
   for your GitHub repo, naming it `SEMGREP_SLACK_WEBHOOK_URL`.
3. Change `.github/workflows/semgrep.yml` to pass the secret as a parameter when running Bento:

   ```yaml
     with:
       slackWebhookURL: ${{ secrets.SEMGREP_SLACK_WEBHOOK_URL }}
   ```


## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)
