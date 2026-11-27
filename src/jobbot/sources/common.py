from __future__ import annotations
import html
import json
import re
from datetime import datetime, timezone
from ..models import Job

_TAG = re.compile(r"<[^>]+>")


def html_to_text(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", s, flags=re.I)
    s = html.unescape(_TAG.sub(" ", s))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


_MONEY = r"\$\s?(\d{2,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?\s?[kK])"
_BAND = re.compile(_MONEY + r"\s*(?:-|–|—|to|and)\s*(?:USD\s*)?" + _MONEY)


def _amt(s: str) -> float:
    s = s.replace(",", "").replace(" ", "")
    return float(s[:-1]) * 1000 if s[-1] in "kK" else float(s)


def parse_band(text: str) -> tuple[float | None, float | None]:
    """First plausible annual USD band in free text, e.g. '$140,000 - $180,000'."""
    for m in _BAND.finditer(text or ""):
        lo, hi = _amt(m.group(1)), _amt(m.group(2))
        if lo < 1000: lo *= 1000
        if hi < 1000: hi *= 1000
        if 30_000 <= lo <= hi <= 1_000_000:
            return lo, hi
    return None, None


def ms_to_dt(ms) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except Exception:
        return None


def iso_to_dt(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def jsonld_jobs(page_html: str, page_url: str, source: str) -> list[Job]:
    """schema.org JobPosting blocks -> Jobs (used by career pages and Built In)."""
    from .. import ats as atsmod
    out = []
    for blob in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html, flags=re.S | re.I):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for it in items:
            if not isinstance(it, dict) or it.get("@type") != "JobPosting":
                continue
            org = it.get("hiringOrganization") or {}
            loc = it.get("jobLocation") or {}
            if isinstance(loc, list): loc = loc[0] if loc else {}
            addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
            location = ", ".join(x for x in [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str) else ""] if x)
            if it.get("jobLocationType") == "TELECOMMUTE":
                location = (location + " Remote").strip()
            sal = ((it.get("baseSalary") or {}).get("value") or {}) if isinstance(it.get("baseSalary"), dict) else {}
            url = it.get("url") or page_url
            apply_url = it.get("directApply") and url or url
            ats, board, jid = atsmod.detect(url)
            desc = html_to_text(it.get("description", ""))
            lo, hi = sal.get("minValue"), sal.get("maxValue")
            if not lo:
                lo, hi = parse_band(desc)
            et = it.get("employmentType") or ""
            out.append(Job(source=source, ats=ats, company=org.get("name", "") if isinstance(org, dict) else str(org),
                           title=it.get("title", ""), url=url, apply_url=apply_url, external_id=jid or it.get("identifier", {}).get("value", "") if isinstance(it.get("identifier"), dict) else jid,
                           board=board, location=location, remote=it.get("jobLocationType") == "TELECOMMUTE",
                           description=desc, posted_at=iso_to_dt(it.get("datePosted")),
                           employment_type=", ".join(et) if isinstance(et, list) else et,
                           comp_min=float(lo) if lo else None, comp_max=float(hi) if hi else None))
    return out
