# commit SHA is from https://github.com/returntocorp/semgrep/pull/4777
FROM returntocorp/semgrep:0d8f2afdf246451f86cc823533629d6664c8afe2

USER root
WORKDIR /semgrep-agent
COPY src/* .
RUN ln -s /semgrep-agent/semgrep_agent.py /usr/local/bin/semgrep-agent

CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
