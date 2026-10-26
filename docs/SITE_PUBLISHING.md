# Publishing to the team site (Skydance Pages)

The campaign form, the QA checklist, the QA tool setup guide and the project files live on one
internal site, so the team has a single link and nobody has to re-upload to Drive.

**Site:** https://promo-ad-operations-automation-qa-tools.skydancepages.cloud/ (company network / VPN)

| On the site | Comes from |
|---|---|
| `/` (team home), `/qa-checklist.html`, `/setup-guide.html` | the `site/` folder in this repo |
| `/Promo-Operations/...` (the campaign form, handbook, docs, config, data) | the whole repo, minus the exclusions below |

## How it updates

`scripts/refresh_data.sh` (the 7am job) ends with step 4, `python3 scripts/publish_site.py`. It
uploads only files whose **content changed** since the last successful publish, and overwrites
them. To publish by hand:

```bash
python3 scripts/publish_site.py --dry-run   # what would upload (works without the VPN)
python3 scripts/publish_site.py             # upload what changed
python3 scripts/publish_site.py --force     # re-upload everything
```

## Safety rules (tested in `tests/test_publish_site.py`)

- **Never published:** `.env` and any hidden file or folder, `.git`, `logs/`, keys and
  certificates (`*.pem`, `*.key`, `id_*`, `known_hosts*`), `__pycache__`, build output.
- **Never deleted:** the publisher only adds or overwrites. Something you delete from the repo
  stays on the site until you remove it in the Pages portal.
- **Site-scoped key:** it uses a deploy key that can only publish to this one site.

## One-time setup (already done on Kate's Mac)

1. Make a key: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/skydance_pages_promo_ops`
2. In the Pages portal, open the site, then **Deploy keys**, paste the `.pub` line, and add it.
   The portal shows the account name it created for that key (the `site-key-...` username).
3. Put that username in `SKY_PAGES_USER` (or the default in `scripts/publish_site.py`).
4. Connect once so the server's host key is recorded:
   `sftp -P 2022 -i ~/.ssh/skydance_pages_promo_ops -o UserKnownHostsFile=~/.ssh/known_hosts_skydance <username>@sftp.skydancepages.cloud`

The server **refuses rsync**, which is why this uses `sftp`.

## If it doesn't publish

- **"Could not resolve hostname" / timed out:** the VPN is off. It retries on the next run.
- **"deploy key not found":** the key file isn't at `~/.ssh/skydance_pages_promo_ops`.
- **Permission denied:** the key was removed from the site; add the public key again.
- Check `logs/refresh.log` (step 4) for the exact message.

## Who can open the site

Set in the Pages portal under **Access**: *Anyone signed in*, *Restricted* (named people and
groups only), *No sign-in*, or *Off*. The form embeds internal FreeWheel lists (shows, audience
segments, channels, brand names), so **Restricted** to the promo team is the safer setting.
