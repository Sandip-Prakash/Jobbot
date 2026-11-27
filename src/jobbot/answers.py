"""Form answers (spec section 3). Deterministic where possible; anything unclear returns None -> hold for review."""
from __future__ import annotations
import re
from dataclasses import dataclass
from . import config, grounding, llm
from .models import Job, norm


@dataclass
class Answer:
    value: str | None          # None => cannot answer safely
    hold_reason: str = ""


STORY = re.compile(r"why (?:do you want|are you interested|us\b|this company|\w+\?)|what (?:excites|draws|attracts|motivates)|tell us (?:about a time|a story)|describe a time|why would you|cover letter|passion|in your own words|what interests you", re.I)


def salary_pick(lo: float | None, hi: float | None) -> int | None:
    """Upper-middle of the posted band."""
    if not lo or not hi:
        return None
    s = config.profile()["salary"]
    step = s.get("round_to", 1000)
    return int(round((lo + (hi - lo) * s.get("percentile", 0.7)) / step) * step)


def needs_story(question: str) -> bool:
    return bool(STORY.search(question or ""))


_EEO = re.compile(r"gender|race|ethnic|veteran|disabilit|sexual orientation|pronoun|hispanic|lgbt|transgender", re.I)


def answer(question: str, options: list[str] | None, job: Job, is_required: bool = True) -> Answer:
    q = norm(question)
    p = config.profile()
    w = p["work"]
    opt = lambda *keys: next((o for o in (options or []) if any(norm(k) == norm(o) or norm(k) in norm(o) for k in keys)), None)

    if re.search(r"sponsor", q):                             # ALWAYS yes
        return Answer(opt("yes") or "Yes")
    if re.search(r"(authorized|eligible|legally|right) to work|work authorization|legally permitted", q):
        return Answer(opt("yes") or ("Yes" if w["authorized_to_work_in_us"] else "No"))
    if _EEO.search(question):
        return Answer(opt("decline", "prefer not", "i don t wish", "do not wish") or p["eeo"]["default"])
    if re.search(r"\bfirst name\b", q): return Answer(p["first_name"])
    if re.search(r"\blast name\b|surname", q): return Answer(p["last_name"])
    if re.search(r"full name|^name$|your name", q): return Answer(p["name"])
    if re.search(r"\bemail\b", q): return Answer(p["email"])
    if re.search(r"phone|mobile", q): return Answer(p["phone"])
    if re.search(r"linkedin", q): return Answer(p["linkedin"])
    if re.search(r"portfolio|website|personal site|github", q): return Answer(p["portfolio"])
    if re.search(r"current location|city|where are you (based|located)|location", q): return Answer(p["location"])
    if re.search(r"years of (relevant |professional |work )?experience|how many years", q): return Answer(w["years_experience_answer"])
    if re.search(r"how did you hear|where did you (hear|find)|source", q):
        return Answer(opt("company website", "careers", "job board", "other", "linkedin") or "Company careers page")
    if re.search(r"salary|compensation|pay expectation|desired (base|pay)", q):
        v = salary_pick(job.comp_min, job.comp_max)
        return Answer(str(v)) if v else Answer(None, "salary asked but no posted band")
    if re.search(r"highest (level of )?education|degree", q): return Answer(w["education_highest"])
    if re.search(r"privacy|consent|acknowledge|i agree|certify|accurate", q) and options is None:
        return Answer("Yes")
    if needs_story(question):
        return Answer(None, "needs a personal story - held for Sandip")
    if re.search(r"relocat|start date|notice period|available to start|visa status|citizen|security clearance|criminal|background check|previously (worked|employed|applied)|referr", q):
        return Answer(None, f"needs Sandip's call: {question[:80]}")
    return Answer(None, f"unmapped question: {question[:80]}")


def short_answer(question: str, job: Job, max_words: int = 90) -> Answer:
    """Free-text 'short answer' built only from the bank; grounded and checked, otherwise held."""
    if needs_story(question):
        return Answer(None, "needs a personal story - held for Sandip")
    if not llm.available():
        return Answer(None, "free-text answer needs LLM; held")
    bank = "\n".join(f"- {b['text']}" for b in config.bank()["bullets"] if b.get("approved"))
    sys_ = ("Answer a job-application question in <= %d words, first person, plain and specific. Use ONLY facts in the supplied bullets. "
            "Never mention visas, sponsorship or relocation. Never invent numbers, tools or certifications. If the bullets don't support an honest answer, reply exactly: HOLD." % max_words)
    txt = llm.complete(sys_, f"Facts:\n{bank}\n\nCompany: {job.company}\nRole: {job.title}\nQuestion: {question}", max_tokens=300).strip()
    if txt == "HOLD" or grounding.check(txt):
        return Answer(None, f"could not ground answer: {grounding.check(txt) or 'model held'}")
    return Answer(txt)
