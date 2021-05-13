FROM python:3.9.5-alpine

WORKDIR /app
COPY poetry.lock ./
COPY pyproject.toml ./

ENV INSTALLED_SEMGREP_VERSION=0.51.0

# This is all in one run command in order to save disk space.
# Note that there's a tradeoff here for debuggability.
RUN apk add --no-cache --virtual=.build-deps build-base libffi-dev openssl-dev &&\
    apk add --no-cache --virtual=.run-deps bash git less libffi openssl &&\
    # Need to pin cryptography version to avoid Rust compiler dependency
    pip install --no-cache-dir cryptography==3.3.2 poetry==1.1.6 &&\
    pip install --no-cache-dir pipx &&\
    pipx install semgrep==${INSTALLED_SEMGREP_VERSION} &&\
    poetry config virtualenvs.create false &&\
    # Don't install dev dependencies or semgrep-agent
    poetry install --no-dev --no-root &&\
    apk del .build-deps &&\
    rm -rf /root/.cache/* /tmp/*

COPY ./src/semgrep_agent /app/src/semgrep_agent
RUN poetry install --no-dev

ENV PATH=/root/.local/bin:${PATH}

CMD ["semgrep-agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
