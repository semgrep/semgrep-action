# Contributing

## Development setup

Install the correct version of poetry:

```
pip3 install poetry==poetry==1.1.0b2
```

Install dependencies with poetry

```
poetry install
```

Run the agent with

```
poetry shell
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

### Publishing to pypi

```
poetry publish
```
