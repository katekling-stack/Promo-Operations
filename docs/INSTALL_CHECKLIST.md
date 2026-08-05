# Promo-Ops — Install Checklist (plain language)

A one-page setup you do **once** on your computer. After this, you'll fill the form in a
browser and run a couple of commands to create FreeWheel drafts. No coding needed — just
copy/paste the lines in the grey boxes. Takes ~15 minutes.

> **What you're setting up:** a small tool called `promo-ops` that turns a filled-in
> campaign form into a FreeWheel Insertion Order draft (NOT_BOOKED — nothing goes live
> until a human books it).

---

## Before you start — what you'll need
- [ ] Your computer (Mac or Windows).
- [ ] Your **FreeWheel API login** (username + password for the `AdOps.api@520311` user).
      If you don't have it, ask whoever set up your FreeWheel access. *(This is the same
      access Ad Ops already uses — not a new approval.)*
- [ ] The **promo-ops code** — a link to download it (from GitHub / your admin).

---

## Part A — Install Python (the tool runs on it)

**On a Mac**
1. Open the **Terminal** app (press `Cmd + Space`, type "Terminal", hit Enter).
2. Paste this and press Enter — it tells you if Python is already there:
   ```
   python3 --version
   ```
   - If it prints `Python 3.10` or higher → you're set, skip to Part B.
   - If not, download Python from **https://www.python.org/downloads/** (get the latest),
     run the installer, then re-check with the command above.

**On Windows**
1. Open **PowerShell** (click Start, type "PowerShell", hit Enter).
2. Paste and press Enter:
   ```
   python --version
   ```
   - If it prints `Python 3.10` or higher → skip to Part B.
   - If not, install from **https://www.python.org/downloads/**. **Important:** on the
     first installer screen, tick **"Add Python to PATH"** before clicking Install. Then
     re-check.

---

## Part B — Get the promo-ops code
- Download the code (your admin will share a link), and **unzip it** somewhere easy to find,
  e.g. your Desktop. You'll have a folder named **`Promo-Operations`**.
- *(If you were given a GitHub link instead, your admin can clone it for you — either way you
  end up with the `Promo-Operations` folder.)*

---

## Part C — Open a terminal **inside** that folder
The commands below must run from inside the `Promo-Operations` folder.

- **Mac:** in Terminal type `cd ` (with a space), then **drag the `Promo-Operations` folder
  onto the Terminal window**, then press Enter.
- **Windows:** open the `Promo-Operations` folder, click the address bar, type `powershell`,
  and press Enter.

To confirm you're in the right place, paste this — you should see files like `pyproject.toml`:
```
ls
```
*(On Windows if `ls` errors, use `dir`.)*

---

## Part D — Install the tool (one command)
Paste and press Enter:
```
python3 -m pip install -e .
```
*(On Windows use `python` instead of `python3`.)*

It'll print a lot of lines — that's normal. When it finishes, check it worked:
```
promo-ops --help
```
If you see a list of commands (build, preview, push, batch…), **the tool is installed.** ✅

---

## Part E — Add your FreeWheel login
The tool reads your credentials from a small file called `.env`.

1. Make a copy of the template:
   - **Mac:** `cp .env.example .env`
   - **Windows:** `copy .env.example .env`
2. Open the new `.env` file in a text editor (TextEdit / Notepad) and fill in these four
   lines, then **save**:
   ```
   FREEWHEEL_BASE_URL=https://api.freewheel.tv
   FREEWHEEL_NETWORK_ID=520311        # 520311 = production (520310 is the test network)
   FREEWHEEL_USERNAME=<your FreeWheel API username>
   FREEWHEEL_PASSWORD=<your FreeWheel API password>
   ```
   Leave everything else as-is. **Never share or email this file** — it has your password.
   *(Salesforce lines can stay blank; that part isn't turned on yet.)*

---

## Part F — Check it really works
1. **Preview** a sample plan (no writes, just shows the tiers):
   ```
   promo-ops preview templates/campaign-plan/sample-plan.json
   ```
   *(If that sample file isn't there, download a plan from the form first — see below — and
   use that filename.)*
2. **Dry-run** against FreeWheel (still no writes — shows exactly what it would create):
   ```
   promo-ops push your-plan.json --target freewheel
   ```
   If this connects and lists placements, your credentials work. 🎉

---

## Using it day-to-day
1. Open **`templates/campaign-plan/campaign-plan-form.html`** in any browser
   (double-click it). Fill it in, then click **Download plan file** — it saves a
   `‹title›-‹region›.plan.json` to your Downloads.
2. In the terminal (inside the folder):
   ```
   promo-ops preview  ~/Downloads/tulsa-king-usa.plan.json          # sanity-check
   promo-ops push     ~/Downloads/tulsa-king-usa.plan.json --target freewheel            # dry-run
   promo-ops push     ~/Downloads/tulsa-king-usa.plan.json --target freewheel --live     # creates the draft
   ```
3. Doing lots at once? Fill one sheet, one row per case, then:
   ```
   promo-ops batch cases.csv --live --out results.csv
   ```
4. Open the new draft in FreeWheel, review, and book it as you normally would.

> **Always dry-run first** (leave off `--live`) and eyeball the placements. `--live` only
> ever creates **NOT_BOOKED** drafts — nothing serves until you book it.

---

## Keeping the show/genre/audience lists fresh (optional)
The download already includes a snapshot of FreeWheel's series + audience data, so the
form's picks resolve out of the box. When FreeWheel adds new shows/segments, refresh the
snapshot (needs your FreeWheel login in `.env`):
```
promo-ops sync-all       # series + audience items + standard attributes (~a few minutes)
```
Then rebuild the form so its dropdowns match:
```
python3 scripts/build_targeting_options.py
python3 -c "from scripts.build_plan_form import build; build()"
```

## If something goes wrong
- **`command not found: promo-ops`** → re-run Part D from inside the folder. On Windows,
  close and reopen PowerShell after installing, then try again.
- **`python3: command not found`** (Mac) → try `python`. **`python` not recognized**
  (Windows) → Python wasn't added to PATH; re-run the installer and tick "Add Python to PATH".
- **A credentials / 401 / login error on `push`** → re-open `.env` and double-check the
  username/password and that `FREEWHEEL_NETWORK_ID=520311`.
- **"No space left" / other oddness** → close the terminal, reopen it inside the folder, and
  retry.
- Stuck? Send me the exact command you ran and the message you got, and I'll walk you through it.

---

## Quick reference (once set up)
| Do this | Command |
|---|---|
| Sanity-check a plan | `promo-ops preview <plan>.json` |
| See what it would create | `promo-ops push <plan>.json --target freewheel` |
| Create the draft | `promo-ops push <plan>.json --target freewheel --live` |
| Many cases at once | `promo-ops batch cases.csv --live --out results.csv` |
| Same title, other markets | `promo-ops mirror <plan>.json --to GSA,IT,ES` |
