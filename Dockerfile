# the boltons library is not yet compatible with 3.10 - https://github.com/mahmoud/boltons/issues/294
FROM python:3.9-alpine

WORKDIR /app
COPY poetry.lock pyproject.toml ./

ENV INSTALLED_SEMGREP_VERSION=0.84.0


# This is all in one run command in order to save disk space.
# Note that there's a tradeoff here for debuggability.
RUN apk add --no-cache --virtual=.build-deps build-base cargo libffi-dev openssl-dev yaml-dev &&\
    apk add --no-cache --virtual=.run-deps bash git git-lfs less libffi openssl yaml &&\
    pip install --no-cache-dir pipx~=1.0.0 &&\
    pipx install semgrep==${INSTALLED_SEMGREP_VERSION} &&\
    pipx inject semgrep 'git+https://github.com/returntocorp/semgrep.git@55af3ff7ee6d16454f6a31f59603094283c46c87#egg=semgrep&subdirectory=semgrep' &&\
    (pip freeze | xargs pip uninstall -y) &&\
    pip install --no-cache-dir poetry~=1.1.13 &&\
    poetry config virtualenvs.create false &&\
    # Don't install dev dependencies or semgrep-agent
    poetry install --no-dev --no-root &&\
    apk del .build-deps &&\
    rm -rf /root/.cache/* /root/.cargo/* /tmp/* &&\
    find / \( -name '*.pyc' -o -path '*/__pycache__*' \) -delete

COPY ./src/semgrep_agent /app/src/semgrep_agent
RUN poetry install --no-dev &&\
    rm -rf /root/.cache/* /tmp/* &&\
    find / \( -name '*.pyc' -o -path '*/__pycache__*' \) -delete

ENV PATH=/root/.local/bin:${PATH}

CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
