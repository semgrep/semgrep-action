FROM returntocorp/semgrep:0.103.0

USER root
WORKDIR /semgrep-agent
COPY src/* .
RUN ln -s /semgrep-agent/semgrep_agent.py /usr/local/bin/semgrep-agent &&\
    apk add --no-cache --virtual=.agent-run-deps bash git git-lfs less libffi openssl yaml

ENTRYPOINT []
CMD ["semgrep-agent"]

ENV PYTHONPATH=/semgrep-agent:$PYTHONPATH\
    SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1\
    SEMGREP_USER_AGENT_APPEND="agent"
