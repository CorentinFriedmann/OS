# shellcheck shell=bash
# NOVA OS — installateur : paquets, configuration du système, démarrage.

NOVA_PKG_DIR=${NOVA_PKG_DIR:-${NOVA_LIB:-/usr/lib/nova-installer}/packages}
NOVA_REPO_URL=${NOVA_REPO_URL:-https://github.com/CorentinFriedmann/OS/releases/download/repo}
KERNEL_CMDLINE="quiet splash loglevel=3 rd.udev.log_level=3 vt.global_cursor_default=0 nowatchdog nmi_watchdog=0 zswap.enabled=0 split_lock_detect=off"

read_list() { grep -vE '^[[:space:]]*(#|$)' "$NOVA_PKG_DIR/$1.txt"; }

cpu_vendor() {
  case "$(grep -m1 vendor_id /proc/cpuinfo 2>/dev/null | awk '{print $3}')" in
    GenuineIntel) echo intel ;;
    AuthenticAMD) echo amd ;;
    *) echo other ;;
  esac
}

gpu_vendors() {
  lspci -nn 2>/dev/null | grep -Ei 'vga|3d|display' | grep -oE '\[(8086|1002|10de):' | sort -u | while read -r id; do
    case "$id" in
      "[8086:") echo intel ;;
      "[1002:") echo amd ;;
      "[10de:") echo nvidia ;;
    esac
  done
}

is_laptop() { compgen -G "/sys/class/power_supply/BAT*" >/dev/null; }

# Listes à installer selon le matériel et les profils choisis (une par ligne)
package_lists() {
  local profiles=$1 gpu
  printf '%s\n' base desktop nova
  [[ ",$profiles," == *",jeux,"* ]] && echo gaming
  [[ ",$profiles," == *",dev,"* ]] && echo dev
  [[ ",$profiles," == *",multimedia,"* ]] && echo multimedia
  case "$(cpu_vendor)" in
    intel) echo cpu-intel ;;
    amd) echo cpu-amd ;;
  esac
  [[ "$(systemd-detect-virt 2>/dev/null)" == oracle ]] && echo vm-virtualbox
  for gpu in ${NOVA_GPUS:-$(gpu_vendors)}; do echo "gpu-$gpu"; done
}

# Construit la liste finale ; les paquets absents des dépôts sont signalés et ignorés.
resolve_packages() {
  local conf=$1 profiles=$2 wanted available list
  wanted=$(for list in $(package_lists "$profiles"); do read_list "$list"; done | sort -u)
  available=$(pacman --config "$conf" -Sl 2>/dev/null | awk '{print $2}' | sort -u)
  if [[ -z "$available" ]]; then
    echo "$wanted"
    return
  fi
  local missing
  missing=$(comm -23 <(echo "$wanted") <(echo "$available") | tr '\n' ' ')
  [[ -n "${missing// }" ]] && ui_warn "Paquets indisponibles ignorés : $missing" && echo "Paquets ignorés : $missing" >>"$NOVA_LOG"
  comm -12 <(echo "$wanted") <(echo "$available")
}

# pacman.conf pour l'installation (« live » : dépôt Nova local) ou le système installé
make_pacman_conf() {
  local kind=$1 out=$2 tmp
  tmp=$(mktemp -d)
  mkdir -p "$tmp/etc"
  cp /etc/pacman.conf "$tmp/etc/pacman.conf"
  /usr/lib/nova/setup-cachyos-repos --root "$tmp" >>"$NOVA_LOG" 2>&1
  if [[ "$kind" == target ]]; then
    sed -i "/^\[nova\]/,/^\[/ s#^Server = .*#Server = ${NOVA_REPO_URL}#" "$tmp/etc/pacman.conf"
  fi
  install -m 644 "$tmp/etc/pacman.conf" "$out"
  rm -rf "$tmp"
}

# Clé live : la liste des miroirs Arch est remplie au démarrage par reflector.
# On attend qu'il ait fini, avec le miroir mondial d'Arch en secours.
ensure_mirrors() {
  [[ -d /run/archiso ]] || return 0
  local _
  for _ in $(seq 1 45); do
    [[ "$(systemctl show -p ActiveState --value reflector.service 2>/dev/null)" == activating ]] || break
    sleep 2
  done
  if ! grep -qE '^[[:space:]]*Server[[:space:]]*=' /etc/pacman.d/mirrorlist 2>/dev/null; then
    # shellcheck disable=SC2016 # $repo et $arch sont remplacés par pacman
    echo 'Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch' >> /etc/pacman.d/mirrorlist
    echo "Miroir de secours ajouté (reflector n'a rien trouvé)" >>"$NOVA_LOG"
  fi
}

install_base_system() {
  local mnt=$1 profiles=$2 conf packages
  conf=/tmp/nova-pacman.conf
  ensure_mirrors
  make_pacman_conf live "$conf"
  pacman --config "$conf" -Sy >>"$NOVA_LOG" 2>&1 || true
  mapfile -t packages < <(resolve_packages "$conf" "$profiles")
  echo "Paquets : ${packages[*]}" >>"$NOVA_LOG"
  ui_run "Installation de ${#packages[@]} paquets (quelques minutes)" pacstrap -C "$conf" "$mnt" "${packages[@]}"
  make_pacman_conf target "$mnt/etc/pacman.conf"
  genfstab -U "$mnt" > "$mnt/etc/fstab"
  # snapper : pas de « subvolid » figé dans fstab (indispensable pour revenir en arrière)
  sed -i 's/,subvolid=[0-9]*//' "$mnt/etc/fstab"
}

# Script exécuté DANS le nouveau système (arch-chroot)
write_configure_script() {
  local out=$1
  {
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
    declare -p NOVA_MODE NOVA_HOSTNAME NOVA_USER NOVA_FULLNAME NOVA_PASSWORD NOVA_TIMEZONE NOVA_LOCALE \
      NOVA_KEYMAP NOVA_XKB_LAYOUT NOVA_XKB_VARIANT KERNEL_CMDLINE
    cat <<'BODY'
enable_unit() { systemctl list-unit-files "$1" >/dev/null 2>&1 && systemctl enable "$1" >/dev/null 2>&1 || true; }
set_grub() {  # set_grub CLÉ VALEUR
  if grep -qE "^#?$1=" /etc/default/grub; then
    sed -i -E "s|^#?$1=.*|$1=$2|" /etc/default/grub
  else
    echo "$1=$2" >> /etc/default/grub
  fi
}

echo "→ Langue, fuseau horaire, clavier"
ln -sf "/usr/share/zoneinfo/$NOVA_TIMEZONE" /etc/localtime
# Windows règle l'horloge matérielle en heure locale : on fait de même en dual-boot
if [[ "$NOVA_MODE" == dualboot ]]; then hwclock --systohc --localtime || true; else hwclock --systohc || true; fi
sed -i -e "s/^#\(${NOVA_LOCALE} UTF-8\)/\1/" -e 's/^#\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
locale-gen
echo "LANG=$NOVA_LOCALE" > /etc/locale.conf
echo "KEYMAP=$NOVA_KEYMAP" > /etc/vconsole.conf
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf <<EOF
Section "InputClass"
        Identifier "system-keyboard"
        MatchIsKeyboard "on"
        Option "XkbLayout" "$NOVA_XKB_LAYOUT"
        Option "XkbVariant" "$NOVA_XKB_VARIANT"
EndSection
EOF

echo "→ Nom de l'ordinateur et compte utilisateur"
echo "$NOVA_HOSTNAME" > /etc/hostname
cat > /etc/hosts <<EOF
127.0.0.1   localhost
::1         localhost
127.0.1.1   $NOVA_HOSTNAME.localdomain $NOVA_HOSTNAME
EOF
groups=wheel,video,input,audio
for g in gamemode docker vboxsf; do getent group "$g" >/dev/null && groups+=",$g"; done  # vboxsf : dossiers partagés VirtualBox
useradd -m -G "$groups" -s /usr/bin/fish -c "$NOVA_FULLNAME" "$NOVA_USER"
printf '%s:%s\n' "$NOVA_USER" "$NOVA_PASSWORD" | chpasswd
passwd -l root >/dev/null
echo '%wheel ALL=(ALL:ALL) ALL' > /etc/sudoers.d/10-wheel
chmod 440 /etc/sudoers.d/10-wheel
su - "$NOVA_USER" -c "LC_ALL=$NOVA_LOCALE xdg-user-dirs-update" || true

echo "→ Démarrage rapide et écran de démarrage"
mkdir -p /etc/mkinitcpio.conf.d
cat > /etc/mkinitcpio.conf.d/nova.conf <<'EOF'
HOOKS=(base systemd plymouth autodetect microcode modconf kms keyboard sd-vconsole block filesystems)
COMPRESSION="zstd"
EOF
plymouth-set-default-theme nova 2>/dev/null || true
mkinitcpio -P

echo "→ Instantanés automatiques (snapper)"
umount /.snapshots 2>/dev/null || true
rm -rf /.snapshots
snapper --no-dbus -c root create-config /
btrfs subvolume delete /.snapshots >/dev/null
mkdir /.snapshots
mount /.snapshots
chmod 750 /.snapshots
sed -i -e 's/^TIMELINE_CREATE=.*/TIMELINE_CREATE="no"/' -e 's/^NUMBER_LIMIT=.*/NUMBER_LIMIT="10"/' \
       -e 's/^NUMBER_LIMIT_IMPORTANT=.*/NUMBER_LIMIT_IMPORTANT="5"/' -e 's/^ALLOW_GROUPS=.*/ALLOW_GROUPS="wheel"/' \
       /etc/snapper/configs/root

echo "→ Menu de démarrage GRUB (Nova + Windows + instantanés)"
set_grub GRUB_DEFAULT saved
set_grub GRUB_TIMEOUT 5
set_grub GRUB_TIMEOUT_STYLE menu
set_grub GRUB_DISTRIBUTOR '"Nova"'
# Pas d'entrées techniques du micrologiciel (« … (EFI BootNext) ») : Windows est
# détecté par os-prober, le BIOS reste accessible par « Paramètres du micrologiciel »
set_grub GRUB_DISABLE_BOOTNEXT true
set_grub GRUB_CMDLINE_LINUX_DEFAULT "\"$KERNEL_CMDLINE\""
set_grub GRUB_DISABLE_OS_PROBER false
set_grub GRUB_GFXMODE auto
[[ -f /usr/share/grub/themes/nova/theme.txt ]] && set_grub GRUB_THEME '"/usr/share/grub/themes/nova/theme.txt"'
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Nova --recheck
if [[ "$NOVA_MODE" == erase ]]; then
  # Disque entier : copie de secours au chemin standard (jamais en dual-boot : c'est celui de Windows)
  grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable
fi
# Sous-menu des instantanés (grub-btrfs) en français
btrfs_conf=/etc/default/grub-btrfs/config
if [[ -f "$btrfs_conf" ]]; then
  if grep -qE '^#?GRUB_BTRFS_SUBMENUNAME=' "$btrfs_conf"; then
    sed -i -E 's|^#?GRUB_BTRFS_SUBMENUNAME=.*|GRUB_BTRFS_SUBMENUNAME="Instantanés Nova (retour en arrière)"|' "$btrfs_conf"
  else
    echo 'GRUB_BTRFS_SUBMENUNAME="Instantanés Nova (retour en arrière)"' >> "$btrfs_conf"
  fi
fi
grub-mkconfig -o /boot/grub/grub.cfg

echo "→ Services"
for unit in NetworkManager.service bluetooth.service sddm.service power-profiles-daemon.service \
            thermald.service fstrim.timer systemd-timesyncd.service snapper-cleanup.timer grub-btrfsd.service \
            nova-mode.service nova-firstboot.service ananicy-cpp.service docker.socket ollama.service \
            vboxservice.service; do
  enable_unit "$unit"
done
mkdir -p /etc/nova
echo equilibre > /etc/nova/mode
mkdir -p /var/lib/sddm
cat > /var/lib/sddm/state.conf <<EOF
[Last]
Session=/usr/share/wayland-sessions/hyprland.desktop
User=$NOVA_USER
EOF
chown -R sddm:sddm /var/lib/sddm 2>/dev/null || true
echo "✓ Configuration terminée"
BODY
  } > "$out"
  chmod 700 "$out"
}

configure_system() {
  local mnt=$1 status=0
  write_configure_script "$mnt/root/nova-configure.sh"
  ui_run "Configuration du système (langue, compte, démarrage, instantanés)" \
    arch-chroot "$mnt" /root/nova-configure.sh || status=$?
  # Le script contient le mot de passe : effacé dans tous les cas, même en cas d'échec
  shred -u "$mnt/root/nova-configure.sh" 2>/dev/null || rm -f "$mnt/root/nova-configure.sh"
  return "$status"
}
