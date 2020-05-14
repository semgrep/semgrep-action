FROM returntocorp/semgrep:0.7.0@sha256:10eba0ce01582f703a8666f7d2e8eb625ce0779a57c05d7146097b0d87b4fc05 AS semgrep
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

COPY ./semgrep_agent /app/semgrep_agent
ENV PYTHONPATH=/app

CMD ["python", "-m", "semgrep_agent"]

ENV BENTO_ACTION=true\
    SEMGREP_ACTION=true\
    SEMGREP_ACTION_VERSION=v1\
    R2C_USE_REMOTE_DOCKER=1
