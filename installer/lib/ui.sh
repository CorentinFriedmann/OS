# shellcheck shell=bash
# NOVA OS — installateur : interface (gum si présent, sinon questions en texte).

# shellcheck disable=SC2034 # palette complète, utilisée selon les écrans
ACCENT=$'\e[38;2;138;180;255m'
LAVENDER=$'\e[38;2;185;173;255m'
VIOLET=$'\e[38;2;164;173;189m'
GREEN=$'\e[38;2;126;226;184m'
YELLOW=$'\e[38;2;242;207;134m'
RED=$'\e[38;2;255;143;143m'
DIM=$'\e[2m'
BOLD=$'\e[1m'
RESET=$'\e[0m'

HAVE_GUM=0
if command -v gum >/dev/null 2>&1 && [[ -t 0 && -t 1 ]]; then
  HAVE_GUM=1
  export GUM_CHOOSE_CURSOR_FOREGROUND="#8ab4ff" GUM_CHOOSE_SELECTED_FOREGROUND="#b9adff"
  export GUM_CHOOSE_HEADER_FOREGROUND="#a4adbd" GUM_INPUT_CURSOR_FOREGROUND="#8ab4ff"
  export GUM_INPUT_PROMPT_FOREGROUND="#8ab4ff" GUM_INPUT_HEADER_FOREGROUND="#a4adbd"
  export GUM_CONFIRM_PROMPT_FOREGROUND="#eef1f6" GUM_CONFIRM_SELECTED_BACKGROUND="#b9adff"
  export GUM_SPIN_SPINNER_FOREGROUND="#8ab4ff"
fi

ui_banner() {
  printf '%s' "$ACCENT"
  cat <<'EOF'

    ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗
    ████╗  ██║██╔═══██╗██║   ██║██╔══██╗
    ██╔██╗ ██║██║   ██║██║   ██║███████║
    ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║
    ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║
    ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝
EOF
  printf '%s       Installation de Nova OS%s\n\n' "$LAVENDER" "$RESET"
}

ui_step() { printf '\n%s━━ %s %s%s\n' "$VIOLET" "$1" "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "$RESET"; }
ui_info() { printf '%s›%s %s\n' "$ACCENT" "$RESET" "$*"; }
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
    # La commande tourne ici même (en arrière-plan) : elle garde l'accès aux fonctions
    # et variables de l'installateur. gum n'affiche que l'animation pendant l'attente.
    local pid code
    "$@" >>"$NOVA_LOG" 2>&1 &
    pid=$!
    gum spin --spinner dot --title "$title" -- \
      bash -c 'while kill -0 "$1" 2>/dev/null; do sleep 0.2; done' _ "$pid" || true
    code=0
    wait "$pid" || code=$?   # « || » : pas d'arrêt immédiat avec set -e
    if (( code == 0 )); then
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
