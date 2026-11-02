# shellcheck shell=bash
# Faux disque « Windows 11 » pour les tests (périphérique loop ou disque de VM).
# Utilisé par test-partitioning.sh et par le test complet en VM (tests/vm/run.sh).

part() { echo "${1}p${2}"; }

# Disque façon Windows 11 après « Réduire le volume » : EFI, MSR, C: (NTFS), [trou], récupération
# make_windows_disk /dev/loopN TAILLE_DE_C
make_windows_disk() {
  local disk=$1 c_size=$2 loader
  sgdisk -a 2048 \
    -n 1:0:+100M -t 1:ef00 -c "1:EFI system partition" \
    -n 2:0:+16M -t 2:0c01 -c "2:Microsoft reserved partition" \
    -n 3:0:+"$c_size" -t 3:0700 -c "3:Basic data partition" \
    -n 4:-600M:0 -t 4:2700 -c "4:Windows RE" "$disk" >/dev/null
  partx -u "$disk" 2>/dev/null; sleep 1
  mkfs.fat -F 32 -n SYSTEM "$(part "$disk" 1)" >/dev/null
  MTOOLS_SKIP_CHECK=1 mmd -i "$(part "$disk" 1)" ::/EFI ::/EFI/Microsoft ::/EFI/Microsoft/Boot
  loader=$(mktemp)
  echo "chargeur Windows factice" > "$loader"
  MTOOLS_SKIP_CHECK=1 mcopy -i "$(part "$disk" 1)" "$loader" ::/EFI/Microsoft/Boot/bootmgfw.efi
  # Base de démarrage de Windows : os-prober exige BCD + bootmgfw.efi, comme sur un vrai Windows
  echo "base BCD factice" > "$loader"
  MTOOLS_SKIP_CHECK=1 mcopy -i "$(part "$disk" 1)" "$loader" ::/EFI/Microsoft/Boot/BCD
  rm -f "$loader"
  mkntfs -Q -F -L Windows "$(part "$disk" 3)" >/dev/null 2>&1
  mkntfs -Q -F -L Recovery "$(part "$disk" 4)" >/dev/null 2>&1
}

# Empreinte d'une partition : entièrement si petite (EFI, MSR), sinon début + fin
partition_fingerprint() {
  local p=$1 size
  size=$(blockdev --getsize64 "$p")
  if (( size <= 64 * 1048576 )); then
    sha256sum < "$p"
  else
    { dd if="$p" bs=1M count=32 status=none
      dd if="$p" bs=1M skip=$(( size / 1048576 - 32 )) count=32 status=none; } | sha256sum
  fi
}

# Empreinte de Windows : table des partitions 1-4 + contenu de chaque partition
windows_fingerprint() {
  local disk=$1 n
  for n in 1 2 3 4; do
    sgdisk -i "$n" "$disk" 2>/dev/null | grep -v '^Partition name'
    partition_fingerprint "$(part "$disk" "$n")"
  done
}
