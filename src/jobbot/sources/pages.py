"""Generic adapters that read schema.org JobPosting JSON-LD: target career pages and (best-effort) Built In."""
from __future__ import annotations
import re
from .. import http
from ..models import Job
from .common import jsonld_jobs

BUILTIN_HOSTS = {"nyc": "www.builtinnyc.com", "sf": "www.builtinsf.com", "boston": "www.builtinboston.com",
                 "seattle": "www.builtinseattle.com", "chicago": "www.builtinchicago.org", "austin": "www.builtinaustin.com",
                 "la": "www.builtinla.com"}


def fetch_career_page(url: str) -> list[Job]:
    r = http.get(url)
    jobs = jsonld_jobs(r.text, url, "career_page")
    if jobs:
        return jobs
    # listing page: follow links that look like individual postings (cap to stay polite)
    links = list(dict.fromkeys(re.findall(r'href="([^"]*(?:/job[s]?/|/careers?/|gh_jid=)[^"]+)"', r.text)))[:25]
    out = []
    for l in links:
        full = l if l.startswith("http") else re.sub(r"^(https?://[^/]+).*", r"\1", url) + l
        try:
            out += jsonld_jobs(http.get(full).text, full, "career_page")
        except Exception:
            continue
    return out


def fetch_builtin(city: str, queries=("product marketing", "go to market", "growth marketing")) -> list[Job]:
    host = BUILTIN_HOSTS[city]
    out, seen = [], set()
    for q in queries:
        r = http.get(f"https://{host}/jobs", params={"search": q})
        if r.status_code != 200:
            raise RuntimeError(f"builtin {city}: HTTP {r.status_code} (likely bot protection)")
        for l in re.findall(r'href="(/job/[^"#?]+)"', r.text)[:20]:
            if l in seen:
                continue
            seen.add(l)
            full = f"https://{host}{l}"
            try:
                out += jsonld_jobs(http.get(full).text, full, "builtin")
            except Exception:
                continue
    return out
