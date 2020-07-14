FROM returntocorp/semgrep:0.14.0@sha256:d9c940e6ace97cb2422e897cfaefee445917d972215b72b98d63f38615ec8897 AS semgrep
FROM python:3.8-alpine

WORKDIR /app
COPY Pipfile* ./

# if this is called BENTO_VERSION, click will think we're trying to set --version
ENV INSTALLED_BENTO_VERSION=0.13.0b4\
    INSTALLED_SEMGREP_VERSION=0.14.0

COPY --from=semgrep /bin/semgrep-core /tmp/semgrep-core

RUN apk add --no-cache --virtual=.build-deps build-base libffi-dev openssl-dev &&\
    apk add --no-cache --virtual=.run-deps bash git less libffi openssl &&\
    pip install --no-cache-dir pipenv==2020.5.28 &&\
    pipenv install --system &&\
    pipx install "bento-cli==${INSTALLED_BENTO_VERSION}" &&\
    PRECOMPILED_LOCATION=/tmp/semgrep-core pipx install "semgrep==${INSTALLED_SEMGREP_VERSION}" &&\
    pip uninstall -y pipenv &&\
    apk del .build-deps &&\
    rm -rf /root/.cache/* /tmp/*

COPY ./src/semgrep_agent /app/semgrep_agent
ENV PATH=/root/.local/bin:${PATH} \
    PYTHONPATH=/app:${PYTHONPATH}

CMD ["python", "-m", "semgrep_agent"]

ENV BENTO_ACTION=true\
    SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
