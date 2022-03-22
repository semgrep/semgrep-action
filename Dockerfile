# commit SHA is from https://github.com/returntocorp/semgrep/pull/4777
FROM returntocorp/semgrep:deed9410c79873c48530b9e9eac22b28858e7340

WORKDIR /app
COPY src/ .
USER root

CMD ["python", "/app/src/semgrep_agent.py"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
