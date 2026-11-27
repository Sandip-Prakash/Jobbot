"""Monthly 'Ask HN: Who is hiring?' thread via the public Algolia API."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from .. import ats as atsmod, http
from ..models import Job
from .common import html_to_text

ID = "hn"
_ROLE = re.compile(r"product marketing|marketing|growth|product manager|go-to-market|gtm|strategy|operations|lifecycle|enablement|launch", re.I)


def latest_thread_id() -> str | None:
    r = http.get("https://hn.algolia.com/api/v1/search_by_date", params={"tags": "story,author_whoishiring", "hitsPerPage": 6})
    for h in r.json().get("hits", []):
        if (h.get("title") or "").lower().startswith("ask hn: who is hiring"):
            return h["objectID"]
    return None


def parse_comment(c: dict) -> Job | None:
    text = html_to_text(c.get("text") or "")
    if not text:
        return None
    head = text.split("\n")[0]
    parts = [p.strip() for p in head.split("|")]
    if len(parts) < 2:
        return None
    company = parts[0][:80]
    roles = [p for p in parts[1:] if _ROLE.search(p)]
    if not roles:
        return None
    links = re.findall(r"https?://[^\s)>\"]+", c.get("text") or "") + re.findall(r"https?://[^\s)>\"]+", text)
    apply_url = next((l for l in links if atsmod.detect(l)[0] != "other"), "") or next(iter(links), "")
    ats, board, jid = atsmod.detect(apply_url)
    posted = datetime.fromtimestamp(c["created_at_i"], tz=timezone.utc) if c.get("created_at_i") else None
    loc = next((p for p in parts[1:] if re.search(r"remote|nyc|new york|sf|san francisco|onsite|hybrid|, [A-Z]{2}\b", p, re.I)), "")
    return Job(source="hn", ats=ats, company=company, title=roles[0][:100], url=f"https://news.ycombinator.com/item?id={c['id']}",
               apply_url=apply_url, external_id=str(c["id"]), board=board, location=loc, remote="remote" in head.lower(),
               description=text, posted_at=posted)


def fetch(_=None) -> list[Job]:
    tid = latest_thread_id()
    if not tid:
        return []
    r = http.get(f"https://hn.algolia.com/api/v1/items/{tid}")
    return [j for c in r.json().get("children", []) if (j := parse_comment(c))]
