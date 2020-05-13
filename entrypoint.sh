#!/usr/bin/env bash
set -euo pipefail

bento_path=$(which bento)

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
}

main
