import glob
import re
import shutil
import subprocess
import pytest
from pathlib import Path
from jobbot import config, render, resume, pipeline
from jobbot.apply import forms
from conftest import mkjob

needs_office = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
FIX = Path(__file__).parent / "fixtures"


def pdf_text(p):
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout


@needs_office
@pytest.mark.parametrize("family,title", [("pmm", "Senior Product Marketing Manager (Remote)"), ("growth", "Lifecycle Marketing Manager - NYC"),
                                          ("product", "Product Manager, AI")])
def test_resume_one_page_correct_shape(tmp_path, family, title):
    j = mkjob(company="Hinge Corp", title=title, desc="positioning launches pricing lifecycle email campaigns")
    pdf = resume.build_resume(j, family, tmp_path)
    assert pdf.name == "Sandip_Prakash_Resume_Hinge_Corp.pdf"
    assert render.page_count(pdf) == 1
    txt = pdf_text(pdf)
    summary = txt.split("SUMMARY")[1].strip().splitlines()[0]
    assert summary.startswith(resume.clean_title(title))              # summary opens with the target title
    order = [txt.index(c) for c in ("ARYA HEALTH", "SAMSUNG TV PLUS", "MILLENNIAL LABS", "SPI EDGE", "KUTUNG DESIGN LABS", "GENERAL MOTORS")]
    assert order == sorted(order)                                       # Arya -> Samsung -> Millennial -> SPI -> Kutung -> GM
    assert txt.count("●") == 3 + 1 + 2 + 2 + 2 + 1 + 2 + 1             # 11 experience + 2 products + 1 skills
    for banned in ("28-person", "search campaigns", "Adobe", "Canva"):  # unapproved / unconfirmed claims never appear
        assert banned not in txt
    assert "Hinge" not in txt                                            # no other company name leaks into the file body


@needs_office
def test_title_cleanup():
    assert resume.clean_title("Sr. product marketing manager (Remote) - NYC") == "Sr. Product Marketing Manager"
    assert resume.clean_title("Head of Growth, Remote US") == "Head of Growth"


@needs_office
def test_fonts_and_margins_untouched(tmp_path):
    import zipfile, re as _re
    docx = tmp_path / "x.docx"
    plan = resume.default_plan(mkjob(), "pmm")
    resume.build_docx(plan, docx)
    new = zipfile.ZipFile(docx).read("word/document.xml").decode()
    old = zipfile.ZipFile(config.TEMPLATE).read("word/document.xml").decode()
    assert _re.findall(r"<w:sectPr.*?</w:sectPr>", new, _re.S) == _re.findall(r"<w:sectPr.*?</w:sectPr>", old, _re.S)
    assert sorted(set(_re.findall(r'w:sz w:val="(\d+)"', new))) == sorted(set(_re.findall(r'w:sz w:val="(\d+)"', old)))
    assert set(_re.findall(r'w:ascii="([^"]+)"', new)) == {"Calibri"}


@needs_office
def test_spill_is_trimmed_not_shrunk(tmp_path, monkeypatch):
    """A too-long bullet must be swapped to its short variant, never fixed by touching fonts/margins."""
    bank = config.bank()
    for b in bank["bullets"]:
        if b["id"] == "mil-gtm":
            b["text"] = b["text"] + " " + "Extended with additional filler words to force a third line in the rendered bullet paragraph. " * 2
    pdf = resume.build_resume(mkjob(title="Product Marketing Manager"), "pmm", tmp_path)
    assert render.page_count(pdf) == 1


def test_template_slot_counts():
    import zipfile
    from lxml import etree
    root = etree.fromstring(zipfile.ZipFile(config.TEMPLATE).read("word/document.xml"))
    s = resume.find_slots(root.find(resume._q("body")))
    assert [len(s.bullets[r]) for r in resume.ROLE_ORDER] == [3, 1, 2, 2, 2, 1] and len(s.bullets["products"]) == 2


# ---------------- form filler (pure planning + real browser against a mock form)
def _fields(page_html):
    from playwright.sync_api import sync_playwright
    import os
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    with sync_playwright() as pw:
        b = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page(); pg.goto(f"file://{FIX / page_html}")
        out = pg.evaluate(forms.JS_FIELDS); b.close()
    return out


def _chromium():
    import os
    c = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or (c[0] if c else None)


@pytest.fixture
def browser_env(monkeypatch):
    exe = _chromium()
    if exe:
        monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", exe)
    try:
        import playwright  # noqa
    except ImportError:
        pytest.skip("playwright not installed")


def test_plan_fields_on_mock_greenhouse(browser_env):
    acts, held = forms.plan_fields(_fields("gh_form.html"), mkjob())
    assert held == []
    vals = {a["f"]["question"]: a["value"] for a in acts}
    assert vals["Are you legally authorized to work in the United States?"] == "Yes"
    assert vals["Will you now or in the future require sponsorship?"] == "Yes"        # ALWAYS yes
    assert vals["First Name"] == "Sandip"
    assert "RESUME" in vals.values()


def test_personal_story_holds_application(browser_env):
    acts, held = forms.plan_fields(_fields("gh_form_story.html"), mkjob())
    assert any("story" in h for h in held)


def test_dry_run_fills_but_never_submits(browser_env, tmp_path):
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
    res = forms.apply(mkjob(), pdf, submit=False, shots_dir=tmp_path, page_url=f"file://{FIX / 'gh_form.html'}")
    assert res.status == "dry_run_ok" and len(res.filled) >= 6, res


def test_live_submit_detects_confirmation(browser_env, tmp_path):
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
    res = forms.apply(mkjob(), pdf, submit=True, shots_dir=tmp_path, page_url=f"file://{FIX / 'gh_form.html'}")
    assert res.status == "submitted", res


def test_story_form_is_held_not_submitted(browser_env, tmp_path):
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
    res = forms.apply(mkjob(), pdf, submit=True, shots_dir=tmp_path, page_url=f"file://{FIX / 'gh_form_story.html'}")
    assert res.status == "held"


# ---------------- end-to-end (offline): dry run applies nothing, enforces every guardrail
@needs_office
def test_pipeline_dry_run_end_to_end(monkeypatch, tmp_path, browser_env):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    jobs = [
        mkjob(company="Acme", title="Senior Product Marketing Manager", external_id="a1"),
        mkjob(company="Acme", title="Senior Product Marketing Manager", external_id="a2"),            # same company+role -> never twice
        mkjob(company="Google", title="Product Marketing Manager", external_id="g1"),                  # blocklist
        mkjob(company="Chime", title="Product Marketing Manager", external_id="c1"),                   # active thread
        mkjob(company="NoVisa", title="Product Marketing Manager", external_id="n1", desc="We are unable to sponsor."),
        mkjob(company="Staffing", title="Product Marketing Manager (Contract)", external_id="s1"),
        mkjob(company="Backend", title="Staff Backend Engineer", external_id="b1"),                   # irrelevant -> silent
        mkjob(company="Weak", title="Marketing Manager", external_id="w1", desc="generic"),
    ]
    for j in jobs: j.posted_at = now
    monkeypatch.setattr(pipeline.sources, "discover", lambda: iter([("ashby:test", jobs, None)]))
    monkeypatch.setattr(pipeline.scoring, "score_job", lambda j: pipeline.scoring.Score(
        score=3.0 if j.company == "Weak" else 8.0, family="pmm", method="llm", picks={}))
    submitted = []
    def fake_apply(job, pdf, submit, **kw):
        submitted.append(submit)
        return forms.ApplyResult("dry_run_ok" if not submit else "submitted", "ok")
    monkeypatch.setattr(pipeline.forms, "apply", fake_apply)
    logged = []
    monkeypatch.setattr(pipeline.notion, "log", lambda d: logged.append(d))
    out = pipeline.run()
    by = {(d.job.company, d.job.external_id): d for d in logged}
    assert submitted == [False]                                     # exactly one simulated apply, never a real submit
    assert by[("Acme", "a1")].status == "dry_run" and by[("Acme", "a1")].resume_path.endswith("Sandip_Prakash_Resume_Acme.pdf")
    assert by[("Acme", "a2")].route == "review" or by[("Acme", "a2")].status in ("skipped", "needs_review")
    assert by[("Google", "g1")].status == "reserved" and not by[("Google", "g1")].resume_path
    assert by[("Chime", "c1")].status == "flagged" and "held because" in by[("Chime", "c1")].reason
    assert by[("NoVisa", "n1")].status == "skipped" and by[("Staffing", "s1")].status == "skipped"
    assert ("Backend", "b1") not in by                              # irrelevant roles are silently dropped
    assert ("Weak", "w1") not in by                                 # score < 5 dropped
    # second run: nothing is re-processed
    logged.clear()
    pipeline.run()
    assert logged == []
