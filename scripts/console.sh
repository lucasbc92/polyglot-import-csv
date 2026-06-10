# Shared colored logging for bash scripts (source from run_example.sh).
# Respects NO_COLOR; set FORCE_COLOR=1 to force ANSI codes.

if [[ -t 1 && -z "${NO_COLOR:-}" ]] || [[ -n "${FORCE_COLOR:-}" ]]; then
  _C_RESET=$'\033[0m'
  _C_BOLD=$'\033[1m'
  _C_DIM=$'\033[2m'
  _C_RED=$'\033[31m'
  _C_GREEN=$'\033[32m'
  _C_YELLOW=$'\033[33m'
  _C_BLUE=$'\033[34m'
  _C_MAGENTA=$'\033[35m'
  _C_CYAN=$'\033[36m'
  _C_GRAY=$'\033[90m'
else
  _C_RESET='' _C_BOLD='' _C_DIM='' _C_RED='' _C_GREEN='' _C_YELLOW=''
  _C_BLUE='' _C_MAGENTA='' _C_CYAN='' _C_GRAY=''
fi

_log_rule() {
  local char="${1:-─}"
  printf '%b%s%b\n' "${_C_DIM}" "$(printf '%.0s'"${char}" 72)" "${_C_RESET}"
}

log_banner() {
  local title="$1"
  echo ""
  _log_rule "═"
  printf '%b  %s%b\n' "${_C_BOLD}${_C_CYAN}" "${title}" "${_C_RESET}"
  _log_rule "═"
}

log_section() {
  local title="$1"
  echo ""
  printf '%b▸ %s%b\n' "${_C_BOLD}${_C_BLUE}" "${title}" "${_C_RESET}"
  _log_rule
}

log_step() {
  local label="$1"
  local detail="${2:-}"
  if [[ -n "${detail}" ]]; then
    printf '  %b→%b %b%s%b %b%s%b\n' \
      "${_C_CYAN}" "${_C_RESET}" \
      "${_C_BOLD}" "${label}" "${_C_RESET}" \
      "${_C_DIM}" "${detail}" "${_C_RESET}"
  else
    printf '  %b→%b %b%s%b\n' \
      "${_C_CYAN}" "${_C_RESET}" \
      "${_C_BOLD}" "${label}" "${_C_RESET}"
  fi
}

log_kv() {
  printf '    %b%s:%b %s\n' "${_C_DIM}" "$1" "${_C_RESET}" "$2"
}

log_ok() {
  printf '%b  ✓ %s%b\n' "${_C_GREEN}" "$1" "${_C_RESET}"
}

log_warn() {
  printf '%b  ! %s%b\n' "${_C_YELLOW}" "$1" "${_C_RESET}" >&2
}

log_err() {
  printf '%b  ✗ %s%b\n' "${_C_RED}" "$1" "${_C_RESET}" >&2
}

log_dim() {
  printf '%b    %s%b\n' "${_C_DIM}" "$1" "${_C_RESET}"
}

log_wait() {
  printf '%b  … %s%b\n' "${_C_YELLOW}" "$1" "${_C_RESET}"
}

log_service_ready() {
  printf '%b    ✓ %s ready%b\n' "${_C_GREEN}" "$1" "${_C_RESET}"
}

log_done() {
  echo ""
  log_ok "$1"
}

# Print a shell-ready command line (for logs and manual reproduction by an advisor).
_format_cmd_line() {
  local part
  local out=""
  for part in "$@"; do
    out+=" $(printf '%q' "${part}")"
  done
  echo "${out# }"
}

log_command() {
  local cmd_line
  cmd_line="$(_format_cmd_line "$@")"
  echo ""
  printf '%b  $ %s%b\n' "${_C_MAGENTA}" "${cmd_line}" "${_C_RESET}"
}

# Log, then execute (stdout/stderr flow through tee when logging is enabled).
run_logged() {
  log_command "$@"
  "$@"
}

# Strip ANSI escape codes (plain-text log files).
_strip_ansi_stream() {
  sed -u 's/\x1B\[[0-9;]*[a-zA-Z]//g'
}

# Tee stdout/stderr to logs/ (plain text). Sets POLYGLOT_LOG_FILE and POLYGLOT_LOG_TEE.
init_session_log() {
  local log_dir="${1:-logs}"
  local prefix="${2:-run_example}"
  local log_file="${3:-}"

  if [[ "${POLYGLOT_NO_LOG:-}" == "1" ]]; then
    return 0
  fi

  mkdir -p "${log_dir}"

  if [[ -n "${log_file}" ]]; then
    LOG_FILE="${log_file}"
  else
    LOG_FILE="${log_dir}/${prefix}_$(date +%Y%m%d_%H%M%S).log"
  fi

  export POLYGLOT_LOG_FILE="${LOG_FILE}"
  export POLYGLOT_LOG_TEE=1

  {
    echo ""
    echo "--- session started $(date -Iseconds 2>/dev/null || date) ---"
  } >> "${LOG_FILE}"

  exec > >(
    tee >( _strip_ansi_stream >> "${LOG_FILE}" )
  ) 2>&1
}

