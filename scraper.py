#!/usr/bin/env python3
"""Checks the Data Mine projects page for new 2026-2027 projects and alerts by email/SMS."""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SITE_URL = "https://crp.the-examples-book.com/"
TARGET_YEAR = "2026-2027"
STATE_FILE = Path(__file__).parent / "seen_projects.json"
REQUEST_TIMEOUT = 30
BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def fetch_current_projects() -> dict[str, dict]:
    resp = requests.get(
        SITE_URL,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "tdmWebScraper/1.0 (personal project-alert bot)"},
    )
    resp.raise_for_status()

    # html.parser mis-nests this page's unclosed <td>/<tr> tags; lxml applies
    # proper HTML5 tree-construction rules and parses the table correctly.
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


def load_seen_projects() -> dict[str, dict]:
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())


def save_seen_projects(projects: dict[str, dict]) -> None:
    STATE_FILE.write_text(json.dumps(projects, indent=2, sort_keys=True) + "\n")


def send_email(subject: str, body: str, recipients: list[str]) -> None:
    api_key = os.environ["BREVO_API_KEY"]
    sender_email = os.environ["BREVO_SENDER_EMAIL"]

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
            "to": [{"email": addr} for addr in recipients],
            "subject": subject or "(no subject)",
            "textContent": body,
        },
    )
    resp.raise_for_status()


def notify_new_projects(new_projects: dict[str, dict]) -> None:
    lines = [
        f"- {p['name']} ({p['company']}) — {p['location']}, {p['semester']}"
        for p in new_projects.values()
    ]
    long_body = (
        f"{len(new_projects)} new {TARGET_YEAR} project(s) found on the Data Mine projects page:\n\n"
        + "\n".join(lines)
        + f"\n\n{SITE_URL}"
    )

    email_to = [addr.strip() for addr in os.environ.get("ALERT_EMAIL_TO", "").split(",") if addr.strip()]
    if email_to:
        send_email(f"New {TARGET_YEAR} Data Mine project(s)", long_body, email_to)

    sms_to = [addr.strip() for addr in os.environ.get("ALERT_SMS_TO", "").split(",") if addr.strip()]
    if sms_to:
        short_names = ", ".join(p["name"] for p in new_projects.values())
        short_body = f"New {TARGET_YEAR} Data Mine project(s): {short_names}"[:300]
        send_email("", short_body, sms_to)


def main() -> int:
    current = fetch_current_projects()
    seen = load_seen_projects()

    if seen is None:
        print(f"No state file found — seeding baseline with {len(current)} current project(s), no alert sent.")
        save_seen_projects(current)
        return 0

    new_ids = set(current) - set(seen)
    if new_ids:
        new_projects = {pid: current[pid] for pid in new_ids}
        print(f"Found {len(new_projects)} new project(s): {[p['name'] for p in new_projects.values()]}")
        notify_new_projects(new_projects)
    else:
        print("No new projects.")

    merged = {**seen, **current}
    save_seen_projects(merged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
