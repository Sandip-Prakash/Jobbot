"""Apollo.io contact finder (hiring manager first, recruiter as fallback). Never guesses email addresses."""
from __future__ import annotations
import os
import re
from . import http
from .models import Job

BASE = "https://api.apollo.io/api/v1"
MANAGER_TITLES = ["head of product marketing", "director of product marketing", "vp product marketing", "head of marketing", "vp marketing",
                  "director of marketing", "head of growth", "vp growth", "chief marketing officer", "product marketing manager",
                  "head of product", "vp product", "director of product", "head of strategy", "chief of staff"]
RECRUITER_TITLES = ["recruiter", "technical recruiter", "talent acquisition", "head of talent", "people operations"]


def _h():
    return {"X-Api-Key": os.environ["APOLLO_API_KEY"], "Content-Type": "application/json", "Cache-Control": "no-cache"}


def available() -> bool:
    return bool(os.environ.get("APOLLO_API_KEY"))


def company_domain(job: Job) -> str | None:
    r = http.request("POST", f"{BASE}/mixed_companies/search", headers=_h(), json={"q_organization_name": job.company, "per_page": 3})
    if r.status_code != 200:
        return None
    for o in (r.json().get("organizations") or r.json().get("accounts") or []):
        if o.get("primary_domain"):
            return o["primary_domain"]
    return None


def _search(domain: str, titles: list[str]) -> list[dict]:
    r = http.request("POST", f"{BASE}/mixed_people/api_search", headers=_h(),
                     json={"q_organization_domains_list": [domain], "person_titles": titles, "per_page": 10})
    if r.status_code != 200:
        raise RuntimeError(f"apollo search HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("people", [])


def _enrich(person: dict) -> dict | None:
    r = http.request("POST", f"{BASE}/people/match", headers=_h(), json={"id": person.get("id"), "reveal_personal_emails": False})
    if r.status_code != 200:
        return None
    p = r.json().get("person") or {}
    if p.get("email") and p.get("email_status") == "verified":
        return {"name": p.get("name"), "first_name": p.get("first_name"), "title": p.get("title"), "email": p["email"],
                "linkedin": p.get("linkedin_url", "")}
    return None


def rank_manager(people: list[dict], job: Job) -> list[dict]:
    """Prefer the person whose title sits closest to the posting's function."""
    jt = job.title.lower()
    def score(p):
        t = (p.get("title") or "").lower()
        s = 0
        if "product marketing" in jt and "product marketing" in t: s += 5
        if any(k in t for k in ("head", "director", "vp", "chief")): s += 2
        if "marketing" in t: s += 1
        return -s
    return sorted(people, key=score)


def find_contact(job: Job) -> dict | None:
    """One person per role: hiring manager, else recruiter. None if Apollo can't find a verified email."""
    if not available():
        return None
    dom = company_domain(job)
    if not dom:
        return None
    for kind, titles in (("hiring_manager", MANAGER_TITLES), ("recruiter", RECRUITER_TITLES)):
        people = _search(dom, titles)
        if kind == "hiring_manager":
            people = rank_manager(people, job)
        for p in people[:3]:
            c = _enrich(p)
            if c:
                c["kind"] = kind
                return c
    return None
