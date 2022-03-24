FROM returntocorp/semgrep:21210813d8fee4bb3f85b8d8bcf227d9a60cda83

USER root
WORKDIR /semgrep-agent
COPY src/* .
RUN ln -s /semgrep-agent/semgrep_agent.py /usr/local/bin/semgrep-agent

ENTRYPOINT []
CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
