#!/usr/bin/env python3
"""Checks the Data Mine projects page and Purdue's Class Search for new
2026-2027 TDM 21100 projects/sections and alerts by email/SMS."""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

SITE_URL = "https://crp.the-examples-book.com/"
TARGET_YEAR = "2026-2027"
STATE_FILE = Path(__file__).parent / "seen_projects.json"
REQUEST_TIMEOUT = 30
BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
NTFY_DEFAULT_SERVER = "https://ntfy.sh"


PURDUE_SEARCH_URL = "https://selfservice.mypurdue.purdue.edu/prod/bwckschd.p_disp_dyn_sched"
PURDUE_TERM_CODE = "202710"
PURDUE_TERM_NAME = "Fall 2026"
PURDUE_SUBJECT = "TDM"
PURDUE_COURSE = "21100"
PURDUE_SECTIONS_STATE_FILE = Path(__file__).parent / "seen_sections.json"
PURDUE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_current_projects() -> dict[str, dict]:
    resp = requests.get(
        SITE_URL,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "tdmWebScraper/1.0 (personal project-alert bot)"},
    )
    resp.raise_for_status()

    
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", id="projects-table")
    if table is None:
        raise RuntimeError("projects-table not found — site markup may have changed")

    projects = {}
    for row in table.find_all("tr"):
        year_cell = row.find("td", attrs={"data-label": "Academic Year"})
        if year_cell is None or year_cell.get_text(strip=True) != TARGET_YEAR:
            continue

        name_cell = row.find("td", attrs={"data-label": "Project Name"})
        location_cell = row.find("td", attrs={"data-label": "Location"})
        partnership_cell = row.find("td", attrs={"data-label": "Partnership"})
        semester_cell = row.find("td", attrs={"data-label": "Semester"})

        name_link = name_cell.find("a") if name_cell else None
        if name_link is None or not name_link.get("href"):
            continue

        match = re.search(r"-(\d+)/?$", name_link["href"])
        if not match:
            continue
        project_id = match.group(1)

        projects[project_id] = {
            "name": name_link.get_text(strip=True),
            "company": partnership_cell.get_text(strip=True) if partnership_cell else "",
            "location": location_cell.get_text(strip=True).rstrip(";").strip() if location_cell else "",
            "semester": semester_cell.get_text(strip=True) if semester_cell else "",
            "url": name_link["href"],
        }

    return projects


def fetch_current_sections() -> dict[str, dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=PURDUE_USER_AGENT)
        try:
            
            page.goto(PURDUE_SEARCH_URL, timeout=REQUEST_TIMEOUT * 1000, wait_until="domcontentloaded")
            page.select_option('select[name="p_term"]', PURDUE_TERM_CODE)
            with page.expect_navigation(timeout=REQUEST_TIMEOUT * 1000, wait_until="domcontentloaded"):
                page.click('input[type="submit"]')

            page.select_option('select[name="sel_subj"]', PURDUE_SUBJECT)
            page.fill('input[name="sel_crse"]', PURDUE_COURSE)
            with page.expect_navigation(timeout=REQUEST_TIMEOUT * 1000, wait_until="domcontentloaded"):
                page.click('input[type="submit"]')

            html = page.content()
        finally:
            browser.close()

    if "No classes were found" in html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    caption = soup.find("caption", string="Sections Found")
    if caption is None:
        raise RuntimeError("Purdue Class Search markup may have changed — 'Sections Found' table not found")
    table = caption.find_parent("table")

    pattern = re.compile(rf"- (\d+) - {PURDUE_SUBJECT} {PURDUE_COURSE} - (\S+)$")
    sections = {}
    for th in table.find_all("th", class_="ddlabel"):
        link = th.find("a")
        if link is None:
            continue
        match = pattern.search(link.get_text(strip=True))
        if not match:
            continue
        crn, section_number = match.groups()

        content_tr = th.find_parent("tr").find_next_sibling("tr")
        td = content_tr.find("td", class_="dddefault")
        project = (td.find(string=True) or "").strip()

        sections[crn] = {
            "section": section_number,
            "project": project,
            "url": f"https://selfservice.mypurdue.purdue.edu/prod/bwckschd.p_disp_detail_sched"
            f"?term_in={PURDUE_TERM_CODE}&crn_in={crn}",
        }

    return sections


def load_seen(state_file: Path) -> dict[str, dict]:
    if not state_file.exists():
        return None
    return json.loads(state_file.read_text())


def save_seen(state_file: Path, items: dict[str, dict]) -> None:
    state_file.write_text(json.dumps(items, indent=2, sort_keys=True) + "\n")


def send_email(subject: str, body: str, recipients: list[str]) -> None:
    api_key = os.environ["BREVO_API_KEY"]
    sender_email = os.environ["BREVO_SENDER_EMAIL"]

    
    for addr in recipients:
        resp = requests.post(
            BREVO_SEND_URL,
            timeout=REQUEST_TIMEOUT,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "sender": {"email": sender_email},
                "to": [{"email": addr}],
                "subject": subject or "(no subject)",
                "textContent": body,
            },
        )
        resp.raise_for_status()


def send_ntfy(title: str, message: str) -> None:
    topic = os.environ["NTFY_TOPIC"]
    server = os.environ.get("NTFY_SERVER", NTFY_DEFAULT_SERVER).rstrip("/")

    
    resp = requests.post(
        server,
        json={"topic": topic, "title": title, "message": message, "priority": 4},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()


def notify_new_projects(new_projects: dict[str, dict]) -> None:
    lines = [
        f"- {p['name']} ({p['company']}) — {p['location']}, {p['semester']}"
        for p in new_projects.values()
    ]
    title = f"New {TARGET_YEAR} Data Mine project(s)"
    body = (
        f"{len(new_projects)} new {TARGET_YEAR} project(s) found on the Data Mine projects page:\n\n"
        + "\n".join(lines)
        + f"\n\n{SITE_URL}"
    )

    email_to = [addr.strip() for addr in os.environ.get("ALERT_EMAIL_TO", "").split(",") if addr.strip()]
    if email_to:
        send_email(title, body, email_to)

    if os.environ.get("NTFY_TOPIC", "").strip():
        send_ntfy(title, body)


def notify_new_sections(new_sections: dict[str, dict]) -> None:
    lines = [
        f"- TDM {PURDUE_COURSE}-{s['section']} (CRN {crn}): {s['project'] or '(no project title listed yet)'}"
        for crn, s in new_sections.items()
    ]
    title = f"New TDM {PURDUE_COURSE} section(s) open — {PURDUE_TERM_NAME}"
    body = (
        f"{len(new_sections)} new TDM {PURDUE_COURSE} lecture section(s) found in Purdue's Class Search "
        f"for {PURDUE_TERM_NAME}:\n\n"
        + "\n".join(lines)
        + f"\n\n{PURDUE_SEARCH_URL}"
    )

    email_to = [addr.strip() for addr in os.environ.get("ALERT_EMAIL_TO", "").split(",") if addr.strip()]
    if email_to:
        send_email(title, body, email_to)

    if os.environ.get("NTFY_TOPIC", "").strip():
        send_ntfy(title, body)


def check_data_mine_projects() -> None:
    current = fetch_current_projects()
    seen = load_seen(STATE_FILE)

    if seen is None:
        print(f"No state file found — seeding baseline with {len(current)} current project(s), no alert sent.")
        save_seen(STATE_FILE, current)
        return

    new_ids = set(current) - set(seen)
    if new_ids:
        new_projects = {pid: current[pid] for pid in new_ids}
        print(f"Found {len(new_projects)} new project(s): {[p['name'] for p in new_projects.values()]}")
        notify_new_projects(new_projects)
    else:
        print("No new Data Mine projects.")

    save_seen(STATE_FILE, {**seen, **current})


def check_purdue_sections() -> None:
    current = fetch_current_sections()
    seen = load_seen(PURDUE_SECTIONS_STATE_FILE)

    if seen is None:
        print(f"No state file found — seeding baseline with {len(current)} current TDM {PURDUE_COURSE} section(s), no alert sent.")
        save_seen(PURDUE_SECTIONS_STATE_FILE, current)
        return

    new_crns = set(current) - set(seen)
    if new_crns:
        new_sections = {crn: current[crn] for crn in new_crns}
        print(f"Found {len(new_sections)} new TDM {PURDUE_COURSE} section(s): "
              f"{[s['project'] for s in new_sections.values()]}")
        notify_new_sections(new_sections)
    else:
        print(f"No new TDM {PURDUE_COURSE} sections.")

    save_seen(PURDUE_SECTIONS_STATE_FILE, {**seen, **current})


def main() -> int:
    check_data_mine_projects()
    check_purdue_sections()
    return 0


if __name__ == "__main__":
    sys.exit(main())
