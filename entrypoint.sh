#!/bin/sh
set -e

function sanitize() {
    if [ -z "${1}" ]; then
        echo >&2 "Unable to find the ${2}. Did you set with.${2}?"
        exit 1
    fi
}

function uses() {
    [ ! -z "${1}" ]
}

function usesBoolean() {
    [ ! -z "${1}" ] && [ "${1}" = "true" ]
}

function main() {
    echo "" # see https://github.com/actions/toolkit/issues/168

    sanitize "${INPUT_CONFIG}" "config"
    sanitize "${INPUT_ERROR}" "error"
    sanitize "${INPUT_TARGETS}" "targets"

    if usesBoolean "${INPUT_ERROR}"; then
        ERROR="--error"
    else
        ERROR=""
    fi

    set +e
    OUTPUT=$(/bin/sgrep-lint ${ERROR} --config "${INPUT_CONFIG}" $INPUT_TARGETS)
    EXIT_CODE=$?
    set -e
    echo $OUTPUT
    echo "::set-output name=output::${OUTPUT}"
    exit 0
}

main
