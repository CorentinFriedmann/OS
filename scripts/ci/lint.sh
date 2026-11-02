#!/usr/bin/env bash
# Vérifications statiques du dépôt : scripts shell (shellcheck), Python, Lua, JSON.
#   scripts/ci/lint.sh   (SHELLCHECK=/chemin/shellcheck pour une autre version)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
SHELLCHECK=${SHELLCHECK:-shellcheck}
status=0
fail() { echo "✗ $*"; status=1; }

echo "== Scripts shell (shellcheck $("$SHELLCHECK" --version | awk '/^version/ {print $2}'))"
count=0
while IFS= read -r -d '' file; do
  case "$file" in
    *.sh) ;;
    *) head -n1 "$file" | grep -qE '^#!.*(/|env )bash' || continue ;;
  esac
  count=$((count + 1))
  # depuis le dossier du script : les « source » relatifs sont résolus comme à l'exécution
  (cd "$(dirname "$file")" && "$SHELLCHECK" -x -S style "$(basename "$file")") || fail "$file"
done < <(find . -path ./.git -prune -o -path ./out -prune -o -path ./work -prune -o -type f -print0 | sort -z)
echo "  $count scripts vérifiés"

echo "== Python (compilation)"
while IFS= read -r -d '' file; do
  python3 - "$file" <<'PY' || fail "$file"
import ast, sys
ast.parse(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1])
PY
done < <(find . -path ./.git -prune -o -type f -name '*.py' -print0)
for file in desktop/bin/nova-keybinds assistant/bin/nova assistant/bin/nova-assistant; do
  [[ -f "$file" ]] || continue
  head -n1 "$file" | grep -q python || continue
  python3 -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$file" || fail "$file"
done

echo "== Lua (syntaxe)"
LUAC=$(command -v luac5.4 || command -v luac || true)
if [[ -n "$LUAC" ]]; then
  while IFS= read -r -d '' file; do
    "$LUAC" -p "$file" || fail "$file"
  done < <(find desktop -type f -name '*.lua' -print0)
else
  echo "  (luac absent : ignoré)"
fi

echo "== JSON"
while IFS= read -r -d '' file; do
  python3 -m json.tool "$file" >/dev/null || fail "$file"
done < <(find . -path ./.git -prune -o -type f -name '*.json' -print0)

(( status == 0 )) && echo "✓ Tout est propre"
exit "$status"
