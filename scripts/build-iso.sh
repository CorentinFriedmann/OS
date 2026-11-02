#!/usr/bin/env bash
# Construit l'ISO de Nova OS à partir du profil « releng » d'archiso.
# À lancer en root sur Arch Linux, après scripts/build-packages.sh.
#   scripts/build-iso.sh [dossier du dépôt nova] [dossier de sortie]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(realpath "${1:-$ROOT/out/repo}")"
OUT="$(realpath -m "${2:-$ROOT/out/iso}")"
WORK="${WORK:-$ROOT/work}"
PROFILE="$WORK/profile"
RELENG=/usr/share/archiso/configs/releng
VERSION="${NOVA_VERSION:-$(date -u +%Y.%m.%d)}"

[[ $EUID -eq 0 ]] || { echo "À lancer en root." >&2; exit 1; }
[[ -d "$RELENG" ]] || { echo "archiso n'est pas installé (pacman -S archiso)." >&2; exit 1; }
[[ -f "$REPO/nova.db.tar.gz" ]] || { echo "Dépôt [nova] introuvable dans $REPO." >&2; exit 1; }

echo "==> Profil : releng d'Arch + surcouche Nova"
rm -rf "$PROFILE"
mkdir -p "$WORK"
cp -a "$RELENG" "$PROFILE"

# 1) pacman.conf de construction : multilib, CachyOS (clés et miroirs) et dépôt Nova local
conf="$PROFILE/pacman.conf"
sed -i -E '/^#\[multilib\]/,/^#Include/ s/^#//' "$conf"
# pacman 7 : bac à sable désactivé sur cette machine (conteneur) → idem pour mkarchiso
if grep -q '^DisableSandbox' /etc/pacman.conf; then sed -i '/^\[options\]/a DisableSandbox' "$conf"; fi
python3 - "$conf" "$REPO" <<'PY'
import sys, re
path, repo = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
cachy = "[cachyos]\nServer = https://mirror.cachyos.org/repo/$arch/$repo\n\n"
nova = f"[nova]\nSigLevel = Optional TrustAll\nServer = file://{repo}\n\n"
text = re.sub(r"^\[core\]", nova + "[core]", text, count=1, flags=re.M)
text += "\n" + cachy
open(path, "w", encoding="utf-8").write(text)
PY

# 2) Paquets de l'image live : ceux qui n'existent pas (renommés, retirés des dépôts)
#    sont signalés et ignorés, plutôt que de faire échouer toute la construction
dbpath=$(mktemp -d)
pacman --config "$conf" --dbpath "$dbpath" -Sy >/dev/null
available=$(pacman --config "$conf" --dbpath "$dbpath" -Slq | sort -u)
rm -rf "$dbpath"
wanted=$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/archiso/packages.x86_64" | sort -u)
missing=$(comm -23 <(echo "$wanted") <(echo "$available") | tr '\n' ' ')
if [[ -n "${missing// }" ]]; then
  echo "::warning::Paquets introuvables, ignorés dans l'image live : $missing"
  if [[ " $missing" == *" nova-"* ]]; then
    echo "Paquets Nova manquants dans $REPO : $missing" >&2
    exit 1
  fi
fi
comm -12 <(echo "$wanted") <(echo "$available") >> "$PROFILE/packages.x86_64"
sort -u -o "$PROFILE/packages.x86_64" "$PROFILE/packages.x86_64"

# 3) Fichiers du système live
cp -a "$ROOT/archiso/airootfs/." "$PROFILE/airootfs/"
mkdir -p "$PROFILE/airootfs/opt/nova/repo"
cp "$REPO"/*.pkg.tar.zst "$PROFILE/airootfs/opt/nova/repo/"
cp -L "$REPO/nova.db" "$PROFILE/airootfs/opt/nova/repo/nova.db"
cp -L "$REPO/nova.files" "$PROFILE/airootfs/opt/nova/repo/nova.files"
# Réseau : NetworkManager (applet du bureau) à la place de systemd-networkd/iwd
rm -f "$PROFILE"/airootfs/etc/systemd/system/multi-user.target.wants/{systemd-networkd,iwd}.service
rm -f "$PROFILE"/airootfs/etc/systemd/system/network-online.target.wants/systemd-networkd-wait-online.service
rm -f "$PROFILE"/airootfs/etc/systemd/system/sockets.target.wants/systemd-networkd.socket

# 4) Identité de l'ISO
sed -i -E \
  -e "s|^iso_name=.*|iso_name=\"novaos\"|" \
  -e "s|^iso_label=.*|iso_label=\"NOVA_$(date -u +%Y%m)\"|" \
  -e "s|^iso_publisher=.*|iso_publisher=\"Nova OS <https://github.com/CorentinFriedmann/OS>\"|" \
  -e "s|^iso_application=.*|iso_application=\"Nova OS — essai et installation\"|" \
  -e "s|^iso_version=.*|iso_version=\"$VERSION\"|" \
  "$PROFILE/profiledef.sh"
cat >> "$PROFILE/profiledef.sh" <<'PERMS'
file_permissions+=(
  ["/etc/sudoers.d/00-nova-live"]="0:0:440"
  ["/usr/local/bin/nova-live-setup"]="0:0:755"
  ["/usr/local/bin/nova-live-welcome"]="0:0:755"
  ["/usr/local/bin/nova-autoinstall"]="0:0:755"
)
PERMS

# 5) Menus de démarrage de la clé : « Nova OS » au lieu de « Arch Linux »
while IFS= read -r -d '' file; do
  sed -i -e 's/Arch Linux install medium/Nova OS — essai et installation/g' -e 's/Arch Linux/Nova OS/g' "$file"
done < <(find "$PROFILE/efiboot" "$PROFILE/syslinux" "$PROFILE/grub" -type f \( -name '*.conf' -o -name '*.cfg' \) -print0 2>/dev/null)

echo "==> mkarchiso (plusieurs minutes)"
mkdir -p "$OUT"
mkarchiso -v -r -w "$WORK/build" -o "$OUT" "$PROFILE"
ls -lh "$OUT"
