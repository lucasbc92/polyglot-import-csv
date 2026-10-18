#!/usr/bin/env bash
# Rebuild the example DBMS stack from scratch, keeping the downloaded images.
#
# `docker compose down --volumes` removes this project's containers, network and
# volumes, so every database starts empty; then all services are started and
# waited on until they are healthy. Images are kept, so nothing is downloaded
# again (run_example.sh --fresh-start also removes and re-pulls the images).
#
# Unused anonymous volumes left on the Docker host may belong to any project,
# so they are only listed; in a terminal the script asks before removing them.
#
# Usage: ./scripts/reset_docker.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=scripts/console.sh
source "${ROOT}/scripts/console.sh"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

export DOCKER_CLI_HINTS=false

log_banner "Docker reset (images kept)"

log_section "Docker daemon"
if ! command -v docker >/dev/null 2>&1; then
  log_err "Docker not found. Install Docker and ensure 'docker compose' works."
  exit 1
fi
# A stuck Docker Desktop VM makes every docker command hang, so bound the probe.
if ! timeout 30 docker info >/dev/null 2>&1; then
  log_err "The Docker daemon did not answer within 30s."
  log_dim "Start Docker Desktop and wait until it says the engine is running."
  log_dim "If it stays stuck: quit Docker Desktop, run 'wsl --shutdown', open it again."
  exit 1
fi
log_ok "Daemon is responding"

log_section "Remove containers, network and volumes"
run_logged docker compose down --volumes --remove-orphans

log_section "Unused anonymous volumes"
# down --volumes already removed this project's; what is left carries no
# compose project label, so it cannot be told apart from other projects' data.
dangling="$(docker volume ls -q --filter dangling=true \
  --filter label=com.docker.volume.anonymous)"
if [[ -z "${dangling}" ]]; then
  log_dim "None"
else
  count="$(printf '%s\n' "${dangling}" | wc -l | tr -d ' ')"
  log_warn "${count} unused anonymous volume(s); they may belong to ANY project on this Docker host."
  if [[ -t 0 ]]; then
    read -r -p "Remove them too? [y/N] " answer || answer=""
    if [[ "${answer}" == "y" || "${answer}" == "Y" ]]; then
      # shellcheck disable=SC2086  # one volume name per word
      run_logged docker volume rm ${dangling}
    else
      log_dim "Kept"
    fi
  else
    log_dim "Not a terminal, so kept (run the script in a terminal to be asked)."
  fi
fi

log_section "Start the stack"
run_logged docker compose up --detach --wait
run_logged docker compose ps

log_done "Stack recreated with empty databases"
