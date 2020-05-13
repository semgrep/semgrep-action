#!/usr/bin/env bash
set -euo pipefail

bento_path=$(which bento)

bento() {
  local bento_result=0
  $bento_path --agree --email "semgrep-action@returntocorp.com" "$@" || bento_result=$?

  if [[ "$1" == "check" ]]
  then
    local bento_output_path=$(mktemp)
    $bento_path --agree --email "semgrep-action@returntocorp.com" --formatter json "$@" > "$bento_output_path"

    echo
    /app/semgrep-monitor \
      "--semgrep-app-url=https://semgrep.live"\
      "--semgrep-app-token=${INPUT_SEMGREPAPPTOKEN-}"\
      "finish" \
      "$bento_result"
      "$bento_output_path"
      "--scan-id=${scan_id-}" \
      "--slack-url=${INPUT_SLACKWEBHOOKURL-}" || true
    echo
  fi

  # https://github.com/returntocorp/bento/tree/cfcd3ef#exit-codes
  # exit codes other than 0/1/2 indicate a malfunction 
  if [[ $bento_result -ge 3 ]]
  then
    cat ~/.bento/last.log
    echo
    echo "== [ERROR] \`semgrep $*\` failed with exit code ${bento_result}"
    echo
    echo "This is an internal error, please file an issue at https://github.com/returntocorp/semgrep/issues/new/choose"
    echo "and include the log output from above."
    exit $bento_result
  fi

  return $bento_result
}

handle_pull_request() {
  # the github ref would be `refs/pull/<pr #>/merge` which isn't known by name here
  # the github sha seems to refer to the base on re-runs
  # so we keep our own head ref around
  real_head_sha=$(git rev-parse HEAD)

  echo
  echo "== [1/3] going to go back to the commit you based your pull request on…"
  echo
  git checkout "${GITHUB_BASE_REF}"
  git status --branch --short

  echo
  echo "== [2/3] …now adding your pull request's changes back…"
  echo

  git checkout "${real_head_sha}" -- .
  git status --branch --short

  echo
  echo "== [3/3] …and seeing if there are any new findings!"
  echo
  bento init &> /dev/null
  bento check --tool=semgrep
}

handle_push() {
  echo
  echo "== seeing if there are any findings"
  echo
  bento init &> /dev/null
  bento check --all --tool=semgrep
}

handle_unknown() {
  echo "== [ERROR] the Semgrep action was triggered by an unsupported GitHub event."
  echo
  echo "This error is often caused by an unsupported value for `on:` in the action's configuration."
  echo "To resolve this issue, please confirm that the `on:` key only contains values from the following list: [pull_request, push]."
  echo "If the problem persists, please file an issue at https://github.com/returntocorp/semgrep/issues/new/choose"
  exit 2
}

check_prerequisites() {
  if ! [[ -v GITHUB_ACTIONS ]]
  then
    echo "== [WARNING] this script is designed to run via GitHub Actions"
  fi

  if ! [[ -v INPUT_CONFIG ]] && ! [[ -e .bento/semgrep.yml ]]
  then
    echo "== [WARNING] you didn't configure what rules semgrep should scan for."
    echo 
    echo "Please either set a config in the action's configuration according to"
    echo "https://github.com/returntocorp/semgrep-action#configuration"
    echo "or commit your own rules at the default path of .bento/semgrep.yml"
  fi
}

main() {
  echo "== action's environment: semgrep/$(semgrep --version), $($bento_path --version), $(python --version)"

  check_prerequisites
  echo "== triggered by a ${GITHUB_EVENT_NAME}"

  [[ -n "${INPUT_CONFIG}" ]] && export BENTO_REGISTRY=$INPUT_CONFIG

  echo
  scan_id=$(
    /app/semgrep-monitor \
    "--semgrep-app-url=https://semgrep.live"\
    "--semgrep-app-token=${INPUT_SEMGREPAPPTOKEN-}"\
    "start" \
    "${INPUT_DEPLOYMENTID-}"
  )
  echo

  case ${GITHUB_EVENT_NAME} in
    pull_request)
      handle_pull_request
      ;;

    push)
      handle_push
      ;;

    *)
      handle_unknown
      ;;
  esac
}

main
