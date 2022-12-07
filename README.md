# Semgrep Action

<p align="center">
  <a href="https://r2c.dev/slack">
      <img src="https://img.shields.io/badge/Slack-1.5K%2B%20members-black" alt="Slack invite" />
  </a>
  <a href="https://semgrep.dev/docs/semgrep-ci/">
      <img src="https://img.shields.io/badge/docs-semgrep.dev-purple" alt="Documentation" />
  </a>
  <a href="https://github.com/returntocorp/semgrep-action/actions/workflows/test.yml">
      <img src="https://github.com/returntocorp/semgrep-action/actions/workflows/test.yml/badge.svg" alt="Tests status" />
  </a>
  <a href="https://hub.docker.com/r/returntocorp/semgrep-agent">
    <img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/returntocorp/semgrep-agent">
  </a>
</p>

## Update from April 11th, 2022

**Semgrep now supports GitHub Actions natively!** :tada:

Refer to the [GitHub Actions configuration document](https://semgrep.dev/docs/semgrep-ci/sample-ci-configs/#sample-github-actions-configuration-file) to run Semgrep natively in CI environments.

## Project summary

| **:warning: Warning :warning:** |
| --------------------------  |
| This wrapper script is **deprecated**. It is recommended to stop using this wrapper script and migrate to native Semgrep support instead. Refer to the [GitHub Actions configuration document](https://semgrep.dev/docs/semgrep-ci/sample-ci-configs/#sample-github-actions-configuration-file). |

Semgrep Action runs Semgrep in CI environments. It can also connect to Semgrep App to configure rules and review findings on a web UI.

To see all the configuration options, [check Semgrep docs](https://semgrep.dev/docs/semgrep-ci/sample-ci-configs/#sample-github-actions-configuration-file).
Semgrep Action runs [Semgrep](https://github.com/returntocorp/semgrep) in CI environments.
It can also connect to [Semgrep App](https://semgrep.dev/products/semgrep-app) to configure rules and review findings on a web UI.

- **Scan every commit.** Semgrep CI rapidly scans modified files on pull and merge requests, protecting developer productivity. Longer full project scans are configurable on merges to specific branches.
- **Block new bugs.** You shouldn’t have to fix existing bugs just to adopt a tool. Semgrep CI reports newly introduced issues on pull and merge requests, scanning them at their base and HEAD commits to compare findings. Developers are signficantly more likely to fix the issues they introduced themselves on PRs and MRs.
- **Get findings where you work.** Semgrep CI can connect to Semgrep App to present findings in Slack, on PRs and MRs via inline comments, email, and through 3rd party services.

> Semgrep runs fully in your build environment: code is never sent anywhere.

## Getting started

Semgrep behaves like other static analysis and linting tools:
it runs a set of user-configured rules and returns a non-zero exit code if there are findings,
resulting in its job showing a ✅ or ❌.

Refer to [Getting started with Semgrep in CI](https://semgrep.dev/docs/semgrep-ci/overview/) to set up a CI job with Semgrep.

Once Semgrep Action is running, [explore the Semgrep Registry](https://semgrep.dev/r) to find and add more project-specific rules.

## Configuration

See the [Semgrep in CI configuration reference](https://semgrep.dev/docs/semgrep-ci/configuration-reference/) for further customizations, such as scanning with custom rules, ignoring files, and tuning performance.

## Metrics

Semgrep collects opt-out non-identifiable aggregate metrics for improving the user experience, guiding Semgrep feature development, and identifying regressions.

The [`PRIVACY.md`](PRIVACY.md) file describes the principles that guide our data-collection decisions, the breakdown of the data that are and are not collected, and how to opt-out of Semgrep CI’s metrics.

> Semgrep never sends your source code anywhere.

## Technical details

### Packaging

The [Semgrep Action](https://github.com/marketplace/actions/semgrep-action) GitHub Marketplace listing
runs the [`semgrep-agent` Docker image](https://hub.docker.com/r/returntocorp/semgrep-agent).

New versions of Semgrep CI and the Docker image above are released by Semgrep maintainers on a regular basis.
To run all jobs with the latest releases, use the `returntocorp/semgrep` Docker image, or the `returntocorp/semgrep-action@v1` action.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)
