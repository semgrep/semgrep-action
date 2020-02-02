# sgrep action

This action runs [sgrep](https://sgrep.dev) and returns the output

## Inputs

### `config`

The config `file|directory|yaml_url|tar|url|registry_name`.

### `targets`

The target(s) to scan

## Outputs

### `findings`

The findings sgrep finds

## Example usage

uses: returntocorp/sgrep-action@v1
with:
  config: 'r2c'
  