#!/usr/bin/env bash
# ┌───────────────────────────────────────────────────────────────────────┐
# │  REFRESH THE PICKER DATA —  run:  ./refresh.sh                         │
# │  Use when the form's search results look stale (new shows / segments  │
# │  from FreeWheel aren't showing up). It pulls fresh FreeWheel data,     │
# │  rebuilds the form, saves it so the whole team stays current, then     │
# │  points you at the form to upload to Drive.                           │
# │  Needs your FreeWheel login in .env. Takes a few minutes (big sync).  │
# └───────────────────────────────────────────────────────────────────────┘
set -uo pipefail
cd "$(dirname "$0")"
FORM="templates/campaign-plan/campaign-plan-form.html"
branch="$(git rev-parse --abbrev-ref HEAD)"

echo "↻ 1/3  Getting the latest code first…"
git fetch origin "$branch" --quiet
git reset --hard "origin/$branch" --quiet

echo "🔄 2/3  Pulling fresh FreeWheel data + rebuilding the form (a few minutes)…"
if ! promo-ops refresh-form; then
  echo
  echo "❌ Refresh failed — most likely your FreeWheel login isn't set in .env."
  echo "   Check FREEWHEEL_USERNAME / FREEWHEEL_PASSWORD in .env, then re-run ./refresh.sh"
  exit 1
fi

echo "💾 3/3  Saving the refreshed data so the whole team gets it…"
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "refresh: pull latest FreeWheel picker data (shows / segments / channels)"
  if git push origin "$branch"; then echo "   pushed to origin."; else
    echo "   (couldn't push — data still refreshed locally; you can still upload the form.)"; fi
else
  echo "   nothing changed — the data was already current."
fi

echo
if command -v open >/dev/null 2>&1; then open -R "$FORM" 2>/dev/null && echo "📂 Finder opened with the form highlighted."; fi
echo "✅ Done. Upload this form to Google Drive (right-click in Drive → Manage versions → Upload new version):"
echo "    $(pwd)/$FORM"
