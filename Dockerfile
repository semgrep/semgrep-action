FROM returntocorp/semgrep:0.17.0@sha256:cdfa923acc3593c426489bcdf6472c748d4c2e065b8028c8bdbfcb9c7dca0065 AS semgrep
FROM python:3.8-alpine

WORKDIR /app
COPY Pipfile* ./

ENV INSTALLED_SEMGREP_VERSION=0.17.0

COPY --from=semgrep /usr/local/bin/semgrep-core /tmp/semgrep-core

RUN apk add --no-cache --virtual=.build-deps build-base libffi-dev openssl-dev &&\
    apk add --no-cache --virtual=.run-deps bash git less libffi openssl &&\
    pip install --no-cache-dir pipenv==2020.5.28 &&\
    pipenv install --system &&\
    wget -O /tmp/semgrep.tar.gz https://github.com/returntocorp/semgrep/archive/v${INSTALLED_SEMGREP_VERSION}.tar.gz &&\
    tar xf /tmp/semgrep.tar.gz -C /tmp &&\
    PRECOMPILED_LOCATION=/tmp/semgrep-core pipx install /tmp/semgrep-${INSTALLED_SEMGREP_VERSION}/semgrep &&\
    pip uninstall -y pipenv &&\
    apk del .build-deps &&\
    rm -rf /root/.cache/* /tmp/*

COPY ./src/semgrep_agent /app/semgrep_agent
ENV PATH=/root/.local/bin:${PATH} \
    PYTHONPATH=/app:${PYTHONPATH}

CMD ["python", "-m", "semgrep_agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
