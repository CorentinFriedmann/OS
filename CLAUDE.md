# Nova OS — notes pour Claude Code

Distribution personnelle basée sur Arch Linux (optimisée façon CachyOS), bureau Hyprland
« verre minimaliste » (palette : branding/palette.json), assistant IA hybride « Nova » (Ollama en local + Claude). Tout est en français
(code commenté, interface, docs) et l'utilisateur est tutoyé.

## Machine cible
PC portable **Acer Aspire 5 A515-57** (Intel 12ᵉ gén. Alder Lake, graphique Iris Xe/UHD
intégré), en **dual-boot avec Windows**. Ne jamais modifier, redimensionner ni formater une
partition Windows.

## Organisation
- `branding/` : logo, fonds d'écran (générés par `branding/tools/`), thèmes GRUB/Plymouth/SDDM
- `desktop/` : config Hyprland **en Lua** (`hypr/nova/*.lua`, API `hl.*`, Hyprland ≥ 0.57), Waybar, scripts `nova-*`
- `assistant/` : Nova IA (Python, `nova_ai/`), tests pytest dans `assistant/tests`
- `system/` : sysctl, udev, modes de performance (`nova-mode`), dépôts CachyOS
- `installer/` : `nova-install` (bash + gum), tests sur périphériques loop
- `packages/` : PKGBUILD des paquets nova-* ; `archiso/` : surcouche de l'image live
- `scripts/` : construction (`build-packages.sh`, `build-iso.sh`) et CI (`scripts/ci/`)
- `tests/vm/` : test complet en VM (QEMU/OVMF, installation à côté d'un faux Windows)

## Vérifier avant de committer
- `scripts/ci/lint.sh` (shellcheck 0.11, Python, Lua, JSON)
- `cd assistant && python -m pytest -q -W error`
- `sudo installer/tests/test-partitioning.sh` (root, disques virtuels)

## CI (.github/workflows/build.yml)
Push sur `main` → tests → paquets + ISO (conteneur Arch) → test en VM → release
`nova-AAAA.MM.JJ.N` + dépôt pacman `[nova]` (release `repo`). Journaux de chaque job dans
la release `ci-logs` (fichiers `tests--*`, `iso--*`). Les modifications `*.md` et `docs/`
ne relancent pas la CI.
