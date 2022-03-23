# commit SHA is from https://github.com/returntocorp/semgrep/pull/4777
FROM returntocorp/semgrep:956e085e5217e44c46fb96f30ed109545e49dc29

USER root
WORKDIR /semgrep-agent
COPY src/* .
RUN ln -s /semgrep-agent/semgrep_agent.py /usr/local/bin/semgrep-agent

CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
