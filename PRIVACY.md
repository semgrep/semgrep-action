# Semgrep CI Privacy Policy

## Metrics

Semgrep CI (also known as semgrep-action or semgrep-agent) may collect non-identifiable aggregate metrics to help improve the product. This document describes:

- the principles that guide our data-collection decisions
- the breakdown of the data that are and are not collected
- how to opt-out of Semgrep CI’s metrics

## Principles

These principles inform our decisions around data collection:

1. *Transparency*: Collect and use data in a way that is clearly explained to the user and benefits them
2. *User control*: Put users in control of their data at all times
3. *Limited data*: Collect what is needed, de-identify where possible, and delete when no longer necessary

## Collected data

Semgrep CI collects opt-out non-identifiable aggregate metrics for improving the user experience, guiding Semgrep feature development, and identifying regressions. It relies on Semgrep CLI’s metric collection, which is discussed in detail in that project’s [PRIVACY.md](https://github.com/returntocorp/semgrep/blob/develop/PRIVACY.md).

## Opt-out behavior

Semgrep CI’s metrics can be disabled by setting the environment variable `SEMGREP_SEND_METRICS=0` or using the flag `--disable-metrics`. If this environment variable or flag is not set, aggregate metrics are enabled.


## Data with Semgrep App only

For Semgrep App users running Semgrep CI with a SEMGREP_APP_TOKEN set, data is sent to power your dashboard, notification, and finding features. These data are ONLY sent when using Semgrep CI in an App-connected mode and are default-disabled for Semgrep CI users.

Two types of data are sent to r2c servers for this logged-in use case: scan data and findings data.

### Scan data

Scan data provide information on the environment and performance of Semgrep. They power dashboards, identify anomalies with the product, and are needed for billing. The classes of data included are:

- Project identity (e.g. name, URL)
- Scan environment (e.g. CI provider, OS)
- Author identity (e.g. committer email)
- Commit metadata (e.g. commit hash)
- Scan metadata, including type of scan and scan parameters (e.g. files or branches to ignore)
- Review and review-requester identifying data (e.g. pull-request ID, branch, merge base, request author)
- Semgrep environment (e.g. version, interpreter, timestamp)

### Findings data

Findings data are used to provide human readable content for notifications and integrations, as well tracking results as new, fixed, or duplicate. The classes of data included are:

- Check ID and metadata (as defined in the rule definition; e.g. OWASP category, message, severity)
- Code location, including file path, that triggered findings
- A one-way hash of a unique code identifier that includes the triggering code content
- Code content is not collected
