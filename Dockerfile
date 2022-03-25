FROM returntocorp/semgrep:72f68220ecbddf38a9616382708b93474f6bbfae

USER root
WORKDIR /semgrep-agent
COPY src/* .
RUN ln -s /semgrep-agent/semgrep_agent.py /usr/local/bin/semgrep-agent &&\
    apk add --no-cache --virtual=.agent-run-deps bash git git-lfs less libffi openssl yaml

ENTRYPOINT []
CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
