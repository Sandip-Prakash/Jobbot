"""Flags to Sandip himself (active-thread holds)."""
from __future__ import annotations
import os
from . import config
from .outreach import gmail_available, send_gmail


def flag_message(company: str, kind: str = "application or referral") -> str:
    return f"New {company} role posted, held because your {kind} is in progress."


def send_flag(company: str, job_title: str, url: str, live: bool) -> str:
    """Returns 'sent' | 'dry_run' | 'no_gmail'."""
    body = f"{flag_message(company)}\n\n{job_title}\n{url}\n"
    if not live:
        return "dry_run"
    to = os.environ.get("NOTIFY_EMAIL")
    if not (to and gmail_available()):
        return "no_gmail"
    send_gmail(to, f"[Jobbot] {company}: new role held", body)
    return "sent"
