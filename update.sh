#!/usr/bin/env bash
# ┌───────────────────────────────────────────────────────────────────────┐
# │  WEEKLY ROUTINE — just run:  ./update.sh                               │
# │  It grabs the latest tool + form, then TELLS YOU whether the campaign │
# │  form actually changed:                                               │
# │    • changed  → it opens Finder + says "upload this to Drive"          │
# │    • no change → it says "nothing to upload" so you can stop.          │
# └───────────────────────────────────────────────────────────────────────┘

set -uo pipefail
cd "$(dirname "$0")"

FORM="templates/campaign-plan/campaign-plan-form.html"
branch="$(git rev-parse --abbrev-ref HEAD)"

# Remember the form's fingerprint BEFORE we update, so we can tell if it changed.
before="$(git hash-object "$FORM" 2>/dev/null || echo none)"

echo "↻ Getting the latest '$branch' …"
git fetch origin "$branch" --quiet
git reset --hard "origin/$branch" --quiet

after="$(git hash-object "$FORM" 2>/dev/null || echo none)"

echo
echo "✅ You're up to date:  $(git log --oneline -1)"
echo

if [ "$before" = "$after" ]; then
  echo "👍 The campaign form did NOT change — nothing to upload. You're done."
  exit 0
fi

# The form changed → make the upload as easy as possible.
if command -v open >/dev/null 2>&1; then
  open -R "$FORM" 2>/dev/null && echo "📂 Finder opened with the form highlighted."
fi
echo
echo "────────────────────────────────────────────────────────────"
echo "  📢 NEW FORM — upload it to Google Drive:"
echo "  (right-click the file in Drive → Manage versions →"
echo "   Upload new version, so the team's link stays the same)"
echo
echo "    $(pwd)/$FORM"
echo "────────────────────────────────────────────────────────────"
