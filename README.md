# sgrep action

This action runs [sgrep](https://sgrep.dev) and returns the output

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

The output of `sgrep`

## Example usage

Put in `.github/workflows/sgrep.yml`

```yaml

name: sgrep

on: [push]

jobs:
  self_test:
    runs-on: ubuntu-latest
    name: A job to run sgrep
    steps:
      - uses: actions/checkout@v2
      - name: sgrep action step
        id: sgrep
        uses: returntocorp/sgrep-action@develop
        with:
          config: tests/self_test.yml
          targets: tests'
      - name: Get the output from sgrep
        run: echo "sgrep ${{ steps.sgrep.outputs.output }}"
```
