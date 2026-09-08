#!/usr/bin/env bash
# ┌───────────────────────────────────────────────────────────────────────┐
# │  WEEKLY ROUTINE — just run:  ./update.sh                               │
# │  1. It grabs the latest tool + form (no conflicts, ever).             │
# │  2. It pops the form open in Finder.                                  │
# │  3. You drag that file into Google Drive (upload as a new version).   │
# └───────────────────────────────────────────────────────────────────────┘
#
# Local copies of the generated files regenerate, so we just discard them and
# fast-forward to origin's latest. Nothing you've hand-authored is touched.

set -uo pipefail
cd "$(dirname "$0")"

FORM="templates/campaign-plan/campaign-plan-form.html"
branch="$(git rev-parse --abbrev-ref HEAD)"

echo "↻ Getting the latest '$branch' …"
git fetch origin "$branch" --quiet
git reset --hard "origin/$branch" --quiet

echo
echo "✅ You're up to date:  $(git log --oneline -1)"
echo

# Reveal the form in Finder (macOS) so the only thing left is to drag it to Drive.
if command -v open >/dev/null 2>&1; then
  open -R "$FORM" 2>/dev/null && echo "📂 Finder just opened with the form highlighted."
fi

echo
echo "────────────────────────────────────────────────────────────"
echo "  ONE THING LEFT:  drag this file into Google Drive"
echo "  (right-click the existing file in Drive → Manage versions →"
echo "   Upload new version, so the team's link stays the same):"
echo
echo "    $(pwd)/$FORM"
echo "────────────────────────────────────────────────────────────"
