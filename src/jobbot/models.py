from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


def norm(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Job:
    source: str                  # ashby | greenhouse | lever | hn | builtin | career_page | workday
    ats: str                     # ashby | greenhouse | lever | workday | other
    company: str
    title: str
    url: str
    apply_url: str = ""
    external_id: str = ""
    board: str = ""              # board slug (company handle on the ATS)
    location: str = ""
    remote: bool = False
    description: str = ""        # plain text
    posted_at: Optional[datetime] = None
    employment_type: str = ""
    department: str = ""
    comp_min: Optional[float] = None
    comp_max: Optional[float] = None
    comp_currency: str = "USD"

    @property
    def role_key(self) -> str:
        """Company + role identity. One application per key, ever."""
        return f"{norm(self.company)}|{norm(self.title)}"

    @property
    def posting_key(self) -> str:
        return f"{self.source}:{self.board or norm(self.company)}:{self.external_id or norm(self.title)}"


@dataclass
class Decision:
    """Outcome of the pipeline for one job (what gets logged to Notion)."""
    job: Job
    route: str = ""          # auto_apply | review | drop | skip | reserved | held_active
    status: str = ""         # dry_run | applied | needs_review | skipped | flagged | failed | reserved
    reason: str = ""
    score: Optional[float] = None
    score_detail: dict = field(default_factory=dict)
    resume_path: str = ""
    contact: dict = field(default_factory=dict)
    email_draft: str = ""
    outreach_status: str = ""
    apply_note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["job"]["posted_at"] = self.job.posted_at.isoformat() if self.job.posted_at else None
        return d
