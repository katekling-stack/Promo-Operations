# Spec: fully-automated "post the plan to Slack" (Option B)

**For:** a Slack admin / developer.
**Goal:** when a Campaign Manager finishes the promo form, one click **uploads the plan
`.json` file straight into `#promo-order-automations-submissions`** — no manual drag/attach.

> **Context:** Today the form's "Download & post to Slack" button downloads the plan file and
> opens the channel; the CM drags the file in (one manual step, zero infrastructure). This
> spec removes that last step. It's an **interim** convenience — the whole form→Slack path
> retires once the Salesforce → FreeWheel integration is live (drafts will build straight
> from the Case).

## Why a backend is required
The form is a **static HTML page** (no server). Slack's file-upload API needs a **secret
token**, and a token must never live in client-side HTML (anyone could view-source it and
spam/abuse the workspace). So the upload has to go through a tiny trusted service that holds
the token.

## What to build
A minimal endpoint the form can POST the plan JSON to, which uploads it to the channel.

1. **Create a Slack app** in the workspace (api.slack.com/apps).
   - Bot token scopes: `files:write` (upload) and `chat:write` (optional message).
   - Install to the workspace; note the **Bot User OAuth Token** (`xoxb-…`).
   - Invite the bot to **#promo-order-automations-submissions**.

2. **Deploy a tiny endpoint** (any of: a Google Apps Script web app, a serverless
   function — Cloud Run / Lambda / Vercel — or an internal service). It should:
   - Accept an HTTPS `POST` with a JSON body: `{ "filename": "...", "plan": { … } }`.
   - Call Slack **`files.upload`** (multipart) or the newer
     `files.getUploadURLExternal` + `files.completeUploadExternal` flow, with:
     - `channels` = the channel ID for `#promo-order-automations-submissions`
     - `filename` = `<title>-<region>.plan.json`
     - file content = the posted `plan` JSON, pretty-printed
     - optional `initial_comment` = e.g. `"New promo submission: <title> — <region>"`
   - Keep the `xoxb-…` token **only** in the server's environment/secret store — never return it.
   - Restrict who can call it (see security below).

3. **Point the form at it.** The form already centralizes the endpoint — set it in
   `scripts/build_plan_form.py` (`SLACK_SUBMIT_URL` / a new `SLACK_UPLOAD_URL`) and the
   button will `POST` the plan there instead of opening the channel. (Ask the promo-ops
   maintainer to wire the button's `fetch(...)` to your endpoint; ~10 lines.)

## Security (important)
- The endpoint is effectively "anyone who can load the form can post to the channel."
  Mitigate with at least one of: host the form behind SSO / an internal-only network; add a
  shared secret header the form sends and the endpoint checks; or rate-limit + validate the
  payload shape (must look like a plan) before uploading.
- Never expose the Slack token to the browser. The browser talks only to your endpoint.

## Payload the form will send
```json
{
  "filename": "tulsa-king-usa.plan.json",
  "plan": { "promoted_title": "Tulsa King", "region": "USA", "...": "..." }
}
```
Your endpoint uploads `plan` (pretty-printed) as `filename` to the channel.

## Acceptance test
1. Open the form, fill a campaign, click the submit button.
2. A `…plan.json` file appears in `#promo-order-automations-submissions` within a few seconds,
   posted by the bot, with no manual attach.
3. Ad Ops downloads that file and runs `promo-ops push <file> --target freewheel --live` — draft appears.

---

### Alternative considered — Incoming Webhook / Workflow Builder (not recommended)
A Slack Incoming Webhook or Workflow-Builder webhook can post a **message** but **cannot
upload a file**. It could post the plan JSON as a text block, but then Ad Ops would have to
copy that text back into a `.json` file to run the tool — clunky and error-prone. Use the
`files.upload` backend above instead.
