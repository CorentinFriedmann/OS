# shellcheck shell=bash
# NOVA OS — installateur : interface (gum si présent, sinon questions en texte).

# shellcheck disable=SC2034 # palette complète, utilisée selon les écrans
CYAN=$'\e[38;2;0;240;255m'
MAGENTA=$'\e[38;2;255;43;214m'
VIOLET=$'\e[38;2;138;92;255m'
GREEN=$'\e[38;2;61;255;168m'
YELLOW=$'\e[38;2;255;210;63m'
RED=$'\e[38;2;255;56;96m'
DIM=$'\e[2m'
BOLD=$'\e[1m'
RESET=$'\e[0m'

HAVE_GUM=0
if command -v gum >/dev/null 2>&1 && [[ -t 0 && -t 1 ]]; then
  HAVE_GUM=1
  export GUM_CHOOSE_CURSOR_FOREGROUND="#00f0ff" GUM_CHOOSE_SELECTED_FOREGROUND="#ff2bd6"
  export GUM_CHOOSE_HEADER_FOREGROUND="#8a5cff" GUM_INPUT_CURSOR_FOREGROUND="#00f0ff"
  export GUM_INPUT_PROMPT_FOREGROUND="#00f0ff" GUM_INPUT_HEADER_FOREGROUND="#8a5cff"
  export GUM_CONFIRM_PROMPT_FOREGROUND="#e6f1ff" GUM_CONFIRM_SELECTED_BACKGROUND="#ff2bd6"
  export GUM_SPIN_SPINNER_FOREGROUND="#00f0ff"
fi

ui_banner() {
  printf '%s' "$CYAN"
  cat <<'EOF'

    ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗
    ████╗  ██║██╔═══██╗██║   ██║██╔══██╗
    ██╔██╗ ██║██║   ██║██║   ██║███████║
    ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║
    ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║
    ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝
EOF
  printf '%s       Installation de Nova OS%s\n\n' "$MAGENTA" "$RESET"
}

ui_step() { printf '\n%s━━ %s %s%s\n' "$VIOLET" "$1" "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "$RESET"; }
ui_info() { printf '%s›%s %s\n' "$CYAN" "$RESET" "$*"; }
ui_ok() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
ui_warn() { printf '%s!%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
ui_error() { printf '%s✗ %s%s\n' "$RED" "$*" "$RESET" >&2; }
die() { ui_error "$*"; exit 1; }

# ui_input "Question" "valeur par défaut"
ui_input() {
  local prompt=$1 default=${2:-} answer
  if (( HAVE_GUM )); then
    answer=$(gum input --header "$prompt" --value "$default" --placeholder "$default") || exit 130
  else
    read -rp "$prompt [$default] : " answer || exit 130
  fi
  printf '%s' "${answer:-$default}"
}

ui_password() {
  local prompt=$1 answer
  if (( HAVE_GUM )); then
    answer=$(gum input --password --header "$prompt") || exit 130
  else
    read -rsp "$prompt : " answer || exit 130
    echo >&2
  fi
  printf '%s' "$answer"
}

# ui_choose "Question" option1 option2 ...
ui_choose() {
  local prompt=$1; shift
  if (( HAVE_GUM )); then
    gum choose --header "$prompt" "$@" || exit 130
    return
  fi
  local PS3="$prompt (numéro) : " choice
  select choice in "$@"; do
    [[ -n "$choice" ]] && { printf '%s\n' "$choice"; return; }
  done
  exit 130
}

# ui_choose_multi "Question" "présélection1,présélection2" option1 option2 ...
ui_choose_multi() {
  local prompt=$1 selected=$2; shift 2
  if (( HAVE_GUM )); then
    gum choose --no-limit --header "$prompt (espace pour cocher)" --selected "$selected" "$@" || exit 130
    return
  fi
  local option answer
  for option in "$@"; do
    local def=n
    [[ ",$selected," == *",$option,"* ]] && def=o
    read -rp "$prompt — $option ? [${def^^}/${def/o/n}] : " answer || exit 130
    answer=${answer:-$def}
    [[ "${answer,,}" == o* || "${answer,,}" == y* ]] && printf '%s\n' "$option"
  done
}

ui_confirm() {
  local prompt=$1
  if (( HAVE_GUM )); then
    gum confirm --affirmative "Oui" --negative "Non" "$prompt"
    return
  fi
  local answer
  read -rp "$prompt [o/N] : " answer || return 1
  [[ "${answer,,}" == o* || "${answer,,}" == y* ]]
}

# ui_run "Titre" commande args... — exécute en journalisant, avec une animation
ui_run() {
  local title=$1; shift
  if (( HAVE_GUM )) && [[ -z "${NOVA_VERBOSE:-}" ]]; then
    # shellcheck disable=SC2016 # développé par le bash enfant, pas ici
    if gum spin --spinner dot --title "$title" -- bash -c '"$@" >>"$NOVA_LOG" 2>&1' _ "$@"; then
      ui_ok "$title"
      return 0
    fi
  else
    ui_info "$title…"
    if "$@" >>"$NOVA_LOG" 2>&1; then
      ui_ok "$title"
      return 0
    fi
  fi
  ui_error "Échec : $title (détails dans $NOVA_LOG)"
  tail -n 15 "$NOVA_LOG" >&2
  return 1
}
