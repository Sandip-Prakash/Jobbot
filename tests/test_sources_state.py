from datetime import datetime, timedelta, timezone
from jobbot import ats, config, state
from jobbot.sources import ashby, greenhouse, lever, hn
from jobbot.sources.common import parse_band, html_to_text
from jobbot import pipeline
from conftest import mkjob


def test_ashby_parse_with_comp():
    data = {"jobs": [{"id": "abc", "title": "PMM", "jobUrl": "https://jobs.ashbyhq.com/acme/abc", "applyUrl": "https://jobs.ashbyhq.com/acme/abc/application",
                      "location": "New York", "isRemote": True, "employmentType": "FullTime", "publishedAt": "2026-11-26T12:00:00.000+00:00",
                      "descriptionPlain": "Do things", "compensation": {"summaryComponents": [{"compensationType": "Salary", "interval": "1 YEAR", "minValue": 150000, "maxValue": 190000}]}},
                     {"id": "x", "title": "Hidden", "isListed": False}]}
    jobs = ashby.parse("acme-co", data)
    assert len(jobs) == 1 and jobs[0].comp_min == 150000 and jobs[0].company == "Acme Co" and jobs[0].posted_at.year == 2026


def test_greenhouse_parse_and_band_from_text():
    data = {"jobs": [{"id": 5, "title": "Growth PM", "absolute_url": "https://boards.greenhouse.io/acme/jobs/5", "location": {"name": "NYC"},
                      "first_published": "2026-11-26T10:00:00-05:00", "content": "&lt;p&gt;Pay range: $140,000 - $180,000 USD&lt;/p&gt;"}]}
    j = greenhouse.parse("acme", data)[0]
    assert (j.comp_min, j.comp_max) == (140000, 180000) and j.external_id == "5"


def test_lever_parse_skips_hourly_band():
    data = [{"id": "11111111-1111-1111-1111-111111111111", "text": "PMM", "hostedUrl": "https://jobs.lever.co/acme/1", "createdAt": 1764000000000,
             "categories": {"location": "NYC", "commitment": "Full-time"}, "descriptionPlain": "x", "salaryRange": {"min": 50, "max": 80, "interval": "per-hour-wage"}}]
    j = lever.parse("acme", data)[0]
    assert j.comp_min is None and j.employment_type == "Full-time"


def test_hn_comment_parse():
    c = {"id": 1, "created_at_i": 1764000000, "text": "Acme | Product Marketing Manager | NYC | Remote<p>Apply https://jobs.lever.co/acme/11111111-1111-1111-1111-111111111111"}
    j = hn.parse_comment(c)
    assert j.company == "Acme" and j.ats == "lever" and j.board == "acme"
    assert hn.parse_comment({"id": 2, "text": "Acme | Backend Engineer | NYC"}) is None


def test_parse_band():
    assert parse_band("Range $120k - $150k") == (120000, 150000)
    assert parse_band("nothing") == (None, None)
    assert html_to_text("<p>A</p> <p>B</p>").split() == ["A", "B"]


def test_ats_detect():
    assert ats.detect("https://jobs.ashbyhq.com/acme/11111111-1111-1111-1111-111111111111")[0] == "ashby"
    assert ats.detect("https://boards.greenhouse.io/acme/jobs/123") == ("greenhouse", "acme", "123")
    assert ats.detect("https://jobs.lever.co/acme/11111111-1111-1111-1111-111111111111")[0] == "lever"
    assert ats.detect("https://acme.wd5.myworkdayjobs.com/en-US/x")[0] == "workday"
    assert ats.detect("https://example.com/jobs/1")[0] == "other"


def test_role_key_is_company_plus_role():
    assert mkjob(company="Acme, Inc.", title="Senior PMM").role_key == mkjob(company="acme inc", title="senior  pmm").role_key
    assert mkjob(title="A").role_key != mkjob(title="B").role_key


def test_state_cap_and_roles(tmp_path):
    s = state.State(tmp_path / "s.json")
    assert s.applied_today() == 0
    s.add_applied(); s.add_applied(); s.mark_role("a|b", "applied"); s.save()
    s2 = state.State(tmp_path / "s.json")
    assert s2.applied_today() == 2 and s2.role_done("a|b")


def test_daily_cap_hard_ceiling(monkeypatch):
    monkeypatch.setitem(config.guardrails(), "daily_auto_apply_cap", 99)
    config.guardrails.cache_clear()
    assert config.guardrails()["daily_auto_apply_cap"] <= 20


def test_first_run_baselines_old_postings(monkeypatch):
    now = datetime.now(timezone.utc)
    old = mkjob(title="Old PMM", external_id="o"); old.posted_at = now - timedelta(days=30)
    fresh = mkjob(title="Fresh PMM", external_id="f"); fresh.posted_at = now - timedelta(hours=2)
    nodate = mkjob(title="No Date PMM", external_id="n")
    monkeypatch.setattr(pipeline.sources, "discover", lambda: iter([("ashby:acme", [old, fresh, nodate], None)]))
    st = state.State()
    new, stats = pipeline.collect(st)
    assert [j.title for j in new] == ["Fresh PMM"] and stats["baselined"] == 2
    # second pass: source is baselined, so an undated new posting now counts as new
    again = mkjob(title="Another", external_id="z")
    monkeypatch.setattr(pipeline.sources, "discover", lambda: iter([("ashby:acme", [old, again], None)]))
    new2, _ = pipeline.collect(st)
    assert [j.title for j in new2] == ["Another"]
