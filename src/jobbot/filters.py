"""Hard guardrails (spec section 2). Pure functions, no I/O - heavily unit-tested."""
from __future__ import annotations
import re
from dataclasses import dataclass
from . import config
from .models import Job, norm

# ---- sponsorship: skip only when the posting EXPLICITLY refuses. Silence = apply.
_NO_SPONSOR = [
    r"(?:unable|not able|cannot|can't|can not|won't|will not|do not|does not|don't|doesn't|not)\s+(?:to\s+)?(?:\w+\s+){0,3}?(?:sponsor|sponsorship)",
    r"no\s+(?:visa\s+|work\s+(?:visa\s+)?|immigration\s+)?sponsorship",
    r"without\s+(?:the\s+need\s+for\s+|requiring\s+|needing\s+|current\s+or\s+future\s+)?(?:visa\s+)?sponsorship",
    r"(?:sponsorship|sponsor)\s+(?:is\s+|are\s+)?not\s+(?:available|offered|provided|possible)",
    r"not\s+(?:offer|provide|eligible\s+for)\s+(?:\w+\s+){0,2}sponsorship",
    r"(?:now\s+or\s+in\s+the\s+future|current\s+or\s+future)[^.]{0,40}sponsorship",
    r"must\s+(?:not\s+)?(?:require|need)\s+(?:visa\s+)?sponsorship",
    r"sponsorship\s+(?:will\s+)?not\s+be\s+(?:available|provided|offered)",
]
_POS_SPONSOR = re.compile(r"(?:will|can|able to|happy to|do|does|may)\s+(?:\w+\s+){0,2}?sponsor|sponsorship\s+(?:is\s+)?(?:available|offered|provided)|visa sponsorship\s+available", re.I)

_US_PERSON = [
    r"\bu\.?s\.?\s+persons?\b", r"\bitar\b", r"\bexport[- ]control(?:led)?\b", r"\bsecurity\s+clearance\b",
    r"\b(?:active|current|secret|top[- ]secret|ts/sci|ts-sci|dod|public\s+trust)\s+(?:security\s+)?clearance\b",
    r"\bts\s*/\s*sci\b", r"\bclearance\s+required\b", r"\b(?:must|need to|required to)\s+(?:be|hold)\s+(?:a\s+)?u\.?s\.?\s+citizen",
    r"\bu\.?s\.?\s+citizen(?:ship)?\s+(?:is\s+)?(?:required|only|needed)", r"\bcitizenship\s+(?:is\s+)?required\b",
    r"\bonly\s+u\.?s\.?\s+citizens\b", r"\bunited\s+states\s+citizen(?:ship)?\s+(?:is\s+)?required",
    r"\bgreen\s*card\s+(?:holders?\s+)?(?:only|required)", r"\bpermanent\s+residen\w+\s+(?:status\s+)?(?:required|only)",
    r"\bfedramp\b.*\bcitizen", r"\blawful\s+permanent\s+resident\s+(?:status\s+)?required",
]

_CONTRACT_TYPES = {"contract", "contractor", "contract to hire", "temporary", "temp", "freelance", "1099", "c2c", "fixed term", "fixed-term"}
_CONTRACT_TEXT = [
    r"\b1099\b", r"\bc2c\b", r"\bcorp[- ]to[- ]corp\b", r"\bindependent\s+contractor\b", r"\bcontract[- ]to[- ]hire\b",
    r"\b\d+[- ]month\s+contract\b", r"\bcontract\s+(?:position|role|opportunity)\b", r"\bw-?2\s+contract\b", r"\bthis\s+is\s+a\s+contract\b",
    r"\bfixed[- ]term\s+contract\b", r"\bcontingent\s+worker\b",
]
_CONTRACT_TITLE = re.compile(r"\((?:contract|contractor|temp|temporary|1099|c2c)\)|\b(?:contract|contractor|freelance)\b", re.I)


@dataclass
class FilterResult:
    action: str          # pass | skip | reserved | held_active | irrelevant
    reason: str = ""
    detail: str = ""


def _hit(patterns, text):
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            s = max(0, m.start() - 40)
            return text[s:m.end() + 40].replace("\n", " ")
    return None


def explicit_no_sponsorship(text: str) -> str | None:
    """Return the offending snippet if the posting explicitly refuses sponsorship."""
    for sent in re.split(r"(?<=[.;!?\n])\s+", text):
        if "sponsor" not in sent.lower():
            continue
        if _POS_SPONSOR.search(sent) and not re.search(r"\b(?:not|no|unable|cannot|can't|won't|without)\b", sent, re.I):
            continue
        hit = _hit(_NO_SPONSOR, sent)
        if hit:
            return hit
    return None


def requires_us_status(text: str) -> str | None:
    return _hit(_US_PERSON, text)


def is_contract(job: Job) -> str | None:
    et = norm(job.employment_type)
    if et and any(c in et for c in (norm(x) for x in _CONTRACT_TYPES)):
        return f"employment type: {job.employment_type}"
    if _CONTRACT_TITLE.search(job.title):
        return f"title: {job.title}"
    hit = _hit(_CONTRACT_TEXT, job.description)
    if hit:
        return hit
    c = norm(job.company)
    for a in config.guardrails().get("agency_names", []):
        if norm(a) in c:
            return f"staffing agency: {job.company}"
    return None


def _company_matches(job: Job, names) -> bool:
    c, slug = norm(job.company), norm(job.board)
    for n in names:
        n = norm(n)
        if not n:
            continue
        if c == n or c.startswith(n + " ") or slug == n:
            return True
    return False


def blocklisted(job: Job) -> str | None:
    for canon, aliases in config.guardrails().get("blocklist", {}).items():
        if _company_matches(job, [canon, *(aliases or [])]):
            return canon
    return None


def excluded_target(job: Job) -> str | None:
    for n in config.guardrails().get("excluded_targets", []) or []:
        if _company_matches(job, [n]):
            return n
    return None


def active_thread(job: Job) -> str | None:
    for n in (config.guardrails().get("active_threads") or {}):
        if _company_matches(job, [n]):
            return n
    return None


def is_relevant(job: Job) -> tuple[bool, str]:
    g = config.guardrails()["relevance"]
    t = norm(job.title)
    if any(norm(x) in t for x in g.get("title_exclude", [])):
        return False, "title excluded"
    if not any(norm(x) in t for x in g.get("title_keywords", [])):
        return False, "title not in target families"
    if g.get("us_only", True) and not _us_location(job):
        return False, "not US-based"
    return True, ""


_STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".replace(" ", "|")
_STATE_RX = re.compile(rf",\s*(?:{_STATES})\b")
_US_HINTS = re.compile(r"\b(united states|usa|u\.s\.|us\b|new york|nyc|san francisco|sf\b|boston|seattle|chicago|austin|los angeles|remote|california|texas|massachusetts|washington|illinois|brooklyn|denver|atlanta|miami)\b", re.I)
_NON_US = re.compile(r"\b(india|uk|united kingdom|london|canada|toronto|germany|berlin|france|paris|ireland|dublin|singapore|australia|sydney|brazil|mexico|emea|apac|latam|netherlands|amsterdam|spain|poland|israel)\b", re.I)


def _us_location(job: Job) -> bool:
    loc = job.location or ""
    if not loc:
        return True  # unknown -> let the JD checks / scorer decide
    explicit_us = bool(re.search(r"united states|usa|\bus\b", loc, re.I)) or bool(_STATE_RX.search(loc))
    if explicit_us:
        return True
    if _NON_US.search(loc):
        return False
    return bool(_US_HINTS.search(loc)) or not re.search(r"[A-Za-z]", loc)


def apply_guardrails(job: Job) -> FilterResult:
    """Order matters: reserved companies first (never touched), then legal-status skips."""
    if (b := blocklisted(job)):
        return FilterResult("reserved", f"blocklisted company ({b}): Sandip talks to hiring managers first")
    if (x := excluded_target(job)):
        return FilterResult("reserved", f"top-target company ({x}): Sandip handles it himself")
    if (a := active_thread(job)):
        return FilterResult("held_active", f"active thread with {a}")
    if (c := is_contract(job)):
        return FilterResult("skip", "contract / 1099 / agency role (STEM OPT needs W-2 E-Verify employer)", c)
    text = f"{job.title}\n{job.description}"
    if (s := explicit_no_sponsorship(text)):
        return FilterResult("skip", "explicitly no sponsorship", s)
    if (u := requires_us_status(text)):
        return FilterResult("skip", "requires U.S. person / ITAR / clearance / citizenship", u)
    return FilterResult("pass")
