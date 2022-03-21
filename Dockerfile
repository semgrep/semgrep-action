# commit SHA is from https://github.com/returntocorp/semgrep/pull/4777
FROM returntocorp/semgrep:cc962011f0c405ba5a4cc5b7af2ec4ca5472406d

WORKDIR /app
COPY src/ .

CMD ["python", "/app/src/semgrep_agent.py"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
