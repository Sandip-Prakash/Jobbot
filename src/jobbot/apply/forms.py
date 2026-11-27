"""Playwright form filler for simple Ashby / Greenhouse / Lever applications.
Conservative by design: any required field it cannot answer safely, any captcha, any security-code step => HOLD (never guess)."""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from .. import answers as ans, ats as atsmod, config
from ..models import Job


@dataclass
class ApplyResult:
    status: str                       # submitted | dry_run_ok | held | failed
    note: str = ""
    filled: list = field(default_factory=list)
    held: list = field(default_factory=list)
    screenshot: str = ""


CAPTCHA = "iframe[src*='recaptcha/api2/bframe'], iframe[src*='hcaptcha.com/captcha'], iframe[title*='challenge' i]"
JS_FIELDS = """
() => {
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const lab = e => {
    let t = '';
    if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l) t = l.innerText; }
    if (!t && e.getAttribute('aria-labelledby')) t = e.getAttribute('aria-labelledby').split(' ').map(i => (document.getElementById(i)||{}).innerText||'').join(' ');
    if (!t) t = e.getAttribute('aria-label') || '';
    if (!t) { const l = e.closest('label'); if (l) t = l.innerText; }
    if (!t) { const fs = e.closest('fieldset'); if (fs && fs.querySelector('legend')) t = fs.querySelector('legend').innerText; }
    if (!t) { const w = e.closest('[class*=field],[class*=question],[class*=Field]'); if (w) { const l = w.querySelector('label,legend'); if (l) t = l.innerText; } }
    return (t || e.placeholder || e.name || '').trim();
  };
  const out = [];
  document.querySelectorAll('input,textarea,select').forEach((e, i) => {
    const type = (e.type || e.tagName).toLowerCase();
    if (['hidden','submit','button','image','reset'].includes(type)) return;
    if (type !== 'file' && !vis(e)) return;
    e.setAttribute('data-jb', String(i));
    const label = lab(e);
    const group = (type === 'radio' || type === 'checkbox') ? (e.name || '') : '';
    let optLabel = '';
    if (group) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`) || e.closest('label'); optLabel = l ? l.innerText.trim() : e.value; }
    let q = label;
    if (group) { const fs = e.closest('fieldset,[role=group],[role=radiogroup]'); if (fs) { const lg = fs.querySelector('legend,[class*=label],label'); q = lg ? lg.innerText : label; } }
    out.push({i, type, tag: e.tagName.toLowerCase(), label: label, question: q.replace(/\\*/g,'').trim(), group, optLabel,
      required: e.required || e.getAttribute('aria-required') === 'true' || /\\*|required/i.test(q),
      options: e.tagName === 'SELECT' ? [...e.options].map(o => o.text.trim()).filter(Boolean) : null,
      role: e.getAttribute('role') || '', value: e.value || ''});
  });
  return out;
}
"""


def form_target(job: Job) -> str:
    ats, board, jid = job.ats, job.board, job.external_id
    if ats == "ashby":
        return job.apply_url if "/application" in (job.apply_url or "") else atsmod.form_url("ashby", board, jid)
    if ats == "lever":
        return job.apply_url if job.apply_url.endswith("/apply") else atsmod.form_url("lever", board, jid)
    return job.apply_url or job.url


def plan_fields(fields: list[dict], job: Job) -> tuple[list[dict], list[str]]:
    """Pure function: decide an action per field. Returns (actions, held_reasons). Unit-testable without a browser."""
    actions, held = [], []
    groups: dict[str, list[dict]] = {}
    for f in fields:
        if f["type"] in ("radio", "checkbox") and f["group"]:
            groups.setdefault(f["group"], []).append(f); continue
        q = f["question"] or f["label"]
        if f["type"] == "file":
            if re.search(r"resume|cv", q, re.I) or not f["required"] and re.search(r"resume|cv", f["label"], re.I):
                actions.append({"f": f, "kind": "file", "value": "RESUME"})
            elif f["required"]:
                held.append(f"required file upload: {q[:60]}")
            continue
        if f["tag"] == "textarea" or (f["type"] == "text" and re.search(r"\?|describe|explain|tell us|why", q, re.I) and f["required"]):
            if ans.needs_story(q):
                if f["required"]: held.append(f"personal-story question: {q[:70]}")
                continue
        a = ans.answer(q, f["options"], job, f["required"])
        if a.value is None:
            if f["required"]: held.append(a.hold_reason or f"unanswerable: {q[:70]}")
            continue
        actions.append({"f": f, "kind": "select" if f["tag"] == "select" else "fill", "value": a.value})
    for name, items in groups.items():
        q = items[0]["question"]
        opts = [i["optLabel"] for i in items]
        a = ans.answer(q, opts, job)
        if a.value is None:
            if any(i["required"] for i in items): held.append(a.hold_reason or f"unanswerable: {q[:70]}")
            continue
        pick = next((i for i in items if i["optLabel"].strip().lower() == a.value.strip().lower()), None) or \
               next((i for i in items if a.value.strip().lower() in i["optLabel"].strip().lower()), None)
        if pick is None:
            if any(i["required"] for i in items): held.append(f"no matching option for '{q[:50]}' -> {a.value}")
            continue
        actions.append({"f": pick, "kind": "check", "value": a.value})
    return actions, held


def apply(job: Job, resume_pdf: Path, submit: bool, shots_dir: Path | None = None, page_url: str | None = None) -> ApplyResult:
    from playwright.sync_api import sync_playwright
    url = page_url or form_target(job)
    shots_dir = shots_dir or (config.OUT_DIR / "shots")
    shots_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = pw.chromium.launch(headless=True, **({"executable_path": exe} if exe else {}))
        ctx = browser.new_context(viewport={"width": 1280, "height": 1800})
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_load_state("networkidle", timeout=15000)
            # Greenhouse/Ashby job pages sometimes need an "Apply" click first
            if not page.query_selector("input[type=file], input[type=email]"):
                btn = page.query_selector("a:has-text('Apply'), button:has-text('Apply')")
                if btn: btn.click(); page.wait_for_timeout(1500)
            if page.query_selector(CAPTCHA):
                return ApplyResult("held", "captcha challenge present")
            fields = page.evaluate(JS_FIELDS)
            actions, held = plan_fields(fields, job)
            if not any(a["kind"] == "file" for a in actions):
                held.append("no resume upload field found")
            if held:
                return ApplyResult("held", "; ".join(held)[:900], held=held)
            filled = []
            for a in actions:
                f = a["f"]; el = page.query_selector(f"[data-jb='{f['i']}']")
                if el is None: continue
                if a["kind"] == "file": el.set_input_files(str(resume_pdf))
                elif a["kind"] == "select": el.select_option(label=_closest(a["value"], f["options"]))
                elif a["kind"] == "check": el.check(force=True)
                else:
                    if f["role"] == "combobox":
                        el.click(); el.fill(a["value"]); page.wait_for_timeout(400); page.keyboard.press("Enter")
                    else:
                        el.fill(a["value"])
                filled.append(f"{(f['question'] or f['label'])[:40]} = {a['value'][:30]}")
            shot = str(shots_dir / f"{re.sub(r'[^a-z0-9]+','_', job.role_key)}.png")
            page.screenshot(path=shot, full_page=True)
            if not submit:
                return ApplyResult("dry_run_ok", "filled; not submitted (dry run)", filled=filled, screenshot=shot)
            sub = page.query_selector("button[type=submit], input[type=submit], button:has-text('Submit')")
            if not sub:
                return ApplyResult("held", "no submit button found", filled=filled, screenshot=shot)
            sub.click()
            page.wait_for_timeout(5000)
            body = page.inner_text("body").lower()
            if re.search(r"security code|verification code|enter the code", body):
                return ApplyResult("held", "ATS asked for an emailed security code - needs Sandip", filled=filled, screenshot=shot)
            if page.query_selector(CAPTCHA):
                return ApplyResult("held", "captcha after submit", filled=filled, screenshot=shot)
            if re.search(r"thank you|application (?:has been )?(?:submitted|received)|we(?:'|’)ve received|successfully submitted", body):
                return ApplyResult("submitted", "confirmation text detected", filled=filled, screenshot=shot)
            return ApplyResult("failed", "no confirmation detected after submit - verify manually", filled=filled, screenshot=shot)
        except Exception as e:
            return ApplyResult("failed", f"{type(e).__name__}: {e}"[:300])
        finally:
            browser.close()


def _closest(value: str, options: list[str]) -> str:
    v = value.lower()
    return next((o for o in options if o.lower() == v), None) or next((o for o in options if v in o.lower()), value)
