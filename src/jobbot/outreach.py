"""Three-sentence outreach: one JD requirement, one real matching achievement, ask for 15 minutes."""
from __future__ import annotations
import base64
import os
import re
from email.message import EmailMessage
from . import config, grounding, http, llm
from .models import Job
from .resume import approved_by_id

GENERIC_REQ = {"pmm": "positioning, launches and sales enablement", "growth": "lifecycle and growth marketing",
               "product": "0→1 product discovery"}


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def validate(body: str, job: Job) -> list[str]:
    probs = []
    ss = sentences(re.sub(r"^(Hi|Hello)[^\n]*\n+", "", body.strip().split("\n\nBest")[0].split("\n\nThanks")[0]))
    if len(ss) != 3:
        probs.append(f"need exactly 3 sentences, got {len(ss)}")
    n = len(grounding.numbers(body))
    if not 1 <= n <= 2:
        probs.append(f"need 1-2 numbers, found {n}")
    probs += grounding.check(body)
    if "15 minutes" not in body and "15-minute" not in body:
        probs.append("missing 15-minute ask")
    return probs


def template_draft(job: Job, contact: dict, bullet_id: str, requirement: str) -> str:
    b = approved_by_id()[bullet_id]
    first = contact.get("first_name") or "there"
    req = requirement or GENERIC_REQ.get("pmm")
    return (f"Hi {first},\n\n"
            f"I saw the {job.title} role at {job.company} and the emphasis on {req} stood out. "
            f"{b['pitch'].rstrip('.')}. "
            f"Could we grab 15 minutes this week so I can learn how your team is thinking about the role?\n\n"
            f"Best,\nSandip")


def draft(job: Job, contact: dict, picks: dict, family: str) -> tuple[str, str]:
    """-> (subject, body). Raises ValueError if nothing safe can be produced."""
    by_id = approved_by_id()
    usable = lambda i: bool(by_id.get(i, {}).get("pitch")) and 1 <= len(grounding.numbers(by_id[i]["pitch"])) <= 2
    cands = [i for ids in picks.values() for i in ids if usable(i)]
    cands = cands or [b["id"] for b in by_id.values() if usable(b["id"]) and family in b["tags"]]
    if not cands:
        raise ValueError("no pitch-able bullet")
    subject = f"{job.title}: 15 minutes?"
    if llm.available():
        for bid in cands[:3]:
            b = by_id[bid]
            sys_ = ("Write a cold email from Sandip to a hiring contact in EXACTLY three sentences after the greeting: (1) cite ONE specific requirement from the job description, "
                    "(2) one real matching achievement from the facts given, (3) ask for 15 minutes. Use 1-2 numbers total, only numbers present in the achievement. "
                    "Never mention visas, sponsorship or relocation. No flattery, no filler. Sign off 'Best,\\nSandip'. Greeting line 'Hi <first name>,'.")
            try:
                body = llm.complete(sys_, f"Contact first name: {contact.get('first_name')}\nRole: {job.title} at {job.company}\nJD excerpt:\n{job.description[:3500]}\nAchievement: {b['pitch']}", max_tokens=300).strip()
                if not validate(body, job):
                    return subject, body
            except Exception:
                break
    bid = cands[0]
    req = _first_requirement(job)
    body = template_draft(job, contact, bid, req)
    probs = validate(body, job)
    if probs:
        raise ValueError("template draft failed validation: " + "; ".join(probs))
    return subject, body


def _first_requirement(job: Job) -> str:
    jd = job.description.lower()
    for kw, phrase in (("positioning", "positioning and messaging"), ("go-to-market", "go-to-market execution"), ("launch", "product launches"),
                       ("sales enablement", "sales enablement"), ("pricing", "pricing and packaging"), ("lifecycle", "lifecycle programs"),
                       ("customer research", "customer research"), ("battlecard", "competitive battlecards")):
        if kw in jd:
            return phrase
    return GENERIC_REQ["pmm"]


# ---------------- Gmail ----------------
def gmail_available() -> bool:
    return all(os.environ.get(k) for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"))


def _gmail_token() -> str:
    r = http.request("POST", "https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GMAIL_CLIENT_ID"], "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
        "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    r.raise_for_status()
    return r.json()["access_token"]


def send_gmail(to: str, subject: str, body: str) -> str:
    m = EmailMessage()
    m["To"], m["Subject"] = to, subject
    m.set_content(body)
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
    r = http.request("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                     headers={"Authorization": f"Bearer {_gmail_token()}"}, json={"raw": raw})
    r.raise_for_status()
    return r.json().get("id", "")
