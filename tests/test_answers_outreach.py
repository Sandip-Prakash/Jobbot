import pytest
from jobbot import answers, grounding, outreach
from conftest import mkjob


def test_sponsorship_always_yes():
    for q in ("Will you now or in the future require sponsorship?", "Do you require visa sponsorship to work in the US?"):
        assert answers.answer(q, ["Yes", "No"], mkjob()).value == "Yes"


def test_work_authorization_yes():
    assert answers.answer("Are you legally authorized to work in the United States?", ["Yes", "No"], mkjob()).value == "Yes"


def test_salary_upper_middle_of_band():
    assert answers.salary_pick(140_000, 180_000) == 168_000        # 70th percentile, rounded to 1k
    j = mkjob(); j.comp_min, j.comp_max = 100_000, 150_000
    assert answers.answer("Desired salary", None, j).value == "135000"


def test_no_band_holds_instead_of_inventing():
    a = answers.answer("What are your salary expectations?", None, mkjob())
    assert a.value is None and "band" in a.hold_reason


@pytest.mark.parametrize("q", ["Why do you want to work at Acme?", "Tell us about a time you led a launch", "Why us?"])
def test_story_questions_held(q):
    assert answers.answer(q, None, mkjob()).value is None


def test_years_is_seven_plus():
    assert answers.answer("How many years of experience do you have?", None, mkjob()).value == "7+ years"


def test_eeo_declines():
    assert "ecline" in answers.answer("Gender", ["Male", "Female", "Decline to self-identify"], mkjob()).value


def test_unknown_question_held():
    assert answers.answer("What is your favorite color?", None, mkjob()).value is None


# ---------------- grounding / outreach
@pytest.mark.parametrize("bad", ["I managed 30+ GTMs", "across 6.5M vehicles", "I have 10+ years", "I need visa sponsorship", "open to relocation",
                                 "Skilled in Adobe Creative Suite", "I use Canva daily", "HubSpot certification holder", "hands-on Google Ads"])
def test_banned_and_unconfirmed_claims_rejected(bad):
    assert grounding.check(bad)


def test_invented_number_rejected():
    assert grounding.check("I grew revenue 340% in a year")


def test_real_numbers_accepted():
    assert not grounding.check("I mapped workflows across 120+ customers into ROI models worth $5M+ in annual customer value")


def test_outreach_template_is_valid_three_sentences():
    j = mkjob()
    subj, body = outreach.draft(j, {"first_name": "Dana"}, {"millennial": ["mil-gtm"]}, "pmm")
    assert not outreach.validate(body, j), body
    assert "15 minutes" in body and len(grounding.numbers(body)) in (1, 2)
    for bad in ("sponsor", "visa", "relocat", "30+ GTMs", "6.5M"):
        assert bad.lower() not in body.lower()


def test_outreach_validator_catches_problems():
    j = mkjob()
    assert outreach.validate("Hi Dana,\n\nOne. Two.\n\nBest,\nSandip", j)
    assert any("numbers" in p for p in outreach.validate("Hi D,\n\nI did 1 and 2 and 3 things. Ok. Could we talk for 15 minutes?\n\nBest,\nSandip", j))


def test_every_pitch_has_one_or_two_numbers_or_is_skipped():
    from jobbot import config
    for b in config.bank()["bullets"]:
        if b.get("approved") and b.get("pitch"):
            n = len(grounding.numbers(b["pitch"]))
            assert n <= 2, (b["id"], n)
            assert not grounding.check(b["pitch"]), (b["id"], grounding.check(b["pitch"]))


def test_unapproved_bullets_are_never_in_grounding_corpus():
    assert "28-person" not in grounding.corpus()
