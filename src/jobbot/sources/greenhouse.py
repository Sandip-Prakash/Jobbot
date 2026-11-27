from __future__ import annotations
from .. import http
from ..models import Job
from .common import html_to_text, iso_to_dt, parse_band
from .ashby import slug_to_name

ID = "greenhouse"


def parse(slug: str, data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        desc = html_to_text(j.get("content", ""))
        lo = hi = None
        for r in j.get("pay_input_ranges") or []:
            if r.get("min_cents"):
                lo, hi = r["min_cents"] / 100, (r.get("max_cents") or r["min_cents"]) / 100
        if not lo:
            lo, hi = parse_band(desc)
        deps = j.get("departments") or []
        out.append(Job(source="greenhouse", ats="greenhouse", company=j.get("company_name") or slug_to_name(slug),
                       title=j.get("title", ""), url=j.get("absolute_url", ""), apply_url=j.get("absolute_url", ""),
                       external_id=str(j.get("id", "")), board=slug, location=(j.get("location") or {}).get("name", ""),
                       description=desc, posted_at=iso_to_dt(j.get("first_published") or j.get("updated_at")),
                       department=deps[0].get("name", "") if deps else "",
                       comp_min=lo, comp_max=hi))
    return out


def fetch(slug: str) -> list[Job]:
    r = http.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    if r.status_code != 200:
        raise RuntimeError(f"greenhouse {slug}: HTTP {r.status_code}")
    return parse(slug, r.json())
