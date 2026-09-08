#!/usr/bin/env bash
# Background form watcher. Checks origin for a new campaign form and sends ONE Mac
# notification when there's a version you don't have yet. Read-only on your working tree —
# it never resets or regenerates anything, so it can't cause the pull conflicts the old job did.
# Installed via scripts/install_form_notifier.sh; runs on a schedule via launchd.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 0
REPO="$(pwd)"
FORM="templates/campaign-plan/campaign-plan-form.html"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
STATE="$REPO/logs/.form_last_notified"
mkdir -p "$REPO/logs"

git fetch origin "$branch" --quiet 2>/dev/null || exit 0     # offline -> quietly skip
local_hash="$(git hash-object "$FORM" 2>/dev/null || echo none)"       # your on-disk form
origin_hash="$(git rev-parse "origin/$branch:$FORM" 2>/dev/null || echo none)"  # latest on origin
[ "$origin_hash" = none ] && exit 0
last="$(cat "$STATE" 2>/dev/null || echo none)"

# Notify when origin has a form you don't have yet — but only once per distinct version.
if [ "$origin_hash" != "$local_hash" ] && [ "$origin_hash" != "$last" ]; then
  echo "$origin_hash" > "$STATE"
  echo "$(date)  new form on origin ($origin_hash) — notified" >> "$REPO/logs/formwatch.log"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'display notification "Run ./update.sh, then upload the form to Google Drive." with title "📢 New campaign form ready" sound name "Glass"' 2>/dev/null || true
  fi
fi
