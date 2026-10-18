#!/usr/bin/env bash
# Rebuild the example DBMS stack from scratch, keeping the downloaded images.
#
# Removes this project's containers, network and volumes (named and anonymous,
# so every database starts empty), prunes unused anonymous volumes left behind by
# earlier runs, then starts all services and waits until they are healthy.
# Images are kept, so nothing is downloaded again (run_example.sh --fresh-start
# also removes and re-pulls the images).
#
# Usage: ./scripts/reset_docker.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=scripts/console.sh
source "${ROOT}/scripts/console.sh"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
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

log_section "Prune unused anonymous volumes"
# Docker >= 23 prunes only anonymous volumes here; named volumes need --all.
run_logged docker volume prune --force

log_section "Start the stack"
run_logged docker compose up --detach --wait --force-recreate
run_logged docker compose ps

log_done "Stack recreated with empty databases"
