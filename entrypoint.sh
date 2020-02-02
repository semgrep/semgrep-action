#!/bin/sh
set -e

function checkRequired() {
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

    if usesBoolean "${INPUT_ERROR}"; then
        ERROR="--error"
    else
        ERROR=""
    fi

    if uses "${INPUT_OUTPUT}"; then
        OUTPUT_ARG = "--output ${INPUT_OUTPUT}"
    else
        OUTPUT_ARG = ""
    fi

    set +e
    OUTPUT=$(/bin/sgrep-lint ${ERROR} --config "${INPUT_CONFIG}" ${OUTPUT_ARG} $INPUT_TARGETS)
    EXIT_CODE=$?
    set -e
    ## echo to STDERR so output shows up in GH action UI
    echo >&2 $OUTPUT
    echo "::set-output name=output::${OUTPUT}"
    exit $EXIT_CODE
}

main
