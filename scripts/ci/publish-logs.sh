#!/usr/bin/env bash
# CI : dépose les journaux d'un job dans la release « ci-logs » (remplacés à chaque
# construction), pour les consulter même quand la construction échoue.
#   scripts/ci/publish-logs.sh NOM_DU_JOB
# Variables : GH_TOKEN, GITHUB_*, JOB_STATUS et STEPS_JSON (fournis par le workflow).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
job=${1:?nom du job}
export GH_REPO="$GITHUB_REPOSITORY"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

{
  echo "job : $job"
  echo "statut : ${JOB_STATUS:-inconnu}"
  echo "commit : ${GITHUB_SHA:-?} (${GITHUB_REF_NAME:-?})"
  echo "exécution : ${GITHUB_SERVER_URL:-https://github.com}/$GITHUB_REPOSITORY/actions/runs/${GITHUB_RUN_ID:-?}"
  echo "date : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "étapes : ${STEPS_JSON:-aucune}"
} > "$stage/$job--statut.txt"

shopt -s nullglob
for file in out/logs/* out/iso/SHA256SUMS out/vm/*.txt out/vm/*.log out/vm/*.png out/vm/grub.cfg out/vm/pacman.conf out/vm/live/*; do
  [[ -f "$file" && -r "$file" ]] || continue
  flat=${file#out/}
  cp "$file" "$stage/$job--${flat//\//-}"
done

if ! gh release view ci-logs >/dev/null 2>&1; then
  gh release create ci-logs --prerelease --target "${GITHUB_SHA:-main}" --title "Journaux de la CI" \
    --notes "Journaux et captures de la dernière construction de chaque job (remplacés à chaque fois)." || true
fi
# Les fichiers de ce job laissés par une construction précédente sont retirés d'abord
fresh=$(cd "$stage" && ls)
gh release view ci-logs --json assets --jq '.assets[].name' 2>/dev/null | while read -r name; do
  [[ "$name" == "$job--"* ]] || continue
  grep -qxF "$name" <<< "$fresh" || gh release delete-asset ci-logs "$name" --yes
done
gh release upload ci-logs "$stage"/* --clobber
echo "✓ Journaux : https://github.com/$GITHUB_REPOSITORY/releases/tag/ci-logs"
