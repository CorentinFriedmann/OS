# Session live : le bureau démarre automatiquement sur la première console.
# nova-live-session affiche un écran d'aide (au lieu d'un écran noir) s'il ne s'affiche pas.
if status is-login; and test (tty) = /dev/tty1; and test (id -u) -eq 1000; and not set -q WAYLAND_DISPLAY
    exec nova-live-session
end
