#!/usr/bin/env bash
# CI : publie une version de Nova OS sur GitHub Releases.
#  - release « nova-VERSION » : l'ISO (découpée si elle dépasse 2 Gio), SHA256SUMS et
#    les captures du test en machine virtuelle
#  - release « repo » (permanente) : le dépôt pacman [nova], utilisé par les systèmes
#    installés pour leurs mises à jour (Server = …/releases/download/repo)
# Nécessite gh (GH_TOKEN) et GITHUB_REPOSITORY, GITHUB_SHA, NOVA_VERSION.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
: "${NOVA_VERSION:?}" "${GITHUB_SHA:?}" "${GITHUB_REPOSITORY:?}"
export GH_REPO="$GITHUB_REPOSITORY"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# --- 1. Dépôt pacman [nova] ---------------------------------------------------------------
mkdir "$STAGE/repo"
cp -L out/repo/*.pkg.tar.zst "$STAGE/repo/"
for db in nova.db nova.files; do
  cp -L "out/repo/$db" "$STAGE/repo/$db"              # copies réelles, pas de liens
  cp -L "out/repo/$db.tar.gz" "$STAGE/repo/$db.tar.gz"
done
if ! gh release view repo >/dev/null 2>&1; then
  gh release create repo --prerelease --target "$GITHUB_SHA" --title "Dépôt pacman [nova]" \
    --notes "Paquets de Nova OS pour les mises à jour des systèmes installés (pacman). Mis à jour automatiquement à chaque construction : ne pas supprimer."
fi
# Les paquets d'abord, la base ensuite : la base ne pointe jamais vers un paquet absent
gh release upload repo "$STAGE"/repo/*.pkg.tar.zst --clobber
gh release upload repo "$STAGE"/repo/nova.db "$STAGE"/repo/nova.files "$STAGE"/repo/*.tar.gz --clobber
# Anciennes versions des paquets : plus référencées par la base, retirées
current=$(cd "$STAGE/repo" && ls)
gh release view repo --json assets --jq '.assets[].name' | while read -r name; do
  grep -qxF "$name" <<< "$current" || gh release delete-asset repo "$name" --yes
done
echo "✓ Dépôt [nova] à jour : https://github.com/$GITHUB_REPOSITORY/releases/tag/repo"

# --- 2. ISO ---------------------------------------------------------------------------------
iso=$(find out/iso -maxdepth 1 -name '*.iso' | head -n1)
[[ -n "$iso" ]] || { echo "Aucune ISO dans out/iso" >&2; exit 1; }
name=$(basename "$iso")
size=$(stat -c %s "$iso")
mkdir "$STAGE/iso"
split_note=""
if (( size >= ${NOVA_ASSET_LIMIT:-2147483648} )); then
  # Limite de GitHub : 2 Gio par fichier → ISO découpée en morceaux à recoller
  split -b "${NOVA_SPLIT_SIZE:-1900M}" -d -a 1 "$iso" "$STAGE/iso/$name.part"
  parts=$(cd "$STAGE/iso" && find . -name "$name.part*" -printf '%f\n' | sort | sed ':a;N;$!ba;s/\n/ + /g')
  split_note=$(cat <<NOTE

> [!IMPORTANT]
> L'image dépasse la limite de 2 Gio par fichier de GitHub : elle est en plusieurs morceaux.
> Télécharge-les tous, puis recolle-les :
> - Windows (invite de commandes) : \`copy /b $parts $name\`
> - Linux / macOS : \`cat $name.part* > $name\`
NOTE
)
else
  ln "$iso" "$STAGE/iso/$name" 2>/dev/null || cp "$iso" "$STAGE/iso/$name"
fi
cp out/iso/SHA256SUMS "$STAGE/iso/"
if [[ -d out/vm ]]; then
  cp out/vm/*.png "$STAGE/iso/" 2>/dev/null || true
  cp out/vm/rapport.txt "$STAGE/iso/test-vm-rapport.txt" 2>/dev/null || true
fi

report="(test en machine virtuelle non lancé)"
[[ -f out/vm/rapport.txt ]] && report=$(cat out/vm/rapport.txt)
cat > "$STAGE/notes.md" <<NOTES
## Nova OS $NOVA_VERSION

Image de la clé USB d'essai et d'installation : **$name** ($(numfmt --to=iec-i --suffix=o "$size")).
$split_note

- Installation à côté de Windows, pas à pas : [docs/installation.md](https://github.com/$GITHUB_REPOSITORY/blob/$GITHUB_SHA/docs/installation.md)
- Vérifier l'image après téléchargement : \`sha256sum -c SHA256SUMS\` (Linux) ou \`certutil -hashfile $name SHA256\` (Windows)
- Captures d'écran prises pendant le test automatique : fichiers \`*.png\` ci-dessous

<details><summary>Test automatique : installation à côté de Windows dans une machine virtuelle</summary>

\`\`\`
$report
\`\`\`
</details>

Construit depuis le commit $GITHUB_SHA.
NOTES

tag="nova-$NOVA_VERSION"
gh release create "$tag" "$STAGE"/iso/* --target "$GITHUB_SHA" --title "Nova OS $NOVA_VERSION" \
  --notes-file "$STAGE/notes.md" --latest
echo "✓ Publié : https://github.com/$GITHUB_REPOSITORY/releases/tag/$tag"
