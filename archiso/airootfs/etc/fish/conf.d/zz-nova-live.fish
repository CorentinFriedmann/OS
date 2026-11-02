# Session live : le bureau démarre automatiquement sur la première console
if status is-login; and test (tty) = /dev/tty1; and test (id -u) -eq 1000; and not set -q WAYLAND_DISPLAY
    if command -q start-hyprland
        exec start-hyprland
    else
        exec Hyprland
    end
end
