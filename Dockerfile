FROM returntocorp/semgrep:0.9.0@sha256:181c44fc98ba61b0af957dd4bb2d7eac3498af53774478fe640015273f5930a8 AS semgrep
FROM python:3.8-alpine

WORKDIR /app
COPY Pipfile* ./

RUN apk add --no-cache --virtual=.build-deps build-base libffi-dev openssl-dev &&\
    apk add --no-cache --virtual=.run-deps bash git less libffi openssl &&\
    pip install --no-cache-dir pipenv==2020.5.28 &&\
    pipenv install --system &&\
    pip uninstall -y pipenv &&\
    apk del .build-deps &&\
    rm -rf /root/.cache/* /tmp/* &&\
    mkdir /bin/semgrep-package/

COPY --from=semgrep /bin/semgrep-core /bin/semgrep-core
COPY ./semgrep_agent /app/semgrep_agent
ENV PYTHONPATH=/app

CMD ["python", "-m", "semgrep_agent"]

ENV BENTO_ACTION=true\
    SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1\
    SEMGREP_IN_DOCKER=1
