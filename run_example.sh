#!/usr/bin/env bash
# Polyglot Import CSV — Docker example runner (Git Bash / macOS / Linux).
#
# Default: start Docker (if needed), clean, dry-run, import with schema creation, inspect data.
#
# Examples:
#   ./run_example.sh
#   ./run_example.sh --dry-run
#   ./run_example.sh --clean --import
#   ./run_example.sh --csv data/ecommerce/ecommerce_join.csv --inspect
#   ./run_example.sh --no-create-schema --import
#   ./run_example.sh --fresh-start   # first-time: wipe volumes/images, re-pull, full default flow
#
# Options:
#   --csv PATH              CSV file (default: data/ecommerce/ecommerce_join.csv)
#   --config PATH           Import (mapping) JSON config (default: data/ecommerce/import_config.json)
#   --sgbd-config PATH      SGBD connection JSON config (default: data/ecommerce/sgbd_config.json)
#   --dry-run               Validate only (no Docker, no import)
#   --import                Real import (skip dry-run unless also passed)
#   --clean                 Empty all configured backends
#   --inspect               Log persisted data after other steps
#   --create-schema         Create DDL on import (default when importing)
#   --no-create-schema      Import without creating tables/keyspace
#   --no-docker             Do not start/wait for Docker (assume DBs already reachable)
#   --fresh-start           First-time run: down -v, remove images, pull, up --wait, then default flow
#   --only BACKENDS         Comma-separated backends (postgres,redis,...)
#   --log-file PATH         Write all output to this log file (default: logs/run_example_*.log)
#   --no-log                Do not write a log file
#   -h, --help              Show this help
#
# Colors: enabled on TTY; disable with NO_COLOR=1, force with FORCE_COLOR=1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"
# shellcheck source=scripts/console.sh
source "${ROOT}/scripts/console.sh"

# Preserve invocation for logging (argv is consumed by the option parser below).
ORIGINAL_ARGS=("$@")

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  export FORCE_COLOR=1
fi

CSV="data/ecommerce/ecommerce_join.csv"
CONFIG="data/ecommerce/import_config.json"
SGBD_CONFIG="data/ecommerce/sgbd_config.json"
DO_DOCKER=true
DO_DRY_RUN=false
DO_IMPORT=false
DO_CLEAN=false
DO_INSPECT=false
CREATE_SCHEMA=true
ONLY=""
USE_DEFAULT_FLOW=true
DO_LOG=true
LOG_FILE=""
DO_FRESH_START=false

usage() {
  sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --csv)
      CSV="$2"
      shift 2
      ;;
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --sgbd-config)
      SGBD_CONFIG="$2"
      shift 2
      ;;
    --dry-run)
      USE_DEFAULT_FLOW=false
      DO_DRY_RUN=true
      shift
      ;;
    --import)
      USE_DEFAULT_FLOW=false
      DO_IMPORT=true
      shift
      ;;
    --clean)
      USE_DEFAULT_FLOW=false
      DO_CLEAN=true
      shift
      ;;
    --inspect)
      USE_DEFAULT_FLOW=false
      DO_INSPECT=true
      shift
      ;;
    --create-schema)
      CREATE_SCHEMA=true
      shift
      ;;
    --no-create-schema)
      CREATE_SCHEMA=false
      shift
      ;;
    --no-docker)
      DO_DOCKER=false
      shift
      ;;
    --fresh-docker)
      log_err "Unknown option: --fresh-docker (renamed to --fresh-start)"
      exit 1
      ;;
    --fresh-start)
      DO_FRESH_START=true
      shift
      ;;
    --only)
      ONLY="$2"
      shift 2
      ;;
    --log-file)
      LOG_FILE="$2"
      shift 2
      ;;
    --no-log)
      DO_LOG=false
      export POLYGLOT_NO_LOG=1
      shift
      ;;
    *)
      log_err "Unknown option: $1"
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${USE_DEFAULT_FLOW}" == true ]]; then
  DO_CLEAN=true
  DO_DRY_RUN=true
  DO_IMPORT=true
  DO_INSPECT=true
fi

if [[ "${DO_DRY_RUN}" == false && "${DO_IMPORT}" == false && "${DO_CLEAN}" == false && "${DO_INSPECT}" == false ]]; then
  log_err "Nothing to do. Use --dry-run, --import, --clean, --inspect, or run without flags."
  exit 1
fi

if [[ ! -f "${CSV}" ]]; then
  log_err "CSV not found: ${CSV}"
  exit 1
fi
if [[ ! -f "${CONFIG}" ]]; then
  log_err "Config not found: ${CONFIG}"
  exit 1
fi
if [[ ! -f "${SGBD_CONFIG}" ]]; then
  log_err "SGBD config not found: ${SGBD_CONFIG}"
  exit 1
fi

if [[ "${DO_LOG}" == true ]]; then
  if [[ -n "${LOG_FILE}" ]]; then
    init_session_log "${ROOT}/logs" "run_example" "${LOG_FILE}"
  else
    init_session_log "${ROOT}/logs" "run_example"
  fi
fi

if command -v python >/dev/null 2>&1; then
  PY=python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  log_err "Python not found. Install Python 3.9+ and run: pip install -e \".[dev]\""
  exit 1
fi

DB_SCRIPT="scripts/inspect_persisted_data.py"

# Only the SGBDs declared in the SGBD config are started / waited on / inspected.
mapfile -t SELECTED_SERVICES < <(
  "${PY}" - "${SGBD_CONFIG}" <<'PYEOF'
import json, sys
order = ["postgres", "redis", "mongodb", "cassandra", "neo4j"]
with open(sys.argv[1], encoding="utf-8") as f:
    cfg = json.load(f)
for backend in order:
    if backend in cfg:
        print(backend)
PYEOF
)
if [[ ${#SELECTED_SERVICES[@]} -eq 0 ]]; then
  log_err "No SGBD declared in ${SGBD_CONFIG}."
  exit 1
fi

# Per-service connection metadata (port:timeout_seconds:label).
declare -A SERVICE_PORT_META=(
  [postgres]="5432:120:PostgreSQL"
  [redis]="6379:120:Redis"
  [mongodb]="27017:120:MongoDB"
  [cassandra]="9042:180:Cassandra"
  [neo4j]="7687:120:Neo4j"
)

# port:timeout_seconds:label — restricted to the selected SGBDs.
DATABASE_PORTS=()
for _svc in "${SELECTED_SERVICES[@]}"; do
  DATABASE_PORTS+=("${SERVICE_PORT_META[${_svc}]}")
done

is_tcp_open() {
  local host="${1:-127.0.0.1}"
  local port="$2"
  (echo >/dev/tcp/"${host}"/"${port}") 2>/dev/null
}

list_down_services() {
  local entry port _timeout label
  local down=()
  for entry in "${DATABASE_PORTS[@]}"; do
    IFS=':' read -r port _timeout label <<< "${entry}"
    if ! is_tcp_open 127.0.0.1 "${port}"; then
      down+=("${label} (127.0.0.1:${port})")
    fi
  done
  if [[ ${#down[@]} -gt 0 ]]; then
    printf '%s\n' "${down[@]}"
  fi
}

wait_tcp_port() {
  local host="${1:-127.0.0.1}"
  local port="$2"
  local timeout="${3:-120}"
  local label="${4:-service}"
  local start=$SECONDS
  if is_tcp_open "${host}" "${port}"; then
    log_service_ready "${label}"
    return 0
  fi
  log_wait "Waiting for ${label} on ${host}:${port} (up to ${timeout}s)..."
  while (( SECONDS - start < timeout )); do
    if is_tcp_open "${host}" "${port}"; then
      log_service_ready "${label}"
      return 0
    fi
    sleep 3
  done
  log_err "Timeout waiting for ${label} on port ${port}."
  return 1
}

docker_compose() {
  run_logged env DOCKER_CLI_HINTS=false docker compose "$@"
}

# Restricted to the SGBDs declared in the SGBD config (see SELECTED_SERVICES).
COMPOSE_SERVICES=("${SELECTED_SERVICES[@]}")

declare -A SERVICE_PORTS=(
  [postgres]=5432
  [redis]=6379
  [mongodb]=27017
  [cassandra]=9042
  [neo4j]=7687
)

container_health_status() {
  local service="$1"
  local cid
  cid="$(docker_compose ps -q "${service}" 2>/dev/null | head -n1)"
  if [[ -z "${cid}" ]]; then
    echo "missing"
    return
  fi
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${cid}" 2>/dev/null || echo "unknown"
}

# Ready = Docker healthcheck green, or port reachable when the container has no health metadata (legacy stack).
service_is_ready() {
  local svc="$1"
  local status port
  status="$(container_health_status "${svc}")"

  if [[ "${status}" == "healthy" ]]; then
    return 0
  fi

  port="${SERVICE_PORTS[${svc}]:-}"
  if [[ "${status}" == "none" && -n "${port}" ]] && is_tcp_open 127.0.0.1 "${port}"; then
    return 0
  fi

  return 1
}

all_services_ready() {
  local svc
  for svc in "${COMPOSE_SERVICES[@]}"; do
    if ! service_is_ready "${svc}"; then
      return 1
    fi
  done
  return 0
}

log_service_readiness() {
  local svc status port
  for svc in "${COMPOSE_SERVICES[@]}"; do
    status="$(container_health_status "${svc}")"
    port="${SERVICE_PORTS[${svc}]:-}"
    if [[ "${status}" == "healthy" ]] || [[ "${status}" == "none" && -n "${port}" ]] && is_tcp_open 127.0.0.1 "${port}"; then
      log_service_ready "${svc}"
      log_dim "    health: ${status}"
    else
      log_dim "  ${svc}: health=${status}"
    fi
  done
}

wait_for_services_ready() {
  local max_wait="${1:-240}"
  local start=$SECONDS

  log_wait "Waiting for databases to be ready (up to ${max_wait}s; Cassandra can be slow)..."
  while (( SECONDS - start < max_wait )); do
    if all_services_ready; then
      log_service_readiness
      return 0
    fi
    sleep 5
  done

  log_err "Timeout waiting for ready containers:"
  log_service_readiness
  return 1
}

docker_compose_up_and_wait() {
  log_step "Docker" "docker compose up -d --wait ${COMPOSE_SERVICES[*]}"
  if docker_compose up -d --wait --quiet-pull "${COMPOSE_SERVICES[@]}"; then
    log_ok "All selected database containers are healthy"
    return 0
  fi

  log_dim "compose --wait unavailable or timed out; falling back to readiness polling"
  run_logged docker_compose up -d --quiet-pull "${COMPOSE_SERVICES[@]}"
  wait_for_services_ready
}

ensure_docker_stack() {
  if ! command -v docker >/dev/null 2>&1; then
    log_err "Docker not found. Install Docker and ensure 'docker compose' works."
    exit 1
  fi

  local down_list
  down_list="$(list_down_services || true)"
  if [[ -z "${down_list}" ]]; then
    if all_services_ready; then
      log_ok "All database containers already running (ready)"
      return 0
    fi
    log_wait "Ports are open but containers are not ready; reconciling with compose up..."
    docker_compose_up_and_wait
    return
  fi

  log_wait "Some databases are not reachable yet:"
  while IFS= read -r line; do
    [[ -n "${line}" ]] && log_dim "${line}"
  done <<< "${down_list}"

  docker_compose_up_and_wait
}

fresh_start_stack() {
  if ! command -v docker >/dev/null 2>&1; then
    log_err "Docker not found. Install Docker and ensure 'docker compose' works."
    exit 1
  fi

  log_wait "Fresh start: remove containers, volumes, and images; re-download; bootstrap stack"

  log_step "Docker" "docker compose down -v --rmi all --remove-orphans"
  run_logged docker_compose down -v --rmi all --remove-orphans 2>/dev/null || true

  log_step "Docker" "docker compose pull --quiet"
  run_logged docker_compose pull --quiet >/dev/null 2>&1

  docker_compose_up_and_wait
  log_ok "Fresh start complete (empty databases, images re-downloaded)"
}

run_polyglot() {
  local dry_run="$1"
  local -a args=(-m polyglotimportcsv "${CSV}" --config "${CONFIG}" --sgbd-config "${SGBD_CONFIG}")
  if [[ -n "${ONLY}" ]]; then
    args+=(--only "${ONLY}")
  fi
  if [[ "${dry_run}" == true ]]; then
    args+=(--dry-run)
  elif [[ "${CREATE_SCHEMA}" == true ]]; then
    args+=(--create-schema)
  else
    args+=(--no-create-schema)
  fi
  run_logged "${PY}" "${args[@]}"
}

needs_docker=false
if [[ "${DO_DOCKER}" == true ]]; then
  if [[ "${DO_FRESH_START}" == true ]]; then
    needs_docker=true
  elif [[ "${DO_CLEAN}" == true || "${DO_IMPORT}" == true || "${DO_INSPECT}" == true || "${USE_DEFAULT_FLOW}" == true ]]; then
    needs_docker=true
  fi
fi

log_banner "Polyglot Import CSV · run example"
log_kv "CSV" "${CSV}"
log_kv "Config" "${CONFIG}"
log_kv "SGBD config" "${SGBD_CONFIG}"
log_kv "Services" "${SELECTED_SERVICES[*]}"
if [[ -n "${ONLY}" ]]; then
  log_kv "Only" "${ONLY}"
fi
if [[ -n "${POLYGLOT_LOG_FILE:-}" ]]; then
  log_kv "Log file" "${POLYGLOT_LOG_FILE}"
fi

if [[ ${#ORIGINAL_ARGS[@]} -gt 0 ]]; then
  log_command "./run_example.sh" "${ORIGINAL_ARGS[@]}"
else
  log_command "./run_example.sh"
fi
log_dim "(from repo root: ${ROOT})"
log_dim "Prerequisite (once): pip install -e \".[dev]\""

if [[ "${needs_docker}" == true ]]; then
  log_section "Docker stack"
  if [[ "${DO_FRESH_START}" == true ]]; then
    fresh_start_stack
  else
    ensure_docker_stack
  fi
fi

if [[ "${DO_CLEAN}" == true ]]; then
  log_section "Clean databases"
  run_logged "${PY}" "${DB_SCRIPT}" clean --config "${CONFIG}" --sgbd-config "${SGBD_CONFIG}"
fi

if [[ "${DO_DRY_RUN}" == true ]]; then
  log_section "Dry-run (no database connections)"
  run_polyglot true
fi

if [[ "${DO_IMPORT}" == true ]]; then
  log_section "Import"
  run_polyglot false
fi

if [[ "${DO_INSPECT}" == true ]]; then
  log_section "Inspect persisted data"
  run_logged "${PY}" "${DB_SCRIPT}" inspect --config "${CONFIG}" --sgbd-config "${SGBD_CONFIG}"
fi

log_done "All requested steps completed"
if [[ -n "${POLYGLOT_LOG_FILE:-}" ]]; then
  log_kv "Log saved to" "${POLYGLOT_LOG_FILE}"
fi
