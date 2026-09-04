#!/usr/bin/env bash
# One-command update for the promo-ops repo.
#
# Local copies of the generated files (the campaign-plan form + the synced-snapshot CSVs)
# are throwaway — they regenerate — so the stash/pop dance keeps conflicting on them.
# This just discards local changes to tracked files and fast-forwards to origin's latest.
# Nothing you've hand-authored is touched; only auto-generated files are reset.
#
#   Usage:  ./update.sh        (or:  bash update.sh)

set -euo pipefail

# Run from the repo root no matter where this is called from.
cd "$(dirname "$0")"

branch="$(git rev-parse --abbrev-ref HEAD)"
echo "↻ Updating '$branch' from origin …"

git fetch origin "$branch"
git reset --hard "origin/$branch"

echo
echo "✅ Up to date:  $(git log --oneline -1)"
echo "→ Next: re-upload templates/campaign-plan/campaign-plan-form.html to Drive (as a new version)."
