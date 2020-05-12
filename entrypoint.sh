#!/usr/bin/env bash
set -euo pipefail

bento_path=$(which bento)

bento() {
  bento_result=0
  $bento_path --agree --email "semgrep-action@returntocorp.com" "$@" || bento_result=$?

  if [[ "$1" == "check" ]]
  then
    echo
    /app/semgrep-monitor "$bento_result" "--slack-url=${INPUT_SLACKWEBHOOKURL-}" || true
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
  echo
  echo "== seeing if there are any new findings"
  echo
  bento init &> /dev/null
  bento check --tool=semgrep --diff-against="${GITHUB_BASE_REF}"
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
