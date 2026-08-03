# Data Mine 2026-2027 Project Watcher

Polls two sources roughly every minute via GitHub Actions and emails/texts you
when something new shows up:

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

Once that works, set up the external trigger in step 6 below — GitHub's own `schedule:` cron is left in the workflow but is not the real trigger; it fires unreliably in practice.

### 6. Fix unreliable scheduling with an external trigger (recommended)

GitHub's native `schedule:` trigger runs on a low-priority, best-effort queue and can silently skip fires under load, with no error anywhere. In testing on this repo it fired **once** in the first 4 hours despite ~16 expected fires — everything else was manual. This isn't fixable from the workflow file; the reliable workaround is to have an external, free scheduler call GitHub's API to trigger the workflow instead of waiting on GitHub's own cron.

1. **Create a GitHub token**: [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens) → **Fine-grained tokens** → **Generate new token**.
   - Set an expiration (e.g. 1 year).
   - **Repository access**: "Only select repositories" → this repo only.
   - **Permissions**: Repository permissions → **Actions** → **Read and write**.
   - Generate and copy the token — you won't see it again.
2. **Sign up free at [cron-job.org](https://cron-job.org)** and create a new cronjob:
   - **URL**: `https://api.github.com/repos/<your-username>/<repo-name>/actions/workflows/check.yml/dispatches`
   - **Request method**: `POST`
   - **Schedule**: every 1 minute (cron-job.org's fastest tier). Briefly backed off to 5 minutes over a suspicion this was too aggressive against Purdue's Class Search, but the real cause of the failures around that time turned out to be an unrelated code bug (see [prd.md](prd.md) §13) — nothing observed actually implicates request frequency, so this is back to 1 minute.
   - **Headers**:

     | Key | Value |
     |---|---|
     | `Authorization` | `Bearer <the token from step 1>` |
     | `Accept` | `application/vnd.github+json` |
     | `Content-Type` | `application/json` |

   - **Request body**: `{"ref":"main"}`
3. Save, then use cron-job.org's "Test run" / "Execute now" button — it should return **204 No Content**. A 401/404 means the token or URL is wrong; check the Actions tab to confirm a new run actually started.
4. The `schedule:` block in `check.yml` is left in place as a harmless backup — if it happens to fire on its own, it just runs an extra (idempotent) check.

The token only needs Actions read/write on this one repo — don't use a classic (account-wide) token, and don't put the token in any file in this repo; it lives only in cron-job.org's job configuration.

`check.yml` also caches pip packages and the Playwright Chromium browser between runs (`actions/cache`) so most runs skip the ~30-60s install step, and a `concurrency` group serializes runs so a slow run can't overlap with the next trigger and race on the final `git push` — a newer trigger just bumps a still-queued older one rather than piling up a backlog. Both matter at a 1-minute cadence.

**If a run fails**: check the Actions tab — a failed run never reaches the `git commit` step, so no state is lost and the next successful run will still catch and alert on anything that was missed, but a project could sit un-alerted for as long as failures continue. Manually clicking **Run workflow** is the fastest way to recover rather than waiting on the next trigger.

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
- GitHub's scheduled cron is best-effort and unreliable in practice (see step 6 above) — an external pinger hitting the `workflow_dispatch` API is the actual primary trigger; the `schedule:` block is a harmless backup that may or may not fire.
- **Each semester**: `PURDUE_TERM_CODE` and `PURDUE_TERM_NAME` in `scraper.py` are hardcoded to Fall 2026 (`202710`) and need updating (plus a fresh `seen_sections.json` baseline) to reuse this for a different term.
