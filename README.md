# Data Mine 2026-2027 Project Watcher

Polls https://crp.the-examples-book.com/ every 15 minutes via GitHub Actions and
emails/texts you when a new 2026-2027 project is added. See [prd.md](prd.md) for
the full design.

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

### 3. Find your carrier's SMS gateway address

Combine your 10-digit number with your carrier's domain:

| Carrier | Gateway |
|---|---|
| Verizon | `<number>@vtext.com` |
| AT&T | `<number>@txt.att.net` |
| T-Mobile | `<number>@tmomail.net` |
| Sprint | `<number>@messaging.sprintpcs.com` |

### 4. Add repo secrets

On GitHub: repo → **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Secret | Value |
|---|---|
| `BREVO_API_KEY` | The API key from step 2 |
| `BREVO_SENDER_EMAIL` | The Gmail address you verified as a sender in step 2 |
| `ALERT_EMAIL_TO` | Your email (comma-separate multiple) |
| `ALERT_SMS_TO` | Your carrier gateway address from step 3 |

### 5. Test it

Repo → **Actions** tab → "Check for new 2026-2027 projects" → **Run workflow** (manual trigger). Check the run log — it should say `No new projects.` since the baseline is already seeded. To verify alerting actually works end-to-end, temporarily delete one entry from `seen_projects.json`, commit, push, and re-run — you should get an email/text, then restore the file.

Once that works, the `*/15 * * * *` cron schedule takes over automatically — no further action needed.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scraper.py
```

Running locally without `BREVO_API_KEY`/`BREVO_SENDER_EMAIL` set will raise a `KeyError` only if a new project is actually found (no alert needed = no crash). Set env vars locally if you want to test sending.

## How it works

- `scraper.py` fetches the page, parses `#projects-table`, filters to Academic Year = 2026-2027, and diffs against `seen_projects.json` by each project's stable numeric ID (parsed from its URL).
- New projects trigger one detailed email and one short SMS-gateway message.
- `seen_projects.json` is updated and committed back to the repo by the workflow after each run.
- GitHub's scheduled cron is best-effort and can lag a few minutes under platform load — this is a GitHub limitation, not something the workflow controls.
