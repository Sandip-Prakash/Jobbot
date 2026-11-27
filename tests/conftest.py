import pytest
from jobbot import config
from jobbot.models import Job


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    for k in ("JOBBOT_MODE", "ANTHROPIC_API_KEY", "NOTION_TOKEN", "APOLLO_API_KEY", "GMAIL_CLIENT_ID"):
        monkeypatch.delenv(k, raising=False)
    config.reset_caches()
    yield
    config.reset_caches()


def mkjob(company="Acme", title="Senior Product Marketing Manager", desc="Own positioning, launches and sales enablement.", **kw):
    d = dict(source="ashby", ats="ashby", company=company, title=title, url="https://jobs.ashbyhq.com/acme/11111111-1111-1111-1111-111111111111",
             apply_url="https://jobs.ashbyhq.com/acme/11111111-1111-1111-1111-111111111111/application", external_id="11111111-1111-1111-1111-111111111111",
             board="acme", location="New York, NY", description=desc)
    d.update(kw)
    return Job(**d)
