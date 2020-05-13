FROM returntocorp/semgrep:0.6.1@sha256:be3080478445f76c38b150235a029d49c41188f1ee9e12d4fbfafede3ab3e27c AS semgrep
FROM python:3.8-alpine

WORKDIR /app
COPY Pipfile* ./

RUN apk add --no-cache --virtual=.build-deps build-base libffi-dev openssl-dev &&\
    apk add --no-cache --virtual=.run-deps bash git less libffi openssl &&\
    pip install --no-cache-dir pipenv==2018.11.26 &&\
    pipenv install --system &&\
    apk del .build-deps &&\
    rm -rf /root/.cache/* /tmp/*

COPY --from=semgrep /bin/semgrep-files /bin/semgrep-files
COPY --from=semgrep /bin/semgrep-core /bin/semgrep-core

RUN ln -s /bin/semgrep-files/semgrep /bin/semgrep

COPY entrypoint.sh semgrep-monitor ./

ENTRYPOINT ["/app/entrypoint.sh"]

ENV BENTO_ACTION=true\
    SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
