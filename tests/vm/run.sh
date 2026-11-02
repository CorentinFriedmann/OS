#!/usr/bin/env bash
# Test de bout en bout de Nova OS dans une vraie machine virtuelle (QEMU/KVM, UEFI) :
#  1. disque « Windows 11 » factice : EFI, MSR, C: (NTFS), récupération + espace libre
#  2. la clé Nova démarre et s'installe toute seule À CÔTÉ de Windows (volume NOVATEST,
#     voir archiso/airootfs/usr/local/bin/nova-autoinstall), puis s'éteint
#  3. vérifications hors ligne : Windows intact, GRUB avec Windows au menu, paquets, compte…
#  4. premier démarrage du système installé : captures du menu GRUB, de l'écran de
#     connexion et du bureau après connexion, puis lecture du journal de ce démarrage
#
# Usage (root, pour les périphériques loop) : tests/vm/run.sh nova.iso dossier-de-sortie
# Nécessite : qemu-system-x86_64, OVMF, sgdisk, mkfs.fat, mkntfs, mtools, python3
# Les vérifications sont des expressions évaluées plus tard par check() :
# shellcheck disable=SC2016,SC2034
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

[[ $EUID -eq 0 ]] || { echo "À lancer en root (périphériques loop)." >&2; exit 1; }
[[ -f "${1:-}" ]] || { echo "Usage : $0 nova.iso dossier-de-sortie" >&2; exit 2; }
ISO=$(realpath "$1")
OUT=$(realpath -m "${2:-out/vm}")
mkdir -p "$OUT"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/nova-vm.XXXXXX")
MNT="$WORK/mnt"
mkdir -p "$MNT"
REPORT="$OUT/rapport.txt"
: > "$REPORT"
PASSWORD=nebuleuse   # mêmes touches en AZERTY et en QWERTY (tapé au clavier virtuel)
INSTALL_TIMEOUT_MIN=${NOVA_VM_INSTALL_TIMEOUT:-100}
LOOP=""
QEMU_PID=""
TAIL_PID=""
export MTOOLS_SKIP_CHECK=1

# shellcheck source=../../installer/tests/fake-windows.sh
source "$ROOT/installer/tests/fake-windows.sh"

PASS=0
FAIL=0
WARN=0
log() { echo "$*" | tee -a "$REPORT"; }
ok() { log "  ✓ $*"; PASS=$((PASS + 1)); }
ko() { log "  ✗ $*"; FAIL=$((FAIL + 1)); }
# check : vérification bloquante ; soft : simple avertissement (limites de la VM, sans GPU)
check() { if eval "$2"; then ok "$1"; else ko "$1"; fi; }
soft() { if eval "$2"; then ok "$1"; else log "  ! $1 (avertissement)"; WARN=$((WARN + 1)); fi; }
vm() { python3 "$HERE/vm.py" "$1" "$WORK/qmp.sock" "${@:2}"; }
shot() { vm shot "$OUT/$1" 2>&1 | tee -a "$OUT/captures.txt" >/dev/null; }

attach() {
  LOOP=$(losetup -f --show -P "$WORK/disque.img")
  partx -u "$LOOP" 2>/dev/null
  udevadm settle 2>/dev/null || sleep 1
}
detach() {
  umount -R "$MNT" 2>/dev/null
  [[ -n "$LOOP" ]] && losetup -d "$LOOP" 2>/dev/null
  LOOP=""
}
stop_vm() {
  if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
    vm quit >/dev/null 2>&1 || kill "$QEMU_PID" 2>/dev/null
  fi
  [[ -n "$QEMU_PID" ]] && wait "$QEMU_PID" 2>/dev/null
  QEMU_PID=""
}
cleanup() {
  stop_vm
  [[ -n "$TAIL_PID" ]] && kill "$TAIL_PID" 2>/dev/null
  detach
  rm -rf "$WORK"
}
trap cleanup EXIT

# --- Micrologiciel UEFI et accélération -----------------------------------------------
OVMF_CODE_FILE="" OVMF_VARS_FILE=""
for pair in "${OVMF_CODE:-}:${OVMF_VARS:-}" \
            /usr/share/OVMF/OVMF_CODE_4M.fd:/usr/share/OVMF/OVMF_VARS_4M.fd \
            /usr/share/edk2/x64/OVMF_CODE.4m.fd:/usr/share/edk2/x64/OVMF_VARS.4m.fd \
            /usr/share/OVMF/OVMF_CODE.fd:/usr/share/OVMF/OVMF_VARS.fd; do
  if [[ -f "${pair%%:*}" && -f "${pair#*:}" ]]; then
    OVMF_CODE_FILE=${pair%%:*}
    OVMF_VARS_FILE=${pair#*:}
    break
  fi
done
[[ -n "$OVMF_CODE_FILE" ]] || { echo "Micrologiciel UEFI (OVMF) introuvable : installe le paquet ovmf." >&2; exit 1; }
if [[ -w /dev/kvm ]]; then
  ACCEL=(-enable-kvm -cpu host)
else
  ACCEL=(-accel tcg -cpu max)
fi

# qemu_start NOM [options QEMU en plus] : démarre la VM en arrière-plan
qemu_start() {
  local name=$1
  shift
  rm -f "$WORK/qmp.sock"
  "${QEMU:-qemu-system-x86_64}" "${ACCEL[@]}" -machine q35 -smp 4 -m "${NOVA_VM_RAM:-6144}" \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$OVMF_CODE_FILE" \
    -drive "if=pflash,format=raw,unit=1,file=$WORK/vars.fd" \
    -drive "file=$WORK/disque.img,format=raw,if=none,id=cible,cache=unsafe" \
    -device virtio-blk-pci,drive=cible,serial=NOVATARGET \
    -netdev user,id=net0 -device virtio-net-pci,netdev=net0,romfile= \
    -device virtio-rng-pci -device virtio-vga -display none -no-reboot \
    -qmp "unix:$WORK/qmp.sock,server=on,wait=off" \
    -serial "file:$OUT/serie-$name.log" \
    "$@" > "$OUT/qemu-$name.log" 2>&1 &
  QEMU_PID=$!
  sleep 3
  if ! kill -0 "$QEMU_PID" 2>/dev/null; then
    cat "$OUT/qemu-$name.log" >&2
    QEMU_PID=""
    return 1
  fi
}

gpt_windows() { local n; for n in 1 2 3 4; do sgdisk -i "$n" "$1" 2>/dev/null; done; }
windows_data() { local n; for n in 2 3 4; do partition_fingerprint "$(part "$1" "$n")"; done; }

log "== Nova OS : test complet en machine virtuelle ($(date -u '+%Y-%m-%d %H:%M UTC'))"
log "ISO : $(basename "$ISO") ($(numfmt --to=iec-i --suffix=o "$(stat -c %s "$ISO")"))"
log "Machine : ${ACCEL[*]}, UEFI ($(basename "$OVMF_CODE_FILE")), ${NOVA_VM_RAM:-6144} Mo"

# --- 1. Faux Windows -----------------------------------------------------------------------
log ""
log "1. Disque « Windows 11 » factice (64 Gio : EFI 100 Mo, MSR, C: 20 Gio, récupération, ~43 Gio libres)"
truncate -s 64G "$WORK/disque.img"
attach
make_windows_disk "$LOOP" 20G
GPT_AVANT=$(gpt_windows "$LOOP")
DONNEES_AVANT=$(windows_data "$LOOP")
detach
cp "$OVMF_VARS_FILE" "$WORK/vars.fd"

truncate -s 64M "$WORK/novatest.img"
mkfs.fat -n NOVATEST "$WORK/novatest.img" >/dev/null
cat > "$WORK/nova-autoinstall.cfg" <<EOF
# Réponses de l'installation automatique (test en VM) : comme un vrai utilisateur
NOVA_DISK=\$(readlink -f /dev/disk/by-id/virtio-NOVATARGET)
NOVA_MODE=dualboot
NOVA_USER=testeur
NOVA_FULLNAME="Testeur Nova"
NOVA_PASSWORD=$PASSWORD
NOVA_HOSTNAME=nova-vm
NOVA_PROFILES=jeux,dev,multimedia
NOVA_GPUS=intel
NOVA_CONFIRM=yes
EOF
mcopy -i "$WORK/novatest.img" "$WORK/nova-autoinstall.cfg" ::/
ok "disque Windows factice et volume NOVATEST prêts"

# --- 2. Installation automatique depuis la clé -----------------------------------------------
log ""
log "2. Démarrage de la clé Nova et installation automatique à côté de Windows"
if ! qemu_start installation \
     -drive "file=$ISO,media=cdrom,if=none,id=cle,readonly=on" -device ide-cd,drive=cle,bus=ide.0,bootindex=0 \
     -drive "file=$WORK/novatest.img,format=raw,if=none,id=novatest" -device virtio-blk-pci,drive=novatest,serial=NOVATEST; then
  ko "QEMU n'a pas démarré (voir qemu-installation.log)"
  exit 1
fi
tail -n +1 -F "$OUT/serie-installation.log" 2>/dev/null &   # progression en direct dans le journal de la CI
TAIL_PID=$!
start=$SECONDS
last_shot=0
while kill -0 "$QEMU_PID" 2>/dev/null; do
  elapsed=$(( SECONDS - start ))
  if (( elapsed >= 150 )) && [[ ! -f "$OUT/01-session-live.png" ]]; then
    shot 01-session-live.png
  fi
  if (( elapsed - last_shot >= 60 )); then
    shot 02-installation-derniere-image.png
    last_shot=$elapsed
  fi
  if (( elapsed > 600 )) && ! grep -q "NOVA-AUTOINSTALL" "$OUT/serie-installation.log" 2>/dev/null; then
    shot 02-installation-derniere-image.png
    ko "l'installation automatique n'a pas démarré (rien sur la console série après 10 min)"
    stop_vm
    break
  fi
  if (( elapsed > INSTALL_TIMEOUT_MIN * 60 )); then
    shot 02-installation-derniere-image.png
    ko "installation pas terminée après $INSTALL_TIMEOUT_MIN minutes"
    stop_vm
    break
  fi
  sleep 10
done
[[ -n "$QEMU_PID" ]] && wait "$QEMU_PID" 2>/dev/null
QEMU_PID=""
kill "$TAIL_PID" 2>/dev/null
TAIL_PID=""
log "  · durée : $(( (SECONDS - start) / 60 )) min"

mkdir -p "$OUT/live"
for file in resultat.txt nova-install.log nova-install.out journal-live.txt; do
  mcopy -o -i "$WORK/novatest.img" "::/$file" "$OUT/live/$file" 2>/dev/null
done
RESULT=$(tr -d '\r\n' 2>/dev/null < "$OUT/live/resultat.txt")
check "installation terminée sans erreur (${RESULT:-aucun résultat})" '[[ "$RESULT" == INSTALL_OK ]]'
skipped=$(grep -h "Paquets ignorés" "$OUT/live/nova-install.log" 2>/dev/null | head -n1)
[[ -n "$skipped" ]] && log "  ! $skipped"

# --- 3. Vérifications hors ligne -------------------------------------------------------------
log ""
log "3. Vérifications du disque après l'installation"
attach
ESP=$(part "$LOOP" 1)
NOVA=$(part "$LOOP" 5)
check "Windows : partitions 1 à 4 inchangées dans la table GPT" '[[ "$(gpt_windows "$LOOP")" == "$GPT_AVANT" ]]'
check "Windows : MSR, C: et récupération identiques au bit près" '[[ "$(windows_data "$LOOP")" == "$DONNEES_AVANT" ]]'
check "Windows : chargeur EFI/Microsoft/Boot/bootmgfw.efi intact" '[[ "$(mtype -i "$ESP" ::/EFI/Microsoft/Boot/bootmgfw.efi 2>/dev/null)" == "chargeur Windows factice" ]]'
check "GRUB de Nova ajouté à la partition EFI (EFI/Nova/grubx64.efi)" 'mdir -b -i "$ESP" ::/EFI/Nova 2>/dev/null | grep -qi grubx64.efi'
check "chargeur de secours EFI/BOOT non créé (dual-boot)" '! mdir -i "$ESP" ::/EFI/BOOT >/dev/null 2>&1'
check "partition Nova btrfs dans l'espace libre" '[[ "$(blkid -p -o value -s TYPE "$NOVA" 2>/dev/null)" == btrfs ]]'

if [[ -b "$NOVA" ]] && mount -o ro,subvol=@ "$NOVA" "$MNT" 2>/dev/null; then
  check "identité Nova OS (os-release)" 'grep -q "^NAME=\"Nova OS\"" "$MNT/usr/lib/os-release"'
  check "noyau CachyOS + noyau de secours LTS" '[[ -f "$MNT/boot/vmlinuz-linux-cachyos" && -f "$MNT/boot/vmlinuz-linux-lts" ]]'
  check "initramfs générés (avec écran de démarrage Plymouth)" '[[ -f "$MNT/boot/initramfs-linux-cachyos.img" ]] && grep -q plymouth "$MNT/etc/mkinitcpio.conf.d/nova.conf"'
  check "menu GRUB : Nova" 'grep -q "^menuentry .Nova Linux" "$MNT/boot/grub/grub.cfg"'
  check "menu GRUB : pas d'entrées techniques du micrologiciel" '! grep -q "EFI BootNext" "$MNT/boot/grub/grub.cfg"'
  check "menu GRUB : Windows détecté" 'grep -qi "^menuentry .Windows" "$MNT/boot/grub/grub.cfg"'
  check "menu GRUB : thème néon Nova" 'grep -q "themes/nova/theme.txt" "$MNT/boot/grub/grub.cfg"'
  check "compte « testeur » (fish) administrateur" 'grep -q "^testeur:.*:/usr/bin/fish$" "$MNT/etc/passwd" && grep -qE "^wheel:.*testeur" "$MNT/etc/group"'
  check "compte root verrouillé" 'grep -q "^root:!" "$MNT/etc/shadow"'
  check "mot de passe effacé du disque (script de configuration supprimé)" '[[ ! -e "$MNT/root/nova-configure.sh" ]]'
  check "sauvegarde de la table des partitions d'origine conservée" 'compgen -G "$MNT/var/lib/nova/nova-gpt-*.bin" >/dev/null'
  check "paquets Nova (branding, bureau, performances, assistant)" '[[ $(find "$MNT/var/lib/pacman/local" -maxdepth 1 -name "nova-*" | wc -l) -eq 4 ]]'
  check "dépôts optimisés CachyOS actifs" 'grep -q "^\[cachyos" "$MNT/etc/pacman.conf"'
  check "dépôt [nova] en ligne pour les mises à jour" 'grep -A3 "^\[nova\]" "$MNT/etc/pacman.conf" | grep -q "releases/download/repo"'
  check "fstab : sous-volumes sans subvolid (retour en arrière possible)" 'grep -qE "subvol=/@([,[:space:]]|$)" "$MNT/etc/fstab" && ! grep -q subvolid "$MNT/etc/fstab"'
  check "instantanés snapper configurés" '[[ -f "$MNT/etc/snapper/configs/root" ]]'
  check "écran de connexion SDDM activé" '[[ "$(readlink "$MNT/etc/systemd/system/display-manager.service")" == *sddm.service ]]'
  check "horloge en heure locale (comme Windows)" 'grep -q LOCAL "$MNT/etc/adjtime"'
  check "français : langue et clavier" 'grep -q "LANG=fr_FR.UTF-8" "$MNT/etc/locale.conf" && grep -q "fr-latin9" "$MNT/etc/vconsole.conf"'
  log "  · $(find "$MNT/var/lib/pacman/local" -mindepth 1 -maxdepth 1 -type d | wc -l) paquets installés"
  cp "$MNT/boot/grub/grub.cfg" "$OUT/grub.cfg" 2>/dev/null && chmod 644 "$OUT/grub.cfg"
  cp "$MNT/etc/pacman.conf" "$OUT/pacman.conf" 2>/dev/null
  grep -E "^(menuentry|submenu)" "$OUT/grub.cfg" 2>/dev/null | cut -d"'" -f2 | sed 's/^/  · menu : /' | tee -a "$REPORT"
  umount "$MNT"
else
  ko "système installé introuvable (sous-volume @)"
fi
detach

# --- 4. Premier démarrage ------------------------------------------------------------------------
if [[ "$RESULT" == INSTALL_OK ]]; then
  log ""
  log "4. Premier démarrage du système installé (captures d'écran)"
  if qemu_start premier-demarrage; then
    # Menu GRUB : la touche « haut » arrête le compte à rebours dès qu'il apparaît
    vm spam up 30
    sleep 1
    shot 10-menu-grub.png
    vm keys ret
    sleep 25
    shot 11-demarrage.png
    sleep 50
    shot 12-ecran-de-connexion.png
    # Connexion : le nom est déjà rempli (dernier utilisateur), le curseur est sur le mot de passe
    vm type "$PASSWORD"
    vm keys ret
    sleep 45
    shot 13-bureau.png
    sleep 45
    shot 14-bureau-apres-90s.png
    # Écrit tout sur le disque (SysRq « sync », autorisé par défaut) avant d'arrêter la VM
    vm chord alt sysrq s
    sleep 8
    stop_vm
  else
    ko "QEMU n'a pas démarré pour le premier démarrage"
  fi

  attach
  NOVA=$(part "$LOOP" 5)
  JOURNAL="$OUT/journal-premier-demarrage.txt"
  if mount -o ro,subvol=@log "$NOVA" "$MNT" 2>/dev/null; then
    # Journal lu avec la même version de systemd qu'Arch si docker est là
    if command -v docker >/dev/null && docker image inspect archlinux:latest >/dev/null 2>&1; then
      docker run --rm -v "$MNT:/journal-nova:ro" archlinux:latest \
        journalctl --directory=/journal-nova/journal --no-pager -o short-monotonic > "$JOURNAL" 2>&1
    else
      journalctl --directory="$MNT/journal" --no-pager -o short-monotonic > "$JOURNAL" 2>&1
    fi
    umount "$MNT"
  fi
  if mount -o ro,subvol=@home "$NOVA" "$MNT" 2>/dev/null; then
    cp "$MNT/testeur/.local/share/sddm/wayland-session.log" "$OUT/session-wayland.log" 2>/dev/null
    umount "$MNT"
  fi
  detach
  check "démarrage complet (« Startup finished » dans le journal)" 'grep -q "Startup finished" "$JOURNAL"'
  check "écran de connexion SDDM lancé" 'grep -q "Started.*Simple Desktop Display Manager" "$JOURNAL"'
  soft "connexion de « testeur » acceptée" 'grep -q "session opened for user testeur" "$JOURNAL"'
  soft "session Hyprland lancée" 'grep -qi "hyprland" "$OUT/session-wayland.log" 2>/dev/null'
  soft "aucun plantage (core dump)" '! grep -q "dumped core" "$JOURNAL"'
  soft "aucun service en échec" '! grep -qE "Failed to start|Failed with result" "$JOURNAL"'
  grep -E "Failed to start|Failed with result|dumped core" "$JOURNAL" 2>/dev/null | head -n 15 | sed 's/^/    /' | tee -a "$REPORT"
fi

log ""
log "Résultat : $PASS réussis, $FAIL échoués, $WARN avertissements"
(( FAIL == 0 ))
