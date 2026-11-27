"""Discovery. Each adapter returns a list[Job]; failures are isolated per source."""
from __future__ import annotations
import logging
from .. import config
from . import ashby, greenhouse, lever, hn, pages

log = logging.getLogger("jobbot.discover")
NOT_IMPLEMENTED = ["wellfound", "yc_waas", "wttj"]   # need login / bot-protected; see README


def discover():
    """Yield (source_id, jobs|None, error|None)."""
    c = config.companies()
    for mod, key in ((ashby, "ashby"), (greenhouse, "greenhouse"), (lever, "lever")):
        for slug in c.get(key) or []:
            sid = f"{key}:{slug}"
            try:
                yield sid, mod.fetch(slug), None
            except Exception as e:
                yield sid, None, str(e)
    if c.get("hn_whos_hiring", True):
        try:
            yield "hn:whoishiring", hn.fetch(), None
        except Exception as e:
            yield "hn:whoishiring", None, str(e)
    for url in c.get("career_pages") or []:
        try:
            yield f"page:{url}", pages.fetch_career_page(url), None
        except Exception as e:
            yield f"page:{url}", None, str(e)
    if c.get("builtin_enabled"):
        for city in c.get("builtin_cities", []):
            try:
                yield f"builtin:{city}", pages.fetch_builtin(city), None
            except Exception as e:
                yield f"builtin:{city}", None, str(e)
