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

## Step 0 — Make sure you have access (one-time)
The code lives in the Paramount GitHub organization, in a **private** repo:
`github.com/cbsi-adtech/digital_promo_automation`. To clone it you need:
1. A GitHub account that is a **member of the `cbsi-adtech` organization** (if you can't see
   the repo when signed in, ask Kate / your GitHub org admin to add you).
2. To **authorize your login for the organization's single sign-on** — GitHub prompts you the
   first time (Step 3). Click **Authorize** when it does.

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

> **If you ever see "organization has enabled or enforced SAML SSO … re-authorize the OAuth
> Application 'GitHub CLI'" or a 403:** your login just needs approving for the organization.
> Open the link GitHub prints (or github.com → profile picture → Settings → Applications →
> Authorized OAuth Apps → GitHub CLI → **Grant** next to `cbsi-adtech`), then try again.
> GitHub Desktop avoids this because it handles the approval in its sign-in screen.

## Step 4 — Clone the code
Go somewhere easy to find first (e.g. your Desktop), then clone the repo's **`main`** branch:

```
cd ~/Desktop
git clone --branch main https://github.com/cbsi-adtech/digital_promo_automation.git Promo-Operations
```

You'll now have a **`Promo-Operations`** folder on your Desktop.

> The team runs the **`main`** branch. If that ever changes, Kate will share the new branch name.

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
