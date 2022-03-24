FROM returntocorp/semgrep:6157eda21d7b8aa1eb0e60a4dc8d2a1994e0ed58

USER root
WORKDIR /semgrep-agent
COPY src/* .
RUN ln -s /semgrep-agent/semgrep_agent.py /usr/local/bin/semgrep-agent

ENTRYPOINT []
CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
