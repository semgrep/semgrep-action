# Contributing

## Development setup

Install semgrep

```
pip install semgrep
```

Install pre-commit hooks:

```
pip install pre-commit
pre-commit install
```

Run the agent with

```
python src/semgrep_agent.py
```

Run diff-aware scans in a git repo with clean state with

```
python src/semgrep_agent.py --config p/r2c --baseline-ref HEAD~1
```

Connect to semgrep-app with the `--publish-token` flag.

## Tests

### Install testing dependencies

```
pip install poetry
poetry install
```

### Acceptance tests

Run with

```
poetry run pytest tests/acceptance/qa.py
```

Regenerate snapshots with

```
poetry run python tests/acceptance/qa.py
```

You may want to use a specific Semgrep build while doing this.
In this case, prepend the directory of your Semgrep binary to your `PATH`.

```
PATH=~/cli/semgrep/.venv/bin:$PATH poetry run python tests/acceptance/qa.py
```

Please always double-check generated snapshots for accuracy prior to committing!

## Release

Let CI pass on GitHub Actions before releasing.

If this release depends on a recent change to semgrep-app, ensure that all production
servers, including on-prem ones for our enterprise customers, have the latest changes.

After you merge your PR, check out develop and pull to get your latest changes.
The following command will change all action runs to use your current `HEAD`:

```
make release
```
