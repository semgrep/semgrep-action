# Contributing

## Development setup

Install the correct version of poetry:

```
pip3 install poetry==1.0.10
```

Install semgrep

```
pip3 install semgrep
```

Install dependencies with poetry

```
poetry install
```

Get a Poetry shell with
```
poetry shell
```

Install pre-commit hooks:

```
python -m pip install pre-commit
pre-commit install
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

Connect to semgrep-app with the `--publish-token` flag.

## Tests

Run unit tests with

```
pytest tests
```

Run acceptance tests with

```
pytest tests/acceptance/qa.py
```

Regenerate acceptance snapshots with

```
python tests/acceptance/qa.py
```

Please always double-check generated snapshots for accuracy prior to committing
them!

## Release

Let CI pass on GitHub Actions before releasing.

If this release depends on a recent change to semgrep-app, ensure that all production
servers, including on-prem ones for our enterprise customers, have the latest changes.

After you merge your PR, check out develop and pull to get your latest changes.
The following command will change all action runs to use your current `HEAD`:

```
make release
```
