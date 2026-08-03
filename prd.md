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
  - `schedule: cron: '7,22,37,52 * * * *'` — every 15 minutes, offset off the exact quarter-hour. GitHub does not guarantee exact timing on scheduled workflows, and in testing, runs scheduled for the exact quarter-hour mark (`*/15`) were delayed 75+ minutes with zero executions — GitHub's queue is most congested exactly at `:00/:15/:30/:45` since that's when most of the platform's cron jobs fire. Offsetting a few minutes off that mark avoids the worst of the congestion. **Superseded**: this trigger turned out to fire almost never in practice regardless of offset — see §10 for the external-trigger replacement and §11 for the current ~1-minute cadence.
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

## 9. Second source: Purdue Class Search (TDM 21100 sections)

**Why**: The Data Mine projects page (§2) is updated manually and doesn't show
whether a project's course section is actually open for registration yet. The
user wants to know the moment a new TDM 21100 lecture section appears — that's
the real "you can register now" signal, and it carries the sponsor/project
name in its description.

**Where it lives**: The user's linked UniTime "Scheduling Assistant"
(`timetable.mypurdue.purdue.edu/Timetabling/sectioning`) turned out to be
entirely behind Purdue's SSO (Microsoft/Azure AD + Duo two-factor) — not
automatable unattended. Investigating further turned up a better source:
Purdue's standard Banner "Class Search"
(`selfservice.mypurdue.purdue.edu/prod/bwckschd.p_disp_dyn_sched`) is public
and requires no login at all. Searching Subject=TDM, Course=21100 there
returns every section with its CRN and the sponsor/project title embedded in
the description, e.g. `TDM 21100 - 103` → *Cummins (Agentic Observability
Cockpit and Agentic AI Platform Advisor)*.

**Why Playwright instead of a plain HTTP request** (unlike the Data Mine
scraper): the search flow is a multi-step form POST
(`bwckgens.p_proc_term_date` → `bwckschd.p_get_crse_unsec`) sitting behind an
F5 BIG-IP load balancer. In testing, byte-identical POST bodies sent via
`curl`/`requests` were intermittently met with an empty "No classes were
found" response or bounced back to the search form, while the exact same
submission via a real (or headless) browser worked reliably — consistent with
F5's bot-fingerprinting silently serving degraded content to non-browser
clients rather than blocking outright. A headless Chromium session via
Playwright reproduces genuine browser form submission and was confirmed
reliable across repeated runs.

**Parsing**: the results page repeats `<th class="ddlabel">` (section
header, e.g. `Corporate Partners III - 14705 - TDM 21100 - 101`) followed by
a sibling `<tr>` whose `<td class="dddefault">` starts with the plain-text
project name before any of the `Associated Term:` / `Registration Dates:`
spans. CRN and section number are pulled from the header link via regex; a
couple of sections have no sponsor assigned yet and parse to an empty project
name — real data, not a parsing bug, surfaced in alerts as "(no project title
listed yet)".

**State/diffing**: identical pattern to §4.2 — `seen_sections.json`, keyed by
CRN, seeded on first run with no alert, unioned (never pruned) on every run
after. This makes a transient empty/degraded fetch from the F5 layer
self-healing: it can't cause a false "section removed" or wipe prior state,
only a missed/delayed detection until the next successful run.

**Cadence/cost trade-off**: launching headless Chromium adds real time
(~10-20s) and GitHub Actions minutes per run, unlike the near-instant Data
Mine check. At the existing 15-minute cadence this is the dominant cost of
the workflow. Acceptable for now; if Actions minutes become a constraint
(relevant mainly for private repos, which get a monthly minutes quota — public
repos get unlimited), the fix is to drop this specific check to a longer
interval, not the whole workflow.

## 10. GitHub's native cron trigger is unreliable — external trigger added

**Observed**: in the first ~4 hours after this workflow was created, GitHub's
`schedule:` trigger (offset to `7,22,37,52 * * * *` specifically to dodge
quarter-hour queue congestion, per §4.4) fired **once**, against ~16 expected
fires. Every other run in that window was a manual `workflow_dispatch`. The
workflow itself was healthy throughout (`state: active` via the Actions API,
valid cron syntax, the one scheduled run and all manual runs succeeded) — this
is GitHub's own scheduled-run queue silently dropping fires under load, a
widely-reported limitation of hosted Actions cron, not a bug in this repo's
config.

**Fix**: rather than depend on GitHub's internal scheduler at all, an
external free cron service (cron-job.org) calls
`POST /repos/{owner}/{repo}/actions/workflows/check.yml/dispatches` — the same
REST endpoint behind the existing `workflow_dispatch:` trigger — using a
fine-grained GitHub token scoped to just this repo's Actions read/write
permission. No workflow file changes were needed since `workflow_dispatch:`
already existed as a trigger; this just calls it externally on a schedule
GitHub itself won't reliably keep. See [README.md](README.md) step 6 for
setup.

The original `schedule:` block is left in the workflow as a free, harmless
backup — an occasional bonus fire from GitHub's own cron doesn't conflict
with the external trigger, since every run is idempotent (§4.2, §9).

I (the assistant) can't create the GitHub token or the cron-job.org account —
both require the user's own authenticated session — so this step is manual
for the user, documented step-by-step in the README.

## 11. Cadence tightened to ~1 minute — concurrency guard added

Once the external trigger (§10) removed GitHub's own scheduler as the
bottleneck, the user asked to shorten the interval as far as practical.
cron-job.org's fastest tier is ~1 minute, which was adopted — but two
new risks come with going that fast, both addressed directly:

- **Overlapping runs racing on `git push`.** A run takes tens of seconds
  (checkout, deps, headless Chromium, two site fetches, commit); at a
  1-minute trigger interval a slow run can still be in flight when the next
  trigger fires. Without protection, two concurrent runs both trying to
  push a `seen_*.json` update would race exactly like the manual
  "rejected — fetch first" conflict hit mid-session when a human push
  collided with an automated one. Fixed with a workflow-level
  `concurrency: { group: <workflow name>, cancel-in-progress: false }`
  block: GitHub queues at most one pending run per group behind the one
  currently executing, and a newer trigger replaces an older still-queued
  one rather than letting a backlog build up. `actions/checkout` resolves
  the ref at job-start time, so a queued run automatically picks up
  whatever the previous run just pushed — no explicit `git pull` needed in
  the commit step.
- **Slow runs make the 1-minute interval moot in practice.** Every run was
  reinstalling pip packages and downloading/installing a full Chromium
  browser (~30-60s) from scratch. Added `cache: "pip"` to
  `actions/setup-python` and an `actions/cache` step keyed on
  `requirements.txt` for Playwright's browser cache
  (`~/.cache/ms-playwright`), so most runs skip both installs entirely and
  the per-run wall-clock time — and thus how often overlap/queueing
  actually happens — drops substantially.

**Politeness/risk note carried over from §9**: hitting Purdue's Banner
system (already observed to have F5 bot-sensitivity) with a full headless
browser session every minute, indefinitely, is more aggressive than the
original 15-minute design. If Purdue's side starts responding oddly (more
"No classes found" false-empties, or the SSO-redirect behavior seen during
initial exploration), that's the first thing to suspect, and the fix is to
back off the cron-job.org interval — not to add retry/evasion logic.

## 12. Backed off to 5 minutes after real failures at 1-minute cadence

The risk flagged in §11 materialized almost immediately: within the first
~15-20 minutes of running at ~1-minute cadence, two consecutive runs (one on
the pre-concurrency-guard workflow, one on the post-guard version — so it
wasn't caused by that change) failed at the `python scraper.py` step. Root
cause wasn't confirmed — GitHub blocks anonymous/unauthenticated log
downloads even on public repos (`403 Must have admin rights`), and re-running
the identical script locally moments later succeeded cleanly — but the
timing lines up with the §11 politeness-risk prediction closely enough that
the user chose to back off rather than dig further.

**Decision**: cron-job.org interval dropped from 1 minute to 5 minutes.
Still far more responsive than the original 15-minute design and than
GitHub's native scheduler ever reliably delivered, with a much larger
margin against whatever pushed back at 1-minute frequency. The
`concurrency` guard and dependency caching added in §11 stay — they're
harmless at any interval and still protect against a slow run overlapping
the next trigger.

**Side effect worth knowing about**: while failing, the pipeline missed
alerting on a real new section (`Purdue Student Life (Leadership)`) that
had already appeared in Purdue's Class Search — confirmed by running the
scraper locally against the live site while diagnosing. This wasn't a
silent permanent loss (the failed runs never reached the `git commit` step,
so `seen_sections.json` on `main` stayed at the old baseline and the next
*successful* run would still catch it as "new" and alert), but it did sit
undetected for as long as the runs kept failing. If a run appears to have
failed, the fastest recovery is a manual `workflow_dispatch` rather than
waiting for the next scheduled trigger.

## 13. Correction: real cause was a `send_ntfy` Unicode bug, not Purdue/F5

§11 and §12's "Purdue is pushing back under load" theory was **wrong**. The
user pulled the actual traceback from a failed run's log (something I
couldn't do myself — GitHub blocks anonymous log downloads even on public
repos), and the real cause was a plain bug that had nothing to do with
request frequency:

```
UnicodeEncodeError: 'latin-1' codec can't encode character '—'
  in position 30: ordinal not in range(256)
  ...at http/client.py putheader(), called from send_ntfy()
```

`send_ntfy()` put the notification `title` directly into an HTTP `Title`
header (`headers={"Title": title, ...}`), and HTTP header values must be
Latin-1. `notify_new_sections()`'s title —
`f"New TDM {PURDUE_COURSE} section(s) open — {PURDUE_TERM_NAME}"` — contains
an em dash (U+2014), which isn't representable in Latin-1, so building the
request itself raised before any HTTP call was even made.

**Why this only surfaced now**: `send_ntfy()`/`notify_new_sections()` had
never actually executed in production before — every prior real run found
zero new sections and took the "nothing new" branch. `Purdue Student Life
(Leadership)` was the first genuine new section since this feature shipped,
so it was the first time this code path ran for real. It coincided almost
exactly with the 1-minute cadence experiment (§11), which is what made the
frequency theory look plausible — a classic correlation/causation trap. My
own local reproduction attempts during diagnosis also "succeeded" and
appeared to support that theory, but only because my local shell had no
`NTFY_TOPIC` set, so `send_ntfy()` was silently skipped there too — I was
inadvertently testing a different code path than production.

**Fix**: `send_ntfy()` now posts to ntfy's JSON publish endpoint
(`POST {server}/` with `{"topic", "title", "message", "priority"}` in the
body) instead of the header-based API, since a JSON body handles arbitrary
UTF-8 (titles/messages built from scraped company and project names could
contain far more than one em dash — accented names, curly quotes, etc. —
and the header approach was one `—` away from breaking every time
regardless of cadence). One more gotcha found while fixing: the JSON API
requires `priority` as an integer 1-5 (4 = "high"), unlike the header API
which also accepts string aliases like `"high"` — sending the string there
produces a misleading `400 "request body must be valid JSON"` even though
the JSON is syntactically valid. Verified against ntfy.sh live with a
disposable test topic before rolling out.

**Standing question for the user**: now that the real cause is fixed and
confirmed unrelated to Purdue, the 5-minute backoff from §12 is no longer
necessary on technical grounds — it was a reasonable precaution given the
information available at the time, but nothing observed actually implicates
polling frequency. Worth deciding explicitly whether to return to a faster
cadence or stay at 5 minutes, rather than carrying it forward by default.

## 14. Back to ~1 minute

Manually triggering the workflow post-fix (§13) succeeded and correctly
alerted on `Purdue Student Life (Leadership)`, confirming the fix end to
end. Per the standing question above, cron-job.org's interval was moved
back from 5 minutes to its fastest 1-minute tier — the concurrency guard
and dependency caching from §11 already handle the overlap/race concerns
at that cadence, and the actual failure (§13) had nothing to do with
frequency. The 5-minute detour was a reasonable precaution given the
information available at the time, not a wasted step — but it wasn't the
fix.
