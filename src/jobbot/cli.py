from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobbot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one discovery -> apply cycle")
    r.add_argument("--live", action="store_true", help="submit applications and send email (default: dry run)")
    r.add_argument("--max-jobs", type=int)
    r.add_argument("--limit-sources", type=int)
    sub.add_parser("preflight", help="check go-live readiness")
    n = sub.add_parser("init-notion", help="create the Notion review-queue database under a parent page")
    n.add_argument("--parent", required=True, help="Notion page id the database is created in")
    rs = sub.add_parser("resume", help="build one tailored resume (for testing)")
    rs.add_argument("--company", required=True); rs.add_argument("--title", required=True)
    rs.add_argument("--family", default="pmm", choices=["pmm", "growth", "product"]); rs.add_argument("--out", default="out/test")
    rs.add_argument("--jd", default="")
    g = sub.add_parser("check", help="run the hard guardrails on a job description from stdin")
    g.add_argument("--company", required=True); g.add_argument("--title", required=True)
    a = ap.parse_args(argv)

    if getattr(a, "live", False):
        os.environ["JOBBOT_MODE"] = "live"
    from . import config
    if a.cmd == "run":
        from .pipeline import run
        run(a.limit_sources, a.max_jobs)
    elif a.cmd == "preflight":
        from .pipeline import preflight, PreflightError
        try:
            print("OK", preflight(True))
        except PreflightError as e:
            print("NOT READY FOR LIVE:\n" + str(e)); sys.exit(1)
    elif a.cmd == "init-notion":
        from . import notion
        print("NOTION_DATABASE_ID=" + notion.create_database(a.parent))
    elif a.cmd == "resume":
        from .models import Job
        from .resume import build_resume
        j = Job(source="cli", ats="other", company=a.company, title=a.title, url="", description=a.jd)
        print(build_resume(j, a.family, Path(a.out)))
    elif a.cmd == "check":
        from . import filters
        from .models import Job
        j = Job(source="cli", ats="other", company=a.company, title=a.title, url="", description=sys.stdin.read())
        print(json.dumps(filters.apply_guardrails(j).__dict__, indent=1))


if __name__ == "__main__":
    main()
