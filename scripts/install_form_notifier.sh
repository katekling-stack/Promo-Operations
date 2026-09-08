#!/usr/bin/env bash
# One-time setup for the campaign-form watcher (macOS). Run once:  ./scripts/install_form_notifier.sh
# It notifies you when a new form is ready. Turn it off any time with the command it prints.

set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
LABEL="com.paramount.promoops.formwatch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

chmod +x "$REPO/scripts/form_notifier.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$REPO/logs"
launchctl unload "$PLIST" 2>/dev/null || true   # in case it's already installed

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$REPO/scripts/form_notifier.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>14400</integer>
  <key>StandardOutPath</key><string>$REPO/logs/formwatch.out.log</string>
  <key>StandardErrorPath</key><string>$REPO/logs/formwatch.err.log</string>
</dict></plist>
PLIST

launchctl load "$PLIST"
echo "✅ Form watcher installed — it checks every few hours and notifies you ONLY when a new"
echo "   campaign form is ready. Nothing else to do."
echo
echo "   Test it now:   launchctl start $LABEL"
echo "   Turn it off:   launchctl unload $PLIST"
