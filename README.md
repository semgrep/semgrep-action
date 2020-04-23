# semgrep action

This action runs [semgrep](https://semgrep.dev) and returns the output

## Inputs

### `config`

The config `file|directory|yaml_url|tar|url|registry_name`.

### `output`

The output arg `file|url`

### `targets`

The target(s) to scan

### `error`

If `true` will exit `1` which will break the build.

## Outputs

### `output`

The output of `semgrep`

## Example usage

Put in `.github/workflows/semgrep.yml`

```yaml

name: semgrep

on: [push]

jobs:
  self_test:
    runs-on: ubuntu-latest
    name: A job to run semgrep
    steps:
      - uses: actions/checkout@v2
      - name: semgrep action step
        id: semgrep
        uses: returntocorp/semgrep-action@develop
        with:
          config: tests/self_test.yml
          targets: tests'
      - name: Get the output from semgrep
        run: echo "semgrep ${{ steps.semgrep.outputs.output }}"
```
