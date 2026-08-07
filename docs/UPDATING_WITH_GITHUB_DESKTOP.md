# Keeping your Mac up to date — the easy way (GitHub Desktop)

**Why:** your current folder is a downloaded ZIP, so it never gets updates — that's why
fixes weren't reaching you and `git pull` failed. GitHub Desktop makes a *real* connected
copy (a "clone"). After this one-time setup, getting the latest fixes is a **single click**
— no ZIPs, no Terminal juggling.

---

## One-time setup (~5 minutes)

### 1. Install GitHub Desktop
- Go to **https://desktop.github.com** → **Download for macOS** → open the downloaded file
  and drag **GitHub Desktop** into Applications. Open it.

### 2. Sign in
- In GitHub Desktop: **Sign in to GitHub.com** → it opens your browser → log in with your
  Paramount GitHub account → **Authorize**. You land back in the app.

### 3. Clone the repo (make your connected copy)
- **File ▸ Clone repository…** → **GitHub.com** tab.
- In the list (or the filter box) pick **`katekling-stack/Promo-Operations`**.
- **Local path:** leave it (defaults to `~/Documents/GitHub/Promo-Operations`) → **Clone**.

### 4. Switch to our working branch
- Top of the window: **Current branch** ▸ pick
  **`claude/freewheel-order-placement-templates-p2rjzd`**.
  (That's where all the latest work lives.)

### 5. Point the tool at the new folder (one time)
Open **Terminal** and run:
```
cp ~/Desktop/Promo-Operations/.env ~/Documents/GitHub/Promo-Operations/.env
cd ~/Documents/GitHub/Promo-Operations
pip3 install -e .
```
That copies your saved FreeWheel login into the new copy and installs the tool from it.

> From now on, **use `~/Documents/GitHub/Promo-Operations`** as your folder (you can delete
> the old `~/Desktop/Promo-Operations` once you've confirmed the new one works).

---

## Getting updates from now on (the whole point)

Whenever I ship a fix, just:
1. Open **GitHub Desktop**.
2. Make sure **Current branch** is `claude/freewheel-order-placement-templates-p2rjzd`.
3. Click **Fetch origin** → it turns into **Pull origin** → click it. Done — you're current.

That's the entire update. (If a change ever touches dependencies, I'll tell you to re-run
`pip3 install -e .` — rare.)

---

## Running an order (unchanged)
```
cd ~/Documents/GitHub/Promo-Operations
promo-ops push ~/Downloads/<your-file>.plan.json --target freewheel --live
```

## Handy
- **See what changed** in an update: GitHub Desktop shows the history on the left.
- **Nothing to pull?** It'll say "up to date" — that's fine.
- **Stuck?** Send me a screenshot and I'll walk you through it.
