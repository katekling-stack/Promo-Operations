# DDA audience-segment requests

For a plan's Tier 1 affinity shows, `promo-ops dda-requests` finds the shows that **don't
have a DDA segment yet** and produces request-ready rows (Type / Region bucket / Title →
the tool's generated name), plus a CSV.

```
promo-ops dda-requests <plan.json>                 # print + write <plan>.dda-requests.csv
promo-ops dda-requests --region UK --shows "A; B"  # ad-hoc, no plan
```

Region maps to the request tool's buckets: USA/CA/BR/LATAM → **Americas**, AU → **APAC**,
UK/IE/FR/IT/GSA/… → **EU/UK**. The genre tab is guessed from the plan's genres (override with
`--genre "Crime"`).

## One-click submit (optional)

`--submit` POSTs the requests straight to the "Audience Segment Request" Apps Script tool.
Two one-time setup steps on the tool side, because the deployed web app only exposes the
in-page `google.script.run` RPC (not callable externally):

**1. Add a `doPost(e)` to the Apps Script** (Extensions → Apps Script), then redeploy a new
version:

```javascript
function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var result = submitSegmentRequest(data);   // reuses the existing function
    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'error', message: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
```

The POST body matches what the form already sends `submitSegmentRequest`:
`{type, region, genre, title, io, placement, action, requester, email, date, notes}`.

**2. Auth.** The app is deployed *"Anyone within Paramount"*, so an external POST needs a
Paramount Google session. Either:
- redeploy **"Who has access: Anyone"** (simplest; the endpoint is unguessable), or
- keep it Paramount-only and provide a Google OAuth bearer token via `DDA_REQUEST_TOKEN`.

Then set the endpoint and submit:
```
export DDA_REQUEST_URL="https://script.google.com/a/macros/paramount.com/s/.../exec"
promo-ops dda-requests <plan.json> --submit --email you@paramount.com
```

Each request creates the row(s) in the Audience Segment Doc and sends the notification email,
exactly as the form does — the tool generates the segment name and Databricks/the internal
team process it as usual.
