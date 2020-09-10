FROM returntocorp/semgrep:0.23.0@sha256:b0268f9c6ffb2da402b2f3da888d4177f8c712013dee4daf04cbe0797451475b AS semgrep
FROM python:3.7-alpine

WORKDIR /app
COPY poetry.lock ./
COPY pyproject.toml ./

ENV INSTALLED_SEMGREP_VERSION=0.23.0

COPY --from=semgrep /usr/local/bin/semgrep-core /tmp/semgrep-core

RUN apk add --no-cache --virtual=.build-deps build-base libffi-dev openssl-dev &&\
    apk add --no-cache --virtual=.run-deps bash git less libffi openssl &&\
    pip install --no-cache-dir poetry==1.0.10 &&\
    pip install --no-cache-dir pipx &&\
    PRECOMPILED_LOCATION=/tmp/semgrep-core pipx install semgrep==${INSTALLED_SEMGREP_VERSION} &&\
    poetry config virtualenvs.create false &&\
    # Don't install dev dependencies or semgrep-agent
    poetry install --no-dev --no-root &&\
    pip uninstall -y poetry &&\
    apk del .build-deps &&\
    rm -rf /root/.cache/* /tmp/*

COPY ./src/semgrep_agent /app/semgrep_agent
ENV PATH=/root/.local/bin:${PATH} \
    PYTHONPATH=/app:${PYTHONPATH}

CMD ["python", "-m", "semgrep_agent"]

ENV SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
