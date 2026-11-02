#!/usr/bin/env bash
# Tests de l'installateur sur de vrais disques virtuels (périphériques loop).
# Nécessite les droits root et : losetup sgdisk sfdisk mkfs.btrfs mkfs.fat mkntfs mtools blkid btrfs
#
# Scénarios :
#  A. dual-boot : disque « Windows » réaliste + espace libre → la partition Nova est créée
#     dans le trou, Windows reste intact au bit près, sauvegarde GPT faite
#  B. espace insuffisant → refus clair, AUCUNE écriture
#  C. disque entier → EFI 1 Gio + racine btrfs avec sous-volumes
#  D. --dry-run → aucune écriture
# Les vérifications sont des expressions évaluées plus tard par check() :
# shellcheck disable=SC2016,SC2034
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/nova-installer-test.XXXXXX")
LOOPS=()
PASS=0
FAIL=0

cleanup() {
  for mnt in "$WORK"/mnt*; do umount -R "$mnt" 2>/dev/null; done
  for loop in "${LOOPS[@]}"; do losetup -d "$loop" 2>/dev/null; done
  rm -rf "$WORK"
}
trap cleanup EXIT

ok() { echo "  ✓ $*"; PASS=$((PASS + 1)); }
ko() { echo "  ✗ $*"; FAIL=$((FAIL + 1)); }
check() { if eval "$2"; then ok "$1"; else ko "$1"; fi; }

new_disk() {  # new_disk nom taille
  truncate -s "$2" "$WORK/$1.img"
  local loop
  loop=$(losetup -f --show -P "$WORK/$1.img")
  LOOPS+=("$loop")
  echo "$loop"
}

# make_windows_disk, windows_fingerprint, part : faux disque Windows partagé avec le test en VM
# shellcheck source=fake-windows.sh
source "$(dirname "${BASH_SOURCE[0]}")/fake-windows.sh"

write_config() {  # write_config fichier disque mode
  cat > "$1" <<EOF
NOVA_DISK=$2
NOVA_MODE=$3
NOVA_USER=testeur
NOVA_FULLNAME="Testeur Nova"
NOVA_PASSWORD='mot de passe de test'
NOVA_CONFIRM=yes
EOF
}

installer() {  # installer config [options]
  local cfg=$1; shift
  NOVA_SKIP_UEFI_CHECK=1 NOVA_LOG="$WORK/install.log" NOVA_MNT="$WORK/mnt" NOVA_LIB="$HERE" \
    bash "$HERE/nova-install" --config "$cfg" "$@" </dev/null
}

[[ $EUID -eq 0 ]] || { echo "À lancer en root."; exit 1; }
mkdir -p "$WORK/mnt"

echo "A. Dual-boot à côté de Windows"
disk=$(new_disk windows 64G)
make_windows_disk "$disk" 20G
before=$(windows_fingerprint "$disk")
gap=$(sfdisk -F "$disk" | awk '$1 ~ /^[0-9]+$/ && $3 > 1000000 { print $1, $2 }')
write_config "$WORK/a.cfg" "$disk" dualboot
if installer "$WORK/a.cfg" --stop-after partition > "$WORK/a.out" 2>&1; then ok "installateur terminé sans erreur"; else ko "installateur en échec"; tail -20 "$WORK/a.out"; fi
check "Windows intact (table + contenu des 4 partitions)" '[[ "$(windows_fingerprint "$disk")" == "$before" ]]'
check "une 5e partition a été créée" '[[ -b "$(part "$disk" 5)" ]]'
new=$(part "$disk" 5)
read -r gap_start gap_end <<< "$gap"
pstart=$(blkid -p -o value -s PART_ENTRY_OFFSET "$new"); psize=$(blkid -p -o value -s PART_ENTRY_SIZE "$new")
check "elle est entièrement dans l'espace libre" '(( pstart >= gap_start && pstart + psize - 1 <= gap_end ))'
check "type « Linux x86-64 root »" '[[ "$(blkid -p -o value -s PART_ENTRY_TYPE "$new")" == 4f68bce3-e8cd-4db1-96e7-fbcaf984b709 ]]'
check "formatée en btrfs (étiquette NovaOS)" '[[ "$(blkid -p -o value -s TYPE "$new")" == btrfs && "$(blkid -p -o value -s LABEL "$new")" == NovaOS ]]'
subvols=""
mount "$new" "$WORK/mnt" && subvols=$(btrfs subvolume list "$WORK/mnt" | awk '{print $NF}' | sort | tr '\n' ' '); umount "$WORK/mnt"
check "sous-volumes @ @home @log @cache @tmp @snapshots @ollama" '[[ "$subvols" == "@ @cache @home @log @ollama @snapshots @tmp " ]]'
check "sauvegarde de la table des partitions" 'grep -q "Sauvegarde de la table des partitions" "$WORK/a.out" && compgen -G "/tmp/nova-gpt-$(basename "$disk")-*.bin" >/dev/null'
check "chargeur Windows toujours présent" 'MTOOLS_SKIP_CHECK=1 mdir -i "$(part "$disk" 1)" ::/EFI/Microsoft/Boot | grep -qi bootmgfw'
rm -f /tmp/nova-gpt-"$(basename "$disk")"-*.bin

echo "B. Espace libre insuffisant"
disk=$(new_disk small 32G)
make_windows_disk "$disk" 21G
before=$(sgdisk -p "$disk")
write_config "$WORK/b.cfg" "$disk" dualboot
if installer "$WORK/b.cfg" --stop-after partition > "$WORK/b.out" 2>&1; then ko "aurait dû refuser"; else ok "installation refusée"; fi
check "message clair (réduire le volume depuis Windows)" 'grep -q "Réduire le volume" "$WORK/b.out"'
check "table des partitions inchangée" '[[ "$(sgdisk -p "$disk")" == "$before" ]]'

echo "C. Disque entier"
disk=$(new_disk blank 40G)
write_config "$WORK/c.cfg" "$disk" erase
if installer "$WORK/c.cfg" --stop-after partition > "$WORK/c.out" 2>&1; then ok "installateur terminé sans erreur"; else ko "installateur en échec"; tail -20 "$WORK/c.out"; fi
check "partition EFI de 1 Gio en FAT32" '[[ "$(blkid -p -o value -s TYPE "$(part "$disk" 1)")" == vfat && "$(blockdev --getsize64 "$(part "$disk" 1)")" == 1073741824 ]]'
check "racine btrfs" '[[ "$(blkid -p -o value -s TYPE "$(part "$disk" 2)")" == btrfs ]]'
rm -f /tmp/nova-gpt-"$(basename "$disk")"-*.bin

echo "D. Simulation (--dry-run)"
disk=$(new_disk dry 64G)
make_windows_disk "$disk" 20G
before=$(windows_fingerprint "$disk")
write_config "$WORK/d.cfg" "$disk" dualboot
installer "$WORK/d.cfg" --dry-run > "$WORK/d.out" 2>&1
check "plan affiché" 'grep -q "à côté de Windows" "$WORK/d.out" && grep -q "Mode simulation" "$WORK/d.out"'
check "rien n'a été modifié" '[[ "$(windows_fingerprint "$disk")" == "$before" && ! -b "$(part "$disk" 5)" ]]'

echo
echo "Résultat : $PASS réussis, $FAIL échoués"
(( FAIL == 0 ))
