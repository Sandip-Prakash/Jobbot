from __future__ import annotations
import re

_PATTERNS = [
    ("ashby", re.compile(r"https?://jobs\.ashbyhq\.com/(?P<board>[^/?#]+)/(?P<id>[0-9a-f-]{36})", re.I)),
    ("greenhouse", re.compile(r"https?://(?:job-boards|boards)\.greenhouse\.io/(?P<board>[^/?#]+)/jobs/(?P<id>\d+)", re.I)),
    ("greenhouse", re.compile(r"https?://[^/]+/.*[?&]gh_jid=(?P<id>\d+)", re.I)),   # company-hosted GH embeds (board unknown)
    ("lever", re.compile(r"https?://jobs\.lever\.co/(?P<board>[^/?#]+)/(?P<id>[0-9a-f-]{36})", re.I)),
    ("workday", re.compile(r"https?://[^/]*\.myworkdayjobs\.com/", re.I)),
]


def detect(url: str) -> tuple[str, str, str]:
    """-> (ats, board, id). ats='other' when unknown."""
    for ats, rx in _PATTERNS:
        m = rx.search(url or "")
        if m:
            d = m.groupdict()
            return ats, d.get("board", "") or "", d.get("id", "") or ""
    return "other", "", ""


def form_url(ats: str, board: str, job_id: str) -> str:
    if ats == "ashby":
        return f"https://jobs.ashbyhq.com/{board}/{job_id}/application"
    if ats == "greenhouse":
        return f"https://job-boards.greenhouse.io/{board}/jobs/{job_id}"
    if ats == "lever":
        return f"https://jobs.lever.co/{board}/{job_id}/apply"
    return ""
