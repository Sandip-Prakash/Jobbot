"""Fit score 0-10 against Sandip's confirmed profile: requirement -> evidence -> gap."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from . import config, llm
from .models import Job, norm
from .resume import approved_by_id


@dataclass
class Score:
    score: float
    family: str                       # pmm | growth | product
    method: str                       # llm | heuristic
    matches: list = field(default_factory=list)      # [{requirement, evidence, gap}]
    picks: dict = field(default_factory=dict)        # role -> [bullet ids]
    rationale: str = ""
    needs_story: bool = False         # the application asks for a personal story -> hold for Sandip


def family_of(job: Job) -> str:
    t = norm(job.title)
    if any(k in t for k in ("lifecycle", "growth", "crm", "demand gen", "content", "retention", "acquisition")):
        return "growth"
    if "product manager" in t or "product management" in t or "product operations" in t or "ai product" in t:
        return "product"
    return "pmm"


def heuristic(job: Job) -> Score:
    """Cheap fallback. Never enough on its own to auto-apply in live mode."""
    t, jd = norm(job.title), norm(job.description)
    s = 3.0
    if "product marketing" in t or "go to market" in t or "gtm" in t: s += 3
    elif any(k in t for k in ("growth", "lifecycle", "product manager", "marketing manager", "strategy")): s += 2
    for kw in ("positioning", "messaging", "launch", "pricing", "enablement", "battlecard", "go to market", "ai", "b2b", "saas", "hubspot", "customer research"):
        if kw in jd: s += 0.4
    if re.search(r"\b(director|vp|vice president|head of|principal|staff)\b", job.title, re.I): s -= 1.5
    if re.search(r"\b(10|12|15)\+? years", job.description, re.I): s -= 1.5
    return Score(score=round(max(0.0, min(9.0, s)), 1), family=family_of(job), method="heuristic", rationale="keyword heuristic (no LLM key)")


SYSTEM = """You score how well a job fits ONE candidate, using only the confirmed facts supplied.
Rules: never invent skills, tools, numbers or certifications. Not confirmed (treat as GAPS if required): Adobe Creative Suite, Canva,
hands-on Google Ads / LinkedIn Ads, HubSpot certification. Candidate has 7+ years of experience (not 10+), so roles demanding 10+ years score lower.
Score 0-10 (7+ = strong fit worth applying today). Choose the resume family: pmm | growth | product.
Pick bullet ids ONLY from the approved list, per role, for the best-matching evidence.
Set needs_story=true only if the posting's application itself demands a personal story/essay."""


def score_llm(job: Job) -> Score:
    by_id = approved_by_id()
    roles = config.bank()["roles"]
    bank_txt = "\n".join(f"[{b['id']}] ({b['role']}) {b['text']}" for b in by_id.values())
    need = {r: v["count"] for r, v in roles.items()}
    user = f"""CANDIDATE FACTS (approved bullet bank):
{bank_txt}

JOB: {job.title} at {job.company} ({job.location})
{job.description[:12000]}

Return JSON: {{"score": number, "family": "pmm|growth|product", "matches": [{{"requirement": str, "evidence": str, "gap": str}}],
"picks": {{"arya": [ids], "samsung": [ids], "millennial": [ids], "spi": [ids], "kutung": [ids], "gm": [ids], "products": [ids]}},
"rationale": str, "needs_story": bool}}. Bullet counts per role: {need}."""
    d = llm.complete_json(SYSTEM, user, max_tokens=1800)
    picks = {r: [i for i in ids if i in by_id and by_id[i]["role"] == r] for r, ids in (d.get("picks") or {}).items() if r in roles}
    fam = d.get("family") if d.get("family") in ("pmm", "growth", "product") else family_of(job)
    return Score(score=max(0.0, min(10.0, float(d.get("score", 0)))), family=fam, method="llm", matches=d.get("matches", [])[:8],
                 picks=picks, rationale=str(d.get("rationale", ""))[:600], needs_story=bool(d.get("needs_story")))


def score_job(job: Job) -> Score:
    if llm.available():
        try:
            return score_llm(job)
        except Exception as e:  # network/JSON failure must not crash the run
            h = heuristic(job); h.rationale += f" (LLM failed: {e})"; return h
    return heuristic(job)


def route(score: Score) -> str:
    g = config.guardrails()
    if score.score >= g["score_auto_apply"]:
        # a heuristic score is never trusted to auto-apply
        return "auto_apply" if score.method == "llm" else "review"
    return "review" if score.score >= g["score_review"] else "drop"
