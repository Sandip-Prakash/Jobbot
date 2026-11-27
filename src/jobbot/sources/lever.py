from __future__ import annotations
from .. import http
from ..models import Job
from .common import ms_to_dt, parse_band
from .ashby import slug_to_name

ID = "lever"


def parse(slug: str, data: list) -> list[Job]:
    out = []
    for j in data:
        cat = j.get("categories") or {}
        sr = j.get("salaryRange") or {}
        desc = "\n".join([j.get("descriptionPlain", "")] + [f"{l.get('text','')}\n{l.get('content','')}" for l in j.get("lists", [])] + [j.get("additionalPlain", "")])
        lo, hi = sr.get("min"), sr.get("max")
        if sr.get("interval") and "year" not in str(sr["interval"]).lower() and "annual" not in str(sr["interval"]).lower():
            lo = hi = None   # hourly / monthly bands are not usable for the annual-salary field
        if not lo:
            lo, hi = parse_band(desc)
        out.append(Job(source="lever", ats="lever", company=slug_to_name(slug), title=j.get("text", ""), url=j.get("hostedUrl", ""),
                       apply_url=j.get("applyUrl") or j.get("hostedUrl", ""), external_id=j.get("id", ""), board=slug,
                       location=cat.get("location", "") or ", ".join(cat.get("allLocations") or []),
                       remote=j.get("workplaceType") == "remote", description=desc, posted_at=ms_to_dt(j.get("createdAt")),
                       employment_type=cat.get("commitment", ""), department=cat.get("team") or cat.get("department") or "",
                       comp_min=float(lo) if lo else None, comp_max=float(hi) if hi else None))
    return out


def fetch(slug: str) -> list[Job]:
    r = http.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    if r.status_code != 200:
        raise RuntimeError(f"lever {slug}: HTTP {r.status_code}")
    return parse(slug, r.json())
