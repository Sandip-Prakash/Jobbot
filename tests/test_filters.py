import pytest
from jobbot import filters
from conftest import mkjob


@pytest.mark.parametrize("text", [
    "We are unable to sponsor visas for this role.",
    "Unfortunately we do not offer visa sponsorship.",
    "No visa sponsorship is available.",
    "Candidates must be authorized to work in the US without sponsorship now or in the future.",
    "We will not sponsor employment visas.",
    "Sponsorship is not available for this position.",
    "This role cannot provide sponsorship.",
])
def test_explicit_no_sponsorship_is_skipped(text):
    assert filters.apply_guardrails(mkjob(desc=text)).action == "skip"


@pytest.mark.parametrize("text", [
    "", "Competitive salary and benefits.",
    "We sponsor visas for the right candidates.",
    "Visa sponsorship available for qualified candidates.",
    "We are happy to sponsor H-1B transfers.",
    "Our sponsors include a16z. Sponsored content experience helps.",   # unrelated 'sponsor'
])
def test_silence_or_positive_sponsorship_passes(text):
    assert filters.apply_guardrails(mkjob(desc=text)).action == "pass"


@pytest.mark.parametrize("text", [
    "Must be a U.S. person under ITAR.", "Active TS/SCI clearance required.", "US citizenship required.",
    "Requires U.S. security clearance.", "Subject to export control regulations (ITAR/EAR).", "You must be a U.S. citizen.",
])
def test_us_person_itar_clearance_skipped(text):
    assert filters.apply_guardrails(mkjob(desc=text)).action == "skip"


@pytest.mark.parametrize("kw", [
    dict(employment_type="Contract"), dict(employment_type="Temporary"), dict(title="Product Marketing Manager (Contract)"),
    dict(desc="This is a 1099 position."), dict(desc="6-month contract, C2C welcome."), dict(company="Robert Half"),
    dict(desc="Contract-to-hire opportunity."),
])
def test_contract_roles_skipped(kw):
    assert filters.apply_guardrails(mkjob(**kw)).action == "skip"


def test_full_time_passes():
    assert filters.apply_guardrails(mkjob(employment_type="FullTime")).action == "pass"


@pytest.mark.parametrize("company", ["Microsoft", "Google LLC", "Amazon Web Services", "Meta Platforms", "OpenAI", "Perplexity AI",
                                     "Anthropic", "NVIDIA", "Salesforce", "Snowflake", "Stripe", "Netflix", "TikTok", "Apple", "GitHub"])
def test_blocklist_is_reserved(company):
    assert filters.apply_guardrails(mkjob(company=company)).action == "reserved"


@pytest.mark.parametrize("company", ["Metabase", "Applied Intuition", "Streamline", "Pineapple Labs", "Slackline", "Snowplow"])
def test_blocklist_does_not_overmatch(company):
    assert filters.apply_guardrails(mkjob(company=company)).action == "pass"


def test_blocklist_by_board_slug():
    assert filters.apply_guardrails(mkjob(company="Some Name", board="openai")).action == "reserved"


@pytest.mark.parametrize("company", ["Chime", "Brex", "Hilton", "Hinge Health", "Hilton Worldwide"])
def test_active_threads_held(company):
    assert filters.apply_guardrails(mkjob(company=company)).action == "held_active"


def test_excluded_targets_reserved(monkeypatch):
    from jobbot import config
    monkeypatch.setitem(config.guardrails(), "excluded_targets", ["Ramp"])
    assert filters.apply_guardrails(mkjob(company="Ramp")).action == "reserved"


def test_blocklist_beats_skip_reasons():   # reserved companies are never touched, whatever else the JD says
    assert filters.apply_guardrails(mkjob(company="Google", desc="unable to sponsor")).action == "reserved"


@pytest.mark.parametrize("title,loc,ok", [
    ("Senior Product Marketing Manager", "New York, NY", True), ("Lifecycle Marketing Manager", "Remote - US", True),
    ("Staff Software Engineer", "New York, NY", False), ("Product Marketing Manager", "London, UK", False),
    ("Product Marketing Manager", "", True), ("Account Executive", "NYC", False), ("Growth Marketing Manager", "Toronto, Canada", False),
])
def test_relevance(title, loc, ok):
    assert filters.is_relevant(mkjob(title=title, location=loc))[0] is ok
