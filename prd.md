# PRD: Data Mine 2026-2027 Project Watcher

## 1. Problem / Goal

The Data Mine's project list (https://crp.the-examples-book.com/) will be updated within the next month with new corporate partnership projects for the 2026-2027 academic year, some from large companies. The user wants to know **immediately** when a new 2026-2027 project appears, via an alert to their phone (email + SMS), including the project's name.

Location (West Lafayette, IN) filtering is a nice-to-have, not required — the user is fine manually checking location after being alerted, since only 2026-2027 projects will be newly added going forward.

## 2. Source Site Analysis

- URL: `https://crp.the-examples-book.com/`
- The projects table (`<table id=projects-table>`) is **fully server-rendered** — a single unauthenticated `GET` returns all rows (378 total across all years as of this writing) embedded directly in the HTML. No JavaScript execution or headless browser is required to see the full dataset; the on-page filters (year/location/search dropdowns) are just client-side show/hide over data that's already present.
- Each row has this structure:
  ```html
  <tr>
    <td data-label="Academic Year"><a href=".../years/2026-2027/"> 2026-2027 </a>
    <td data-label=Location><a href=".../locations/west-lafayette-in/">West Lafayette, IN</a>;
    <td data-label=Partnership><a href=".../companies/some-company/"> Some Company </a>
    <td data-label="Project Name"><a href="https://crp.the-examples-book.com/some-project-slug-543/">Some Project Title</a>
    <td data-label=Semester><span class="semester-badge full-year">Full Year</span>
  ```
- Each project detail page URL ends in a stable numeric ID (e.g. `-543`). This ID is the most reliable unique key for diffing — more robust than the project title, which sometimes carries a mutable `(NEW)` / `(RETURNING)` prefix.
- As of this writing there are **18 rows** for academic year 2026-2027.

## 3. Scope

**In scope:**
- Detect newly-added rows where Academic Year = "2026-2027"
- Alert via email (Brevo) and phone push notification (ntfy.sh) with project name, company, location, and semester
- Run automatically on a schedule without the user's computer needing to be on

**Out of scope:**
- Automatic filtering/alerting by location (West Lafayette) — user will check manually
- Tracking academic years other than 2026-2027
- Detecting edits to existing project rows (only additions trigger alerts)

## 4. Approach

### 4.1 Scraper (`scraper.py`)

1. `GET https://crp.the-examples-book.com/` with a timeout and a descriptive `User-Agent`.
2. Parse `#projects-table` rows with BeautifulSoup.
3. Keep only rows where the Academic Year cell text is `2026-2027`.
4. For each kept row, extract:
   - `project_id` — numeric suffix parsed from the Project Name `<a href>` (unique key)
   - `project_name`, `company`, `location`, `semester`
5. Load previously-seen project IDs from `seen_projects.json` (checked into the repo).
6. Compute `new_projects = current - seen`.
7. If `new_projects` is non-empty:
   - Send one email via the Brevo transactional email API to `ALERT_EMAIL_TO`, and one push notification via ntfy.sh to `NTFY_TOPIC`, listing each new project's name, company, location, and semester.
8. Write the updated full set of current project IDs back to `seen_projects.json`.
9. Exit non-zero (but without sending a false "new project" alert) if the page fetch/parse fails, so the GitHub Actions run shows as failed and is visible in the Actions tab.

### 4.2 State persistence

- `seen_projects.json` lives in the repo and is committed back by the workflow after each run (`git commit` + `git push` using the workflow's built-in `GITHUB_TOKEN`).
- **Seed value**: pre-populated with the 18 project IDs currently listed for 2026-2027, so the first scheduled run does not fire 18 false "new project" alerts.

### 4.3 Notifications

- **Email**: sent via the [Brevo](https://www.brevo.com) transactional email HTTP API (`POST /v3/smtp/email`), authenticated with an API key. Switched from the original Gmail SMTP + App Password design because the user's Google account has Advanced Protection enabled, which disables App Password generation entirely — no workaround available. Brevo requires verifying a sender email address (one-click confirmation, no domain needed) and has a free tier (300 emails/day). Recipients: `ALERT_EMAIL_TO` (comma-separated for multiple).
- **Phone push**: sent via [ntfy.sh](https://ntfy.sh) (`POST https://ntfy.sh/<topic>`), a free no-signup push notification service. Switched from the original carrier email-to-SMS gateway design after confirming T-Mobile discontinued `tmomail.net` in December 2024 (silently, via DNS removal) and AT&T retired its gateway in June 2025 — only Verizon's still works, and it's slated to shut down March 2027, so a carrier-agnostic solution was needed. The topic name (`NTFY_TOPIC`) acts as a shared secret: anyone who knows it can read or post to it, so it must be a hard-to-guess string, not a real word. The user subscribes to that topic in the ntfy mobile app to receive pushes.

### 4.4 Hosting & schedule

- GitHub Actions in a new repo the user creates and owns.
- Workflow triggers:
  - `schedule: cron: '7,22,37,52 * * * *'` — every 15 minutes, offset off the exact quarter-hour. GitHub does not guarantee exact timing on scheduled workflows, and in testing, runs scheduled for the exact quarter-hour mark (`*/15`) were delayed 75+ minutes with zero executions — GitHub's queue is most congested exactly at `:00/:15/:30/:45` since that's when most of the platform's cron jobs fire. Offsetting a few minutes off that mark avoids the worst of the congestion.
  - `workflow_dispatch:` — manual "Run workflow" button, for on-demand testing
- Repo secrets (set by the user directly in GitHub's Settings → Secrets UI — never shared with or seen by the assistant):
  - `BREVO_API_KEY`
  - `BREVO_SENDER_EMAIL` — the verified sender address
  - `ALERT_EMAIL_TO`
  - `NTFY_TOPIC` — the user's chosen ntfy.sh topic name

## 5. Repo layout

```
tdmWebScraper/
├── scraper.py
├── seen_projects.json        # seeded with current 18 IDs
├── requirements.txt          # requests, beautifulsoup4
├── .github/
│   └── workflows/
│       └── check.yml
├── README.md                 # setup: Brevo account, GitHub secrets, enabling Actions
└── prd.md
```

## 6. Failure handling

- Network/parse errors: logged, job fails visibly in the Actions tab, no alert sent (avoids false positives). No separate "scraper is down" notification channel in v1 — user can glance at the Actions tab if they suspect an issue.
- If the site's HTML structure changes enough to break parsing, the job will fail loudly (exception) rather than silently reporting zero projects.

## 7. Testing plan

1. Run `scraper.py` locally against the live site to confirm current 18 projects parse correctly and match the seeded `seen_projects.json` (i.e., zero new-project alerts).
2. Temporarily remove one known project ID from a local copy of `seen_projects.json` and re-run to confirm the alert email and push notification fire with correct content.
3. Push to GitHub, add secrets, trigger the workflow manually via `workflow_dispatch` to confirm the Brevo send and repo commit-back work end-to-end in Actions.
4. Let the cron schedule run for a day and confirm at least one successful scheduled execution in the Actions history.

## 8. Open items for implementation phase

- User to create the GitHub repo and add the four secrets before first deploy.
- User to sign up for Brevo, verify a sender email, and generate an API key; and to pick an ntfy.sh topic name and subscribe to it in the mobile app.
