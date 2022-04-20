# Upcoming - Date

# 2022-04-20

## Changed

- Use semgrep 0.89.0

## Fixed

- Allow --config and --audit-on multiple times (#566)

# 2022-03-24

## Changed

- Use semgrep 0.86.0
- Move all functionality to `semgrep ci` and run that command

## Deprecating
- Deprecating `semgrep-agent --audit-on`: Instead of setting this flag, please use `semgrep ci || true` to ignore errors.
- Deprecating `INPUT_GENERATESARIF=1 semgrep-agent`: Instead of setting this environment variable, please run `semgrep --sarif --output semgrep.sarif`.
- For questions on updating usage of deprecated flags feel free to reach out to us on https://r2c.dev/slack

## Removed
- `semgrep-agent --json`: This flag will be consistent with Semgrep’s JSON format effective immediately. If you rely on the schema changes `semgrep-agent` introduced, please pin to `returntocorp/semgrep-agent:legacy` while you adapt to the Semgrep format.

# 2022-02-24

## Changed

- Use semgrep 0.81.0
