#!/usr/bin/env bash
# CI : construit les paquets Nova, vérifie la configuration Hyprland et construit
# l'ISO, dans un conteneur Arch Linux lancé par le workflow :
#   docker run --rm --privileged -v "$PWD:/src" -w /src -e HOST_UID -e HOST_GID \
#     -e NOVA_VERSION archlinux:latest bash scripts/ci/build-in-arch.sh
# Chaque étape est journalisée dans out/logs/ (publié même en cas d'échec).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOGS="$ROOT/out/logs"
CACHYOS_KEY=F3B607488DB35A47

# --- étapes (chacune tourne dans son propre bash, avec set -e) ---------------------------

setup_system() {
  pacman-key --init
  pacman-key --populate archlinux
  if ! pacman -Sy --noconfirm --needed archlinux-keyring; then
    # pacman 7 : le bac à sable de téléchargement peut échouer dans certains conteneurs
    # (build-iso.sh reporte alors ce réglage dans la configuration de mkarchiso)
    sed -i '/^\[options\]/a DisableSandbox' /etc/pacman.conf
    pacman -Sy --noconfirm --needed archlinux-keyring
  fi
  pacman -Su --noconfirm
  pacman -S --noconfirm --needed archiso base-devel git python python-pip python-pytest mtools hyprland
  import_cachyos_key
}

# Clé des dépôts CachyOS (l'image live embarque leurs clés et miroirs). Téléchargée en
# HTTPS (plus fiable que dirmngr en CI), puis par les serveurs de clés en secours.
import_cachyos_key() {
  local url attempt tmp
  tmp=$(mktemp)
  for attempt in 1 2 3; do
    for url in "https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x$CACHYOS_KEY" \
               "https://keys.openpgp.org/vks/v1/by-keyid/$CACHYOS_KEY"; do
      if curl -fsSL --max-time 30 "$url" -o "$tmp" && grep -q "BEGIN PGP PUBLIC KEY BLOCK" "$tmp" \
         && pacman-key --add "$tmp" && pacman-key --lsign-key "$CACHYOS_KEY"; then
        rm -f "$tmp"
        return 0
      fi
    done
    if pacman-key --keyserver hkps://keyserver.ubuntu.com --recv-keys "$CACHYOS_KEY" \
       && pacman-key --lsign-key "$CACHYOS_KEY"; then
      rm -f "$tmp"
      return 0
    fi
    sleep $(( attempt * 10 ))
  done
  rm -f "$tmp"
  echo "Impossible de récupérer la clé CachyOS $CACHYOS_KEY" >&2
  return 1
}

build_packages() {
  id builder >/dev/null 2>&1 || useradd -m builder
  chown -R builder: "$ROOT"
  sudo -H -u builder git config --global --add safe.directory "$ROOT"
  sudo -H -u builder bash "$ROOT/scripts/build-packages.sh" "$ROOT/out/repo"
  ls -l "$ROOT/out/repo"
}

verify_hyprland() {
  # La configuration Lua de Nova, validée par le Hyprland d'Arch (sans écran)
  local tmp
  tmp=$(sudo -u builder mktemp -d)
  sudo -u builder tee "$tmp/hyprland.lua" >/dev/null <<EOF
package.path = "$ROOT/desktop/hypr/?.lua;$ROOT/desktop/hypr/?/init.lua;" .. package.path
require("nova").setup({ })
EOF
  Hyprland --version
  sudo -u builder env XDG_RUNTIME_DIR="$tmp" HOME="$tmp" Hyprland --verify-config --config "$tmp/hyprland.lua"
}

build_iso() {
  WORK="$ROOT/work" bash "$ROOT/scripts/build-iso.sh" "$ROOT/out/repo" "$ROOT/out/iso"
  rm -rf "$ROOT/work"
  ls -l "$ROOT/out/iso"
}

if [[ "${1:-}" == step ]]; then
  shift
  "$@"
  exit
fi

# --- enchaînement ----------------------------------------------------------------------------
mkdir -p "$LOGS"
restore_owner() {
  # Rend les fichiers à l'utilisateur du runner, quoi qu'il arrive
  if [[ -n "${HOST_UID:-}" ]]; then chown -R "$HOST_UID:${HOST_GID:-$HOST_UID}" "$ROOT"; fi
}
trap restore_owner EXIT

run() {  # run NOM ÉTAPE : exécute une étape en l'affichant et en la journalisant
  local name=$1 status=0
  shift
  echo "::group::$name"
  bash "${BASH_SOURCE[0]}" step "$@" 2>&1 | tee "$LOGS/$name.log" || status=$?
  echo "::endgroup::"
  if (( status )); then
    echo "::error::Échec de l'étape « $name » (code $status), voir out/logs/$name.log"
  fi
  return "$status"
}

run 01-systeme setup_system
run 02-paquets build_packages
run 03-hyprland verify_hyprland || echo "::warning::La configuration Hyprland n'est pas validée par la version d'Arch (voir 03-hyprland.log)"
run 04-iso build_iso
df -h "$ROOT" | tee "$LOGS/05-disque.log"
