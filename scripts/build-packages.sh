#!/usr/bin/env bash
# Construit les paquets Nova OS (makepkg) et le dépôt pacman [nova].
# À lancer sur Arch Linux, en utilisateur normal (makepkg refuse root).
#   scripts/build-packages.sh [dossier de sortie]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/out/repo}"
count="$(git -C "$ROOT" rev-list --count HEAD 2>/dev/null || echo 0)"
export NOVA_PKGVER="${NOVA_PKGVER:-$(date -u +%Y.%m.%d).$count}"
mkdir -p "$OUT"
for pkg in nova-branding nova-desktop nova-performance nova-assistant nova-installer; do
  echo "==> $pkg $NOVA_PKGVER"
  (cd "$ROOT/packages/$pkg" && PKGDEST="$OUT" makepkg --force --cleanbuild --nodeps --noconfirm)
done
cd "$OUT"
rm -f nova.db* nova.files*
repo-add -q nova.db.tar.gz ./*.pkg.tar.zst
echo "✓ Dépôt [nova] prêt dans $OUT"
