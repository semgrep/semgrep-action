# commit SHA is from https://github.com/returntocorp/semgrep/pull/4777
FROM returntocorp/semgrep:bdeb43ff85578561d5b698165da9ebc290071f7d

WORKDIR /app
COPY src/ .

CMD ["python", "/app/src/semgrep_agent.py"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
