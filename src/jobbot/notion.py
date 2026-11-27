"""Notion review-queue log. Every decision also goes to out/log.jsonl so nothing is lost if Notion is down."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from . import config, http
from .models import Decision

API = "https://api.notion.com/v1"
VER = "2022-06-28"


def _h():
    return {"Authorization": f"Bearer {os.environ['NOTION_TOKEN']}", "Notion-Version": VER, "Content-Type": "application/json"}


def available() -> bool:
    return bool(os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_DATABASE_ID"))


def _txt(s: str) -> dict:
    s = (s or "")[:1990]
    return {"rich_text": [{"text": {"content": s}}]} if s else {"rich_text": []}


def _sel(s: str) -> dict:
    return {"select": {"name": s[:90]}} if s else {"select": None}


def band_text(d: Decision) -> str:
    j = d.job
    return f"${j.comp_min:,.0f}-${j.comp_max:,.0f}" if j.comp_min and j.comp_max else ""


def run_url() -> str:
    if os.environ.get("GITHUB_RUN_ID"):
        return f"{os.environ.get('GITHUB_SERVER_URL','https://github.com')}/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return ""


def properties(d: Decision) -> dict:
    j = d.job
    return {
        "Name": {"title": [{"text": {"content": f"{j.company} — {j.title}"[:200]}}]},
        "Company": _txt(j.company), "Role": _txt(j.title), "URL": {"url": j.url or None},
        "Source": _sel(j.source), "ATS": _sel(j.ats), "Score": {"number": d.score},
        "Route": _sel(d.route), "Status": _sel(d.status), "Reason": _txt(d.reason),
        "Salary band": _txt(band_text(d)),
        "Resume": _txt(os.path.basename(d.resume_path) + (f"  (artifact: {run_url()})" if d.resume_path and run_url() else "")),
        "Contact": _txt(f"{d.contact.get('name','')} <{d.contact.get('email','')}> {d.contact.get('title','')} [{d.contact.get('kind','')}]" if d.contact else ""),
        "Outreach": _sel(d.outreach_status), "Draft email": _txt(d.email_draft),
        "Apply note": _txt(d.apply_note), "Job key": _txt(j.role_key), "Mode": _sel(config.mode()),
        "Logged": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }


def log(d: Decision) -> None:
    rec = d.to_dict(); rec["logged_at"] = datetime.now(timezone.utc).isoformat(); rec["mode"] = config.mode()
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.OUT_DIR / "log.jsonl", "a", encoding="utf8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    if not available():
        return
    r = http.request("POST", f"{API}/pages", headers=_h(), json={"parent": {"database_id": os.environ["NOTION_DATABASE_ID"]}, "properties": properties(d)})
    if r.status_code != 200:
        print(f"[notion] log failed {r.status_code}: {r.text[:200]}")


def create_database(parent_page_id: str, title: str = "Jobbot Review Queue") -> str:
    sel = {"select": {}}
    props = {"Name": {"title": {}}, "Company": {"rich_text": {}}, "Role": {"rich_text": {}}, "URL": {"url": {}},
             "Source": sel, "ATS": sel, "Score": {"number": {"format": "number"}}, "Route": sel, "Status": sel,
             "Reason": {"rich_text": {}}, "Salary band": {"rich_text": {}}, "Resume": {"rich_text": {}},
             "Contact": {"rich_text": {}}, "Outreach": sel, "Draft email": {"rich_text": {}}, "Apply note": {"rich_text": {}},
             "Job key": {"rich_text": {}}, "Mode": sel, "Logged": {"date": {}}}
    r = http.request("POST", f"{API}/databases", headers=_h(), json={"parent": {"type": "page_id", "page_id": parent_page_id},
                     "title": [{"type": "text", "text": {"content": title}}], "properties": props})
    r.raise_for_status()
    return r.json()["id"]
