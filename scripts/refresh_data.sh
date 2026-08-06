#!/bin/bash
# Auto-refresh the FreeWheel data snapshots + rebuild the campaign form.
# Runs on a schedule via launchd — see docs/SCHEDULED_REFRESH.md.
#
# It pulls the latest series / audience items / attributes from FreeWheel, rebuilds the
# targeting-option lists, and regenerates the form. After it runs, the ENGINE resolves
# everything current; re-upload the rebuilt form to Drive so Campaign Managers also see
# the new options in the picker (until Drive auto-upload / promo-site hosting is set up).

set -uo pipefail

# --- edit this if the folder ever moves ---
PROJECT="/Users/klemley/Desktop/Promo-Operations"

# launchd runs with a bare PATH; make sure python3 (python.org 3.14) + pip console scripts resolve.
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"

LOG="$PROJECT/logs/refresh.log"
mkdir -p "$PROJECT/logs"
cd "$PROJECT" || { echo "$(date)  ERROR: project folder not found at $PROJECT" >> "$LOG"; exit 1; }

{
  echo "==================== refresh started $(date) ===================="
  echo "-- 1/3 sync FreeWheel data (series + audience items + attributes)…"
  python3 -m promo_ops.cli sync-all || echo "!! sync-all failed"
  echo "-- 2/3 rebuild targeting-option lists…"
  python3 scripts/build_targeting_options.py || echo "!! build_targeting_options failed"
  echo "-- 3/3 rebuild the campaign form…"
  python3 -c "from scripts.build_plan_form import build; print('form rebuilt ->', build())" || echo "!! form rebuild failed"
  echo "DONE $(date)."
  echo "NEXT (manual for now): re-upload templates/campaign-plan/campaign-plan-form.html to Drive"
  echo "so CMs get the refreshed picker. (The engine is already current after this run.)"
  echo ""
} >> "$LOG" 2>&1
