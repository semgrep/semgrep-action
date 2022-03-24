# commit SHA is from https://github.com/returntocorp/semgrep/pull/4777
FROM returntocorp/semgrep:87d6d3032dd876f82191b433fea1ed02717767ae

USER root
WORKDIR /semgrep-agent
COPY src/* .
RUN ln -s /semgrep-agent/semgrep_agent.py /usr/local/bin/semgrep-agent

ENTRYPOINT []
CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
