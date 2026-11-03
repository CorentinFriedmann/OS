#!/usr/bin/env bash
# Régénère toutes les images de Nova OS à partir des sources (SVG + générateur).
# Les fichiers produits sont versionnés : la construction de l'ISO n'a donc
# besoin ni de Python ni de numpy.
#
# Dépendances : python3 + numpy + Pillow, rsvg-convert (librsvg).
# Usage : branding/tools/build-assets.sh [python]
set -euo pipefail

PY="${1:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="$ROOT/tools/gen_wallpaper.py"
LOGO="$ROOT/logo/nova.svg"

command -v rsvg-convert >/dev/null || { echo "rsvg-convert introuvable (paquet librsvg)" >&2; exit 1; }

echo "→ Fonds d'écran"
"$PY" "$GEN" --width 3840 --height 2160 --out "$ROOT/wallpapers/nova-verre.jpg"
"$PY" "$GEN" --width 3840 --height 2160 --variant lock --out "$ROOT/wallpapers/nova-verre-lock.jpg"
"$PY" "$GEN" --width 3840 --height 2160 --seed 1338 --out "$ROOT/wallpapers/nova-verre-2.jpg"

echo "→ Arrière-plan GRUB (PNG non progressif, 1920x1080)"
"$PY" "$GEN" --width 1920 --height 1080 --variant lock --out "$ROOT/grub/nova/background.png"

echo "→ Logos PNG"
for size in 32 64 128 256 512; do
  rsvg-convert -w "$size" -h "$size" "$LOGO" -o "$ROOT/logo/nova-$size.png"
done

echo "→ Thème GRUB (surbrillance, icônes) et animation Plymouth"
"$PY" "$ROOT/tools/gen_boot_assets.py"

echo "✓ Images régénérées"
