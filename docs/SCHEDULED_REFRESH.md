# Scheduled auto-refresh (Mac) — set once, forget it

Keeps the searchable option lists (shows, audience segments, genres, Pluto categories/
channels) current automatically, so you don't have to remember to sync. It runs on your
Mac via `launchd`.

## What it does, every weekday at 7:00 AM
Runs `scripts/refresh_data.sh`, which:
1. `promo-ops sync-all` — pulls the latest series / audience items / attributes from FreeWheel.
2. Rebuilds the targeting-option lists.
3. Rebuilds the campaign form.

After each run, the **engine resolves everything current** (so `push` / `batch` always
find the newest shows/segments). Output is logged to `logs/refresh.log`.

> **One manual step remains (for now):** re-upload the rebuilt
> `templates/campaign-plan/campaign-plan-form.html` to Drive so Campaign Managers see the
> new options in the *picker*. To make even that hands-off, we'd host the form on the promo
> site or wire the Google service-account upload (see `SLACK_AUTOPOST_SPEC.md` pattern) —
> ask and I'll set it up. Meanwhile the **"Request a new audience segment"** button covers
> anything added same-day.

## One-time setup (run these 3 lines in Terminal)
```
chmod +x /Users/klemley/Desktop/Promo-Operations/scripts/refresh_data.sh
cp /Users/klemley/Desktop/Promo-Operations/deploy/com.paramount.promoops.refresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.paramount.promoops.refresh.plist
```
That's it — it now runs itself every weekday morning.

## Test it right now (optional)
```
launchctl start com.paramount.promoops.refresh
sleep 5 && tail -n 20 /Users/klemley/Desktop/Promo-Operations/logs/refresh.log
```
(The full run takes a few minutes because it pulls ~229k series.)

## Good to know
- **Your Mac must be on/awake** at the scheduled time. If it was asleep/off, `launchd`
  runs the missed job once when it next wakes — so it still refreshes.
- **Change the time / frequency:** edit `~/Library/LaunchAgents/com.paramount.promoops.refresh.plist`
  (the `Hour`/`Minute`, or remove the `Weekday` entries to run all 7 days), then reload:
  ```
  launchctl unload ~/Library/LaunchAgents/com.paramount.promoops.refresh.plist
  launchctl load   ~/Library/LaunchAgents/com.paramount.promoops.refresh.plist
  ```
- **Turn it off:** `launchctl unload ~/Library/LaunchAgents/com.paramount.promoops.refresh.plist`
- **If the project folder moves,** update the path in `scripts/refresh_data.sh` and the plist.
- Needs your FreeWheel login in `.env` (already set up).
