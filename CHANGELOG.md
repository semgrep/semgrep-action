# Upcoming - Date

# 2022-05-12

## Changed

- Use semgrep 0.92.0

# 2022-04-26

## Changed

- Use semgrep 0.90.0

## Fixed

- Allow --config and --audit-on multiple times (#566)

# 2022-04-20

## Changed

- Use semgrep 0.89.0
- The version of Git included in the Docker image has been bumped to 2.35.2;
  this means that the
  [safe directory check added in response to CVE-2022-24765](https://github.blog/2022-04-12-git-security-vulnerability-announced/)
  now applies to scans done with semgrep-agent.

  If the directory you scan is owned by a different user than semgrep-agent runs with,
  you will need to run `git config --global --add safe.directory /YOUR/REPO/PATH` before scanning,
  see [discussion on the release PR](https://github.com/returntocorp/semgrep-action/pull/567#issuecomment-1104375865).

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
