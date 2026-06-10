# Bash programmable completion for ./run_example.sh
#
# Enable once (Git Bash / Linux / macOS), then restart the shell or run: source ~/.bashrc
#
#   source "/c/Users/DELL/Documents/polyglot-import-csv/scripts/run_example.completion.bash"
#
# Replace the path with your clone location.

_RUN_EXAMPLE_COMPLETION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_RUN_EXAMPLE_REPO_ROOT="$(cd "${_RUN_EXAMPLE_COMPLETION_DIR}/.." && pwd)"
_RUN_EXAMPLE_SCRIPT="${_RUN_EXAMPLE_REPO_ROOT}/run_example.sh"

_run_example_completion() {
  local cur prev
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"

  local flags=(
    --csv --config
    --dry-run --import --clean --inspect
    --create-schema --no-create-schema
    --no-docker --fresh-start
    --only
    --log-file --no-log
    -h --help
  )
  local backends=(postgres mongodb cassandra redis neo4j)

  case "${prev}" in
    --csv)
      local -a samples=( "${_RUN_EXAMPLE_REPO_ROOT}"/data/ecommerce/*.csv )
      if [[ -e "${samples[0]}" ]]; then
        COMPREPLY=( $(compgen -W "$(printf '%s\n' "${samples[@]}")" -- "${cur}") )
      fi
      if [[ ${#COMPREPLY[@]} -eq 0 ]]; then
        COMPREPLY=( $(compgen -f -X '!*.csv' -- "${cur}") )
      fi
      return 0
      ;;
    --config)
      local -a configs=( "${_RUN_EXAMPLE_REPO_ROOT}"/data/ecommerce/*.json )
      if [[ -e "${configs[0]}" ]]; then
        COMPREPLY=( $(compgen -W "$(printf '%s\n' "${configs[@]}")" -- "${cur}") )
      fi
      if [[ ${#COMPREPLY[@]} -eq 0 ]]; then
        COMPREPLY=( $(compgen -f -X '!*.json' -- "${cur}") )
      fi
      return 0
      ;;
    --log-file)
      mkdir -p "${_RUN_EXAMPLE_REPO_ROOT}/logs" 2>/dev/null || true
      local -a logs=( "${_RUN_EXAMPLE_REPO_ROOT}"/logs/*.log )
      if [[ -e "${logs[0]}" ]]; then
        COMPREPLY=( $(compgen -W "$(printf '%s\n' "${logs[@]}")" -- "${cur}") )
      fi
      COMPREPLY+=( $(compgen -f -X '!*.log' -- "${cur}") )
      # Deduplicate while preserving order
      local -a unique=()
      local item
      for item in "${COMPREPLY[@]}"; do
        [[ " ${unique[*]} " == *" ${item} "* ]] || unique+=( "${item}" )
      done
      COMPREPLY=( "${unique[@]}" )
      return 0
      ;;
    --only)
      local prefix="" last selected b candidates
      last="${cur##*,}"
      if [[ "${cur}" == *","* ]]; then
        prefix="${cur%,*},"
      fi
      candidates=""
      for b in "${backends[@]}"; do
        selected=false
        local word
        for word in "${COMP_WORDS[@]}"; do
          if [[ "${word}" == *"${b}"* && "${word}" == *","* ]]; then
            selected=true
            break
          fi
        done
        [[ "${selected}" == false ]] && candidates+=" ${b}"
      done
      COMPREPLY=( $(compgen -W "${candidates}" -- "${last}") )
      COMPREPLY=( $(printf '%s\n' "${COMPREPLY[@]}" | sed "s|^|${prefix}|") )
      return 0
      ;;
  esac

  if [[ "${cur}" == -* ]]; then
    local available=()
    local flag already_used w
    for flag in "${flags[@]}"; do
      already_used=false
      for w in "${COMP_WORDS[@]}"; do
        if [[ "${w}" == "${flag}" ]]; then
          already_used=true
          break
        fi
      done
      [[ "${already_used}" == false ]] && available+=( "${flag}" )
    done
    COMPREPLY=( $(compgen -W "$(printf '%s\n' "${available[@]}")" -- "${cur}") )
  fi
}

# Relative, bare name, and absolute path to this repo's run_example.sh
complete -F _run_example_completion run_example.sh
complete -F _run_example_completion ./run_example.sh
if [[ -f "${_RUN_EXAMPLE_SCRIPT}" ]]; then
  complete -F _run_example_completion "${_RUN_EXAMPLE_SCRIPT}"
fi
