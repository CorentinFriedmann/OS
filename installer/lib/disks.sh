# shellcheck shell=bash
# NOVA OS — installateur : détection et préparation des disques.
#
# RÈGLE DE SÉCURITÉ ABSOLUE : en mode « à côté de Windows », Nova ne modifie,
# ne redimensionne et ne formate JAMAIS une partition existante. Il crée une
# nouvelle partition dans l'espace libre (préparé depuis Windows) et réutilise
# la partition EFI existante sans la formater. Une sauvegarde de la table des
# partitions est faite avant toute écriture.

ESP_GUID=c12a7328-f81f-11d2-ba4b-00a0c93ec93b
MSR_GUID=e3c9e316-0b5c-4db8-817d-f92df00215ae
LINUX_ROOT_TYPE=8304   # « Linux x86-64 root (/) » pour sgdisk
export MIN_FREE_GIB=${NOVA_MIN_FREE_GIB:-30}
BTRFS_OPTS="noatime,compress=zstd:1"
SUBVOLUMES=("@:/" "@home:/home" "@log:/var/log" "@cache:/var/cache" "@tmp:/var/tmp" "@snapshots:/.snapshots" "@ollama:/var/lib/ollama")

settle() {
  partprobe "$1" >/dev/null 2>&1 || partx -u "$1" >/dev/null 2>&1 || true
  command -v udevadm >/dev/null && udevadm settle >/dev/null 2>&1
  sleep 1
}

# Disque qui porte le support d'installation (à exclure de la liste)
live_disk() {
  local src
  src=$(findmnt -no SOURCE /run/archiso/bootmnt 2>/dev/null || true)
  [[ -n "$src" ]] && lsblk -npdo PKNAME "$src" 2>/dev/null | head -n1
}

# Lignes « /dev/nvme0n1|512110190592|Samsung SSD 980 » des disques installables
disk_list() {
  local live name size type ro model
  live=$(live_disk)
  while read -r name size type ro model; do
    [[ "$type" == disk && "$ro" == 0 ]] || continue
    [[ "$name" == "$live" ]] && continue
    [[ "$name" == /dev/zram* || "$name" == /dev/sr* ]] && continue
    printf '%s|%s|%s\n' "$name" "$size" "${model:-disque}"
  done < <(lsblk -dbnpo NAME,SIZE,TYPE,RO,MODEL 2>/dev/null)
}

disk_partitions() { lsblk -lnpo NAME,TYPE "$1" 2>/dev/null | awk '$2 == "part" { print $1 }'; }
part_type() { blkid -p -o value -s PART_ENTRY_TYPE "$1" 2>/dev/null | tr 'A-F' 'a-f'; }
part_fstype() { blkid -p -o value -s TYPE "$1" 2>/dev/null; }
part_number() { blkid -p -o value -s PART_ENTRY_NUMBER "$1" 2>/dev/null; }
sector_size() { cat "/sys/class/block/$(basename "$1")/queue/logical_block_size" 2>/dev/null || echo 512; }
human() { numfmt --to=iec-i --suffix=o --format='%.1f' "$1" 2>/dev/null || echo "$1 octets"; }

disk_esp() {
  local part
  for part in $(disk_partitions "$1"); do
    [[ "$(part_type "$part")" == "$ESP_GUID" ]] && { echo "$part"; return 0; }
  done
  return 1
}

# Code 0 si Windows semble présent sur le disque ; affiche les indices trouvés
disk_windows_signs() {
  local part type fstype found=1
  for part in $(disk_partitions "$1"); do
    type=$(part_type "$part")
    fstype=$(part_fstype "$part")
    if [[ "$type" == "$MSR_GUID" ]]; then echo "partition réservée Microsoft ($part)"; found=0; fi
    if [[ "$fstype" == ntfs ]]; then echo "partition NTFS $part"; found=0; fi
    if [[ "$fstype" == BitLocker ]]; then echo "partition chiffrée BitLocker $part"; found=0; fi
  done
  return $found
}

disk_has_bitlocker() {
  local part
  for part in $(disk_partitions "$1"); do
    [[ "$(part_fstype "$part")" == BitLocker ]] && return 0
  done
  return 1
}

# Plus grande zone libre : « début fin secteurs » (secteurs logiques, bornes incluses)
disk_largest_free() {
  LC_ALL=C sfdisk -F "$1" 2>/dev/null | awk '
    $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ && $3 ~ /^[0-9]+$/ {
      if ($3 > best) { best = $3; line = $1 " " $2 " " $3 }
    }
    END { if (line != "") print line }'
}

free_bytes() {
  local region sectors
  region=$(disk_largest_free "$1") || true
  sectors=$(awk '{print $3}' <<< "$region")
  echo $(( ${sectors:-0} * $(sector_size "$1") ))
}

# Espace libre (Mo) sur une partition EFI existante, lu SANS la monter (mtools)
esp_free_mb() {
  local esp=$1 tmp avail
  if command -v mdir >/dev/null; then
    avail=$(MTOOLS_SKIP_CHECK=1 mdir -i "$esp" ::/ 2>/dev/null | awk '/bytes free/ { gsub(/[^0-9]/, "", $0); print int($0 / 1048576) }')
    [[ -n "$avail" ]] && { echo "$avail"; return; }
  fi
  tmp=$(mktemp -d)
  if mount -o ro "$esp" "$tmp" 2>/dev/null; then
    avail=$(df --output=avail -B1M "$tmp" | tail -n1 | tr -d ' ')
    umount "$tmp"
  fi
  rmdir "$tmp"
  echo "${avail:-0}"
}

backup_partition_table() {
  local disk=$1 backup
  backup="/tmp/nova-gpt-$(basename "$disk")-$(date +%Y%m%d-%H%M%S).bin"
  sgdisk --backup="$backup" "$disk" >/dev/null
  echo "$backup"
}

# Crée la partition Nova dans la plus grande zone libre ; affiche son chemin.
create_partition_in_free() {
  local disk=$1 region start end before after new
  region=$(disk_largest_free "$disk") || true
  [[ -n "$region" ]] || { echo "aucun espace libre" >&2; return 1; }
  read -r start end _ <<< "$region"
  before=$(disk_partitions "$disk" | sort)
  sgdisk -a 2048 -n "0:${start}:${end}" -t "0:${LINUX_ROOT_TYPE}" -c "0:Nova OS" "$disk" >/dev/null
  settle "$disk"
  after=$(disk_partitions "$disk" | sort)
  new=$(comm -13 <(echo "$before") <(echo "$after"))
  [[ $(wc -l <<< "$new") -eq 1 && -n "$new" ]] || { echo "partition créée introuvable" >&2; return 1; }
  echo "$new"
}

# Mode « effacer tout le disque » : EFI (1 Gio) + racine Nova
wipe_and_partition() {
  local disk=$1
  wipefs -af "$disk" >/dev/null
  sgdisk --zap-all "$disk" >/dev/null
  sgdisk -a 2048 -n 1:0:+1G -t 1:ef00 -c 1:"EFI" -n "2:0:0" -t "2:${LINUX_ROOT_TYPE}" -c 2:"Nova OS" "$disk" >/dev/null
  settle "$disk"
  local parts
  mapfile -t parts < <(disk_partitions "$disk")
  [[ ${#parts[@]} -eq 2 ]] || { echo "partitionnement inattendu" >&2; return 1; }
  echo "${parts[0]} ${parts[1]}"
}

format_root() { mkfs.btrfs -f -L "NovaOS" "$1" >/dev/null; }
format_esp() { mkfs.fat -F 32 -n NOVA_EFI "$1" >/dev/null; }

create_subvolumes() {
  local root=$1 mnt=$2 entry
  mkdir -p "$mnt"
  mount "$root" "$mnt"
  for entry in "${SUBVOLUMES[@]}"; do
    btrfs subvolume create "$mnt/${entry%%:*}" >/dev/null
  done
  umount "$mnt"
}

mount_target() {
  local root=$1 esp=$2 mnt=$3 entry name path
  mount -o "subvol=@,${BTRFS_OPTS}" "$root" "$mnt"
  for entry in "${SUBVOLUMES[@]:1}"; do
    name=${entry%%:*}
    path=${entry#*:}
    mkdir -p "$mnt$path"
    mount -o "subvol=${name},${BTRFS_OPTS}" "$root" "$mnt$path"
  done
  mkdir -p "$mnt/boot/efi"
  mount "$esp" "$mnt/boot/efi"
}

unmount_target() {
  local mnt=$1
  sync
  umount -R "$mnt" 2>/dev/null || umount -lR "$mnt" 2>/dev/null || true
}
