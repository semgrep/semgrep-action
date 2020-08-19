FROM returntocorp/semgrep:0.20.0@sha256:06bd2a285ff0aeb3f0afc0e9144bdee8150125f130b1738599c9b9fc1734536b AS semgrep
FROM python:3.8-alpine

WORKDIR /app
COPY Pipfile* ./

ENV INSTALLED_SEMGREP_VERSION=0.20.0

COPY --from=semgrep /usr/local/bin/semgrep-core /tmp/semgrep-core

RUN apk add --no-cache --virtual=.build-deps build-base libffi-dev openssl-dev &&\
    apk add --no-cache --virtual=.run-deps bash git less libffi openssl &&\
    pip install --no-cache-dir pipenv==2020.5.28 &&\
    pipenv install --system &&\
    PRECOMPILED_LOCATION=/tmp/semgrep-core pipx install semgrep==${INSTALLED_SEMGREP_VERSION} &&\
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
