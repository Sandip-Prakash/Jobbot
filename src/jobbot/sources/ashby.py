from __future__ import annotations
from .. import http
from ..models import Job
from .common import iso_to_dt, parse_band

ID = "ashby"


def parse(slug: str, data: dict) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        lo = hi = None
        for c in ((j.get("compensation") or {}).get("summaryComponents") or []):
            if c.get("compensationType") == "Salary" and "YEAR" in str(c.get("interval", "")).upper():
                lo, hi = c.get("minValue"), c.get("maxValue")
        desc = j.get("descriptionPlain") or ""
        if not lo:
            lo, hi = parse_band(desc + " " + ((j.get("compensation") or {}).get("compensationTierSummary") or ""))
        loc = j.get("location") or ""
        if j.get("isRemote") and "remote" not in loc.lower():
            loc = f"{loc} (Remote)".strip()
        jobs.append(Job(source="ashby", ats="ashby", company=slug_to_name(slug), title=j.get("title", ""), url=j.get("jobUrl", ""),
                        apply_url=j.get("applyUrl") or j.get("jobUrl", ""), external_id=j.get("id", ""), board=slug,
                        location=loc, remote=bool(j.get("isRemote")), description=desc, posted_at=iso_to_dt(j.get("publishedAt")),
                        employment_type=j.get("employmentType", ""), department=j.get("department") or j.get("team") or "",
                        comp_min=float(lo) if lo else None, comp_max=float(hi) if hi else None))
    return jobs


def slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def fetch(slug: str) -> list[Job]:
    r = http.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"})
    if r.status_code != 200:
        raise RuntimeError(f"ashby {slug}: HTTP {r.status_code}")
    return parse(slug, r.json())
