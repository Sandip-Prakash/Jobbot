"""Never invent a claim, number, tool or certification (spec section 3)."""
from __future__ import annotations
import re
from . import config

_NUM = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?(?:%|x\b|\+|[MK]\b)?")
_IDIOMS = re.compile(r"\b0\s?(?:→|->)\s?1\b|\b15[- ]min(?:ute)?s?\b", re.I)   # "0→1" and the "15 minutes" ask are not claims


def numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM.findall(_IDIOMS.sub(" ", text or "")):
        m = m.strip().rstrip("+").replace(",", "")
        if m:
            out.add(m.lower())
    return out


def corpus() -> str:
    b = config.bank()
    parts = []
    for x in b["bullets"]:
        if x.get("approved"):
            parts += [x.get("text", ""), x.get("short", ""), x.get("pitch", ""), x.get("label", "")]
    parts += list(b["summaries"].values())
    p = config.profile()
    parts.append(str(p.get("work", "")))
    return "\n".join(parts)


def ungrounded_numbers(text: str, extra_allowed: str = "") -> list[str]:
    allowed = numbers(corpus() + "\n" + extra_allowed)
    return sorted(n for n in numbers(text) if n not in allowed)


def banned_hits(text: str) -> list[str]:
    low = (text or "").lower()
    p = config.profile()
    hits = [b for b in p.get("banned_phrases", []) if b.lower() in low]
    hits += [u for u in p.get("unconfirmed", []) if u.lower() in low]
    return hits


def check(text: str, extra_allowed: str = "") -> list[str]:
    """Return a list of problems; empty means the text is safe to send."""
    problems = []
    if (h := banned_hits(text)):
        problems.append(f"banned/unconfirmed: {h}")
    if (n := ungrounded_numbers(text, extra_allowed)):
        problems.append(f"numbers not in bullet bank: {n}")
    return problems
