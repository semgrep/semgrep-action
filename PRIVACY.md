# Semgrep Privacy Policy

Semgrep collects usage data to provide useful results and to help us improve the product. We send two types of data to r2c servers: scan data and findings data.

## Scan data

Scan data provide information on the environment and performance of Semgrep. They power dashboards, identify anomalies with the product, and are needed for billing. The classes of data included are:
- Project identity (e.g. name, URL)
- Scan environment (e.g. CI provider, OS)
- Author identity (e.g. committer email)
- Commit metadata (e.g. commit hash)
- Scan metadata, including type of scan and scan parameters (e.g. files or branches to ignore)
- Review and review-requester identifying data (e.g pull-request ID, branch, merge base, request author)
- Semgrep environment (e.g. version, interpreter, timestamp)

## Findings data

Findings data are used to provide human readable content for notifications and integrations, as well tracking results as new, fixed, or duplicate. The classes of data included are:
- Check ID and metadata (as defined in the rule definition; e.g. OWASP category, message, severity)
- Code location, including file path, that triggered finding
- A one-way hash of a unique code identifier that includes the triggering code content
- **Code content is not collected**
