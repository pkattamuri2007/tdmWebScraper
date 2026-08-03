# Data Mine 2026-2027 Project Watcher

Polls two sources every 15 minutes via GitHub Actions and emails/texts you when
something new shows up:

1. https://crp.the-examples-book.com/ — new 2026-2027 Data Mine projects.
2. Purdue's public [Class Search](https://selfservice.mypurdue.purdue.edu/prod/bwckschd.p_disp_dyn_sched)
   — new TDM 21100 lecture sections for Fall 2026 (a new section/CRN showing up
   there means a new Corporate Partners project just opened for registration,
   often before or independent of the Data Mine page being updated). This one
   is scraped headlessly with Playwright since it needs real form
   interaction, not just a static page fetch — see [prd.md](prd.md) §9 for why.

See [prd.md](prd.md) for the full design.

## One-time setup

### 1. Create the GitHub repo

```bash
cd /Users/prajith/tdmWebScraper
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

(Create the empty repo on GitHub first, e.g. via `gh repo create <repo-name> --private --source=. --remote=origin` or the GitHub web UI, then push.)

### 2. Set up Brevo (free transactional email API)

Used instead of Gmail SMTP since Gmail App Passwords require 2-Step Verification with no Advanced Protection — many accounts can't generate them.

1. Sign up free at https://www.brevo.com (no credit card required)
2. Go to **Senders, Domains & Dedicated IPs → Senders** and add/verify your Gmail address as a sender (click the confirmation link Brevo emails you)
3. Go to **SMTP & API → API Keys** and generate a new API key
4. Copy the API key — you'll paste it into a GitHub secret next, not into any file here

### 3. Set up ntfy.sh for phone push alerts

Carrier email-to-SMS gateways are dead (T-Mobile shut down `tmomail.net` in Dec 2024, AT&T retired theirs in June 2025), so phone alerts go through [ntfy.sh](https://ntfy.sh) instead — a free, no-signup-required push notification service.

1. Install the **ntfy** app ([iOS](https://apps.apple.com/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)) on your phone
2. Pick a **hard-to-guess topic name** (anyone who knows it can read your notifications or post fake ones — it's a shared secret, not a private channel), e.g. `tdm-project-alerts-8f3k2q`
3. In the app, tap **Subscribe to topic** and enter that exact name (default server `ntfy.sh` is fine)
4. That's it — no account, no API key

### 4. Add repo secrets

On GitHub: repo → **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Secret | Value |
|---|---|
| `BREVO_API_KEY` | The API key from step 2 |
| `BREVO_SENDER_EMAIL` | The Gmail address you verified as a sender in step 2 |
| `ALERT_EMAIL_TO` | Your email (comma-separate multiple) |
| `NTFY_TOPIC` | The topic name you picked in step 3 |

### 5. Test it

Repo → **Actions** tab → "Check for new 2026-2027 projects" → **Run workflow** (manual trigger). Check the run log — it should say `No new projects.` since the baseline is already seeded. To verify alerting actually works end-to-end, temporarily delete one entry from `seen_projects.json`, commit, push, and re-run — you should get an email and a phone push notification, then restore the file.

Once that works, the `7,22,37,52 * * * *` cron schedule (every 15 min, offset off the exact quarter-hour to dodge GitHub's scheduling congestion — see below) takes over automatically — no further action needed.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scraper.py
```

Running locally without `BREVO_API_KEY`/`BREVO_SENDER_EMAIL` set will raise a `KeyError` only if a new project is actually found (no alert needed = no crash). Set env vars locally if you want to test sending.

## How it works

- `scraper.py` fetches the Data Mine page, parses `#projects-table`, filters to Academic Year = 2026-2027, and diffs against `seen_projects.json` by each project's stable numeric ID (parsed from its URL).
- It also drives Purdue's Class Search with a headless Chromium browser (Playwright): select term Fall 2026 → search subject TDM, course 21100 → parse the resulting section list, and diffs against `seen_sections.json` by CRN.
- New projects/sections each trigger one detailed email (via Brevo) and one push notification (via ntfy.sh).
- `seen_projects.json` and `seen_sections.json` are updated and committed back to the repo by the workflow after each run.
- GitHub's scheduled cron is best-effort. Runs scheduled for the exact quarter-hour (`*/15 * * * *`) hit heavy queue congestion in testing (75+ min delay, zero runs) since that's when most of the platform's scheduled jobs fire; the cron is offset a few minutes off that mark to avoid it. Even offset, expect occasional lag under high platform load — this is a GitHub limitation, not something the workflow controls.
- **Each semester**: `PURDUE_TERM_CODE` and `PURDUE_TERM_NAME` in `scraper.py` are hardcoded to Fall 2026 (`202710`) and need updating (plus a fresh `seen_sections.json` baseline) to reuse this for a different term.
