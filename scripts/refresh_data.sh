#!/bin/bash
# Auto-refresh the FreeWheel data snapshots + rebuild the campaign form.
# Runs on a schedule via launchd — see docs/SCHEDULED_REFRESH.md.
#
# It pulls the latest series / audience items / attributes from FreeWheel, rebuilds the
# targeting-option lists, and regenerates the form. After it runs, the ENGINE resolves
# everything current; re-upload the rebuilt form to Drive so Campaign Managers also see
# the new options in the picker (until Drive auto-upload / promo-site hosting is set up).
# Step 4 now publishes the project + the team pages to the Skydance Pages site (docs/SITE_PUBLISHING.md).

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
  echo "-- 1/4 sync FreeWheel data (series + audience items + attributes)…"
  python3 -m promo_ops.cli sync-all || echo "!! sync-all failed"
  echo "-- 1b/4 sync the (Promo) Brand list (needs the MRM login in .env)…"
  python3 scripts/sync_brands.py || echo "!! brand sync failed (MRM login missing?) — the Brand list keeps its last copy"
  echo "-- 2/4 rebuild targeting-option lists…"
  python3 scripts/build_targeting_options.py || echo "!! build_targeting_options failed"
  echo "-- 3/4 rebuild the campaign form…"
  python3 -c "from scripts.build_plan_form import build; print('form rebuilt ->', build())" || echo "!! form rebuild failed"
  echo "-- 4/4 publish to the team site (Skydance Pages; needs the VPN)…"
  python3 scripts/publish_site.py || echo "!! site publish did not finish (VPN off?) — everything above is unaffected; it retries on the next run"
  if [ -f "$HOME/.ssh/skydance_pages_promo_ops_app" ]; then
    echo "-- 4b/4 publish the hosted app's source (same fresh data)…"
    python3 scripts/publish_site.py --app || echo "!! app publish did not finish (VPN off?) — retries on the next run"
  fi
  echo "DONE $(date)."
  echo "If step 4 finished, the team site has the current campaign form. The Drive copy is NOT updated"
  echo "by this job any more -- point the team at the site link, or re-upload to Drive by hand."
  echo ""
} >> "$LOG" 2>&1
