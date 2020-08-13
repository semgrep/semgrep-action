# Contributing

## Development setup

Install dependencies with

```
pipenv install
```

Run the agent with

```
pipenv shell
export PYTHONPATH=$(pwd)/src
python -m semgrep_agent --config p/r2c
```

Run diff-aware scans in a git repo with clean state with

```
python -m semgrep_agent --config p/r2c --baseline-ref HEAD~1
```

Connect to semgrep-app with the `--publish-deployment` & `--publish-token` flags.

## Release

Let CI pass on GitHub Actions before releasing.
The following command will change all action runs to use your current `HEAD`:
```make release```
