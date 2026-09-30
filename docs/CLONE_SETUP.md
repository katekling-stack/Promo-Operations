# Set up Promo-Operations on your computer (clone from GitHub)

This is how each campaign manager gets their **own copy** of the tool and keeps it up to date.

> **Mental model:** you are **not** copying files from someone else's computer. Everyone
> downloads ("clones") the same code from the shared GitHub repo, which is the single source of
> truth. When the tool is updated, everyone runs `./update.sh` to pull the latest.
>
> Your **`.env`** file (the FreeWheel login) is personal and is **never** stored in GitHub —
> you create it once on your own machine (Step 6). Never share or commit it.

Do this **once**, ~15–20 minutes, copy/paste — no coding.

---

## Step 0 — Admin grants repo access (one-time, done by Kate)
The repo is **private**. Before a CM can clone it, add them on GitHub:
`github.com/katekling-stack/Promo-Operations` → **Settings → Collaborators → Add people**
(or add them to the team). They'll get an email invite to accept.

---

## Step 1 — Install Python 3.10+
- **Mac:** open **Terminal** (Cmd+Space → "Terminal"), run `python3 --version`.
  If it's below 3.10 or missing, install the latest from https://www.python.org/downloads/.
- **Windows:** open **PowerShell**, run `python --version`. If missing, install from the same
  link and **tick "Add Python to PATH"** on the first installer screen.

## Step 2 — Install Git
- **Mac:** run `git --version`. If prompted, click **Install** (Xcode command line tools).
- **Windows:** if `git --version` fails, install from https://git-scm.com/download/win
  (accept the defaults).

## Step 3 — Sign in to GitHub (so you can clone the private repo)
Easiest option — **GitHub CLI** (handles login in your browser, no tokens to manage):
1. Install it from https://cli.github.com/ (Mac: `brew install gh`).
2. Run:
   ```
   gh auth login
   ```
   Choose **GitHub.com → HTTPS → Login with a web browser**, and follow the prompts.

*(Alternative: install **GitHub Desktop** (https://desktop.github.com), sign in, and use it to
clone in Step 4 via File → Clone repository. Then continue in Terminal from Step 5.)*

## Step 4 — Clone the code (get the working branch)
Go somewhere easy to find first (e.g. your Desktop), then clone the **team's branch**:

```
cd ~/Desktop
git clone --branch claude/freewheel-order-placement-templates-p2rjzd https://github.com/katekling-stack/Promo-Operations.git
```

You'll now have a **`Promo-Operations`** folder on your Desktop.

> The team currently runs the `claude/freewheel-order-placement-templates-p2rjzd` branch.
> If that ever changes, Kate will share the new branch name.

## Step 5 — Go into the folder
```
cd ~/Desktop/Promo-Operations
```
*(On Windows, replace `~/Desktop` with the path where you cloned it.)*

## Step 6 — Create your `.env` (your FreeWheel login)
Copy the example and fill in the FreeWheel API login (the same `AdOps.api@520311` access Ad Ops
already uses — ask Kate if you don't have it):

- **Mac:** `cp .env.example .env`
- **Windows:** `copy .env.example .env`

Then open `.env` in any text editor and fill in at least:
```
FREEWHEEL_NETWORK_ID=520311
FREEWHEEL_USERNAME=...   (the AdOps.api@520311 user)
FREEWHEEL_PASSWORD=...
```
**Never** commit or share this file — it holds your credentials.

## Step 7 — Install the tool
From inside the `Promo-Operations` folder:
```
python -m pip install -e .
```
*(If `python` isn't found on Mac, use `python3 -m pip install -e .`.)*

## Step 8 — Test it
```
promo-ops --help
promo-ops qa <an IO id>
```
If `promo-ops --help` prints the list of commands, you're set. See
[`docs/QA_GUIDE.md`](QA_GUIDE.md) for how to run the QA review.

---

## Keeping up to date (every time the tool changes)
From inside the folder, just run:
```
./update.sh
```
It pulls the latest code (and tells you if the campaign form changed and needs re-uploading).

> `./update.sh` does a hard reset to the shared branch — so **don't hand-edit files** in this
> folder; your changes would be discarded. Only your `.env` (which git ignores) is left alone.

---

## Quick checklist per CM
- [ ] Invited to the private GitHub repo (admin)
- [ ] Python 3.10+ installed
- [ ] Git installed + signed in to GitHub (`gh auth login` or GitHub Desktop)
- [ ] Cloned the `Promo-Operations` folder (team branch)
- [ ] Created their own `.env` with the FreeWheel login
- [ ] `python -m pip install -e .`
- [ ] `promo-ops --help` works
