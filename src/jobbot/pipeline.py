"""Discover -> filter -> score -> route -> tailor -> apply -> outreach -> log."""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from . import answers, apollo, config, filters, notion, notify, outreach, resume, scoring, sources
from .apply import forms
from .models import Decision, Job
from .state import State

log = logging.getLogger("jobbot")
AUTO_ATS = {"ashby", "greenhouse", "lever"}      # Workday + everything else: review queue only


class PreflightError(RuntimeError):
    pass


def preflight(live: bool) -> list[str]:
    """Return warnings; raise PreflightError when going live without the safety rails in place."""
    warns, errs = [], []
    g = config.guardrails()
    if not config.TEMPLATE.exists(): errs.append(f"resume template missing: {config.TEMPLATE}")
    if live:
        if not g.get("excluded_targets") and not g.get("acknowledge_empty_excluded_targets"):
            errs.append("guardrails.yaml: excluded_targets is empty (your top 10-15 companies). Fill it or set acknowledge_empty_excluded_targets: true")
        from . import llm
        if not llm.available(): errs.append("ANTHROPIC_API_KEY missing: live mode needs LLM scoring (heuristic scores never auto-apply)")
        if not notion.available(): errs.append("NOTION_TOKEN / NOTION_DATABASE_ID missing: every action must be logged to Notion")
        if not outreach.gmail_available(): warns.append("Gmail credentials missing: outreach + flags will be logged but NOT sent")
        if not apollo.available(): warns.append("APOLLO_API_KEY missing: no contacts, outreach skipped")
        if not os.environ.get("NOTIFY_EMAIL"): warns.append("NOTIFY_EMAIL missing: active-thread flags cannot be emailed")
    if errs:
        raise PreflightError("\n".join(errs))
    return warns


def _fresh(job: Job, max_h: int) -> bool:
    return bool(job.posted_at) and datetime.now(timezone.utc) - job.posted_at <= timedelta(hours=max_h)


def collect(st: State, limit_sources: int | None = None) -> tuple[list[Job], dict]:
    """New jobs only. First sight of a source baselines everything older than max_posting_age_hours."""
    max_h = config.guardrails()["max_posting_age_hours"]
    new, stats = [], {"sources": 0, "errors": [], "baselined": 0, "seen_before": 0}
    for sid, jobs, err in sources.discover():
        if limit_sources and stats["sources"] >= limit_sources: break
        stats["sources"] += 1
        if err:
            stats["errors"].append(f"{sid}: {err}"); continue
        first = not st.baselined(sid)
        for j in jobs:
            if st.seen(j.posting_key):
                stats["seen_before"] += 1; continue
            if first and not _fresh(j, max_h):
                st.mark_seen(j.posting_key, "baseline"); stats["baselined"] += 1; continue
            new.append(j)
        st.set_baselined(sid)
    new.sort(key=lambda j: j.posted_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return new, stats


def handle(job: Job, st: State, live: bool, sim_applied: list[int]) -> Decision | None:
    """Return a Decision to log, or None for silent drops (irrelevant roles)."""
    key = job.posting_key
    ok, why = filters.is_relevant(job)
    if not ok:
        st.mark_seen(key, "irrelevant"); return None
    d = Decision(job=job)
    if st.role_done(job.role_key, live):
        st.mark_seen(key, "duplicate")
        d.route, d.status, d.reason = "skip", "skipped", "already applied / queued for this company + role"; return d

    fr = filters.apply_guardrails(job)
    if fr.action == "reserved":
        st.mark_seen(key, "reserved"); d.route, d.status, d.reason = "reserved", "reserved", fr.reason; return d
    if fr.action == "held_active":
        st.mark_seen(key, "held_active")
        flag_key = f"{filters.norm(job.company)}|{job.external_id or filters.norm(job.title)}"
        d.route, d.status, d.reason = "held_active", "flagged", notify.flag_message(filters.active_thread(job) or job.company)
        if not st.flag_sent(flag_key):
            try:
                d.outreach_status = f"flag_{notify.send_flag(job.company, job.title, job.url, live)}"
                st.add_flag(flag_key)
            except Exception as e:
                d.outreach_status = f"flag_failed: {e}"[:120]
        return d
    if fr.action == "skip":
        st.mark_seen(key, "skipped"); d.route, d.status, d.reason = "skip", "skipped", f"{fr.reason} :: {fr.detail[:160]}"; return d

    sc = scoring.score_job(job)
    d.score, d.score_detail = sc.score, {"family": sc.family, "method": sc.method, "matches": sc.matches, "rationale": sc.rationale}
    d.route = scoring.route(sc)
    if d.route == "drop":
        st.mark_seen(key, "dropped"); d.status, d.reason = "skipped", f"score {sc.score} < {config.guardrails()['score_review']}"
        return d if os.environ.get("JOBBOT_LOG_DROPS") else _quiet(d)

    # ---- tailor resume (needed for both auto-apply and review)
    try:
        pdf = resume.build_resume(job, sc.family, config.OUT_DIR / "resumes" / _slug(job), sc.picks)
        d.resume_path = str(pdf)
    except Exception as e:
        st.mark_seen(key, "resume_failed")
        d.route, d.status, d.reason = "review", "needs_review", f"resume build failed: {e}"[:400]; return d

    if sc.needs_story:
        d.route = "review"; d.reason = "application asks for a personal story - held for Sandip"
    if job.ats not in AUTO_ATS and d.route == "auto_apply":
        d.route = "review"; d.reason = f"{job.ats} apply flow is not automated (review queue)"
    cap = config.guardrails()["daily_auto_apply_cap"]
    if d.route == "auto_apply" and st.applied_today() + sim_applied[0] >= cap:
        d.route = "review"; d.reason = f"daily auto-apply cap ({cap}) reached"

    if d.route == "review":
        d.status = d.status or "needs_review"; d.reason = d.reason or f"score {sc.score}: review"
        st.mark_seen(key, "review"); return d

    # ---- auto-apply
    res = forms.apply(job, Path(d.resume_path), submit=live)
    d.apply_note = f"{res.status}: {res.note}"[:900]
    if res.status == "held":
        d.route, d.status, d.reason = "review", "needs_review", f"held by form filler: {res.note}"[:400]
        st.mark_seen(key, "review"); return d
    if res.status == "failed":
        d.status, d.reason = "failed", res.note[:400]
        st.mark_seen(key, "failed"); st.mark_role(job.role_key, "attempted")   # never retry blindly: avoid double-applying
        return d
    if res.status == "submitted":
        st.add_applied(); st.mark_role(job.role_key, "applied"); st.mark_seen(key, "applied"); d.status = "applied"
    else:  # dry_run_ok
        sim_applied[0] += 1; st.mark_dry_role(job.role_key); st.mark_seen(key, "dry_run"); d.status = "dry_run"; d.reason = "would auto-apply"
    _outreach(d, sc, st, live)
    return d


def _outreach(d: Decision, sc, st: State, live: bool):
    """One person per applied role: hiring manager, else recruiter."""
    job = d.job
    try:
        contact = apollo.find_contact(job)
    except Exception as e:
        d.outreach_status = f"apollo_error: {e}"[:100]; return
    if not contact:
        d.outreach_status = "no_contact"; return
    d.contact = contact
    try:
        subject, body = outreach.draft(job, contact, sc.picks, sc.family)
    except ValueError as e:
        d.outreach_status = f"draft_failed: {e}"[:100]; return
    d.email_draft = f"Subject: {subject}\n\n{body}"
    cap = config.guardrails()["daily_outreach_cap"]
    if not live:
        d.outreach_status = "dry_run"; return
    if contact["email"] in st.d["contacted"]:
        d.outreach_status = "skipped_already_contacted"; return
    if st.emails_today() >= cap or not outreach.gmail_available():
        d.outreach_status = "queued_cap_or_no_gmail"; return
    try:
        outreach.send_gmail(contact["email"], subject, body)
        st.add_email(); st.d["contacted"][contact["email"]] = st.today(); d.outreach_status = "sent"
    except Exception as e:
        d.outreach_status = f"send_failed: {e}"[:100]


def _quiet(d: Decision):
    return None


def _slug(job: Job) -> str:
    return filters.norm(f"{job.company} {job.title}").replace(" ", "-")[:70]


def run(limit_sources: int | None = None, max_jobs: int | None = None) -> dict:
    live = config.is_live()
    warns = preflight(live)
    st = State()
    new, stats = collect(st, limit_sources)
    sim = [0]
    counts: dict[str, int] = {}
    for job in new[: max_jobs or None]:
        try:
            d = handle(job, st, live, sim)
        except Exception as e:
            log.exception("job failed"); st.mark_seen(job.posting_key, "error")
            d = Decision(job=job, route="review", status="failed", reason=f"pipeline error: {e}"[:300])
        if d is None:
            counts["irrelevant_or_dropped"] = counts.get("irrelevant_or_dropped", 0) + 1; continue
        notion.log(d)
        counts[d.status] = counts.get(d.status, 0) + 1
    st.save()
    summary = {"mode": config.mode(), "new_jobs": len(new), **stats, "outcomes": counts, "warnings": warns}
    print(summary)
    return summary
