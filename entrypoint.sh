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
        OUTPUT=$(/bin/sgrep-lint --error --config "${INPUT_CONFIG}" $INPUT_TARGETS)
        EXIT_CODE=$?
    else
        OUTPUT=$(/bin/sgrep-lint --config "${INPUT_CONFIG}" $INPUT_TARGETS)
        EXIT_CODE=$?
    fi
    echo "::set-output name=output::${OUTPUT}"
    exit $EXIT_CODE
}

main
