"""Tailored one-page resume from Sandip's own DOCX. Never rebuild layout: only replace text inside existing runs."""
from __future__ import annotations
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from lxml import etree
from . import config, render
from .models import Job

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
COMPANIES = [("arya", "ARYA HEALTH"), ("samsung", "SAMSUNG TV PLUS"), ("millennial", "MILLENNIAL LABS"),
             ("spi", "SPI EDGE"), ("kutung", "KUTUNG DESIGN LABS"), ("gm", "GENERAL MOTORS")]
ROLE_ORDER = [r for r, _ in COMPANIES]   # Arya -> Samsung -> Millennial -> SPI -> Kutung -> GM
HEADINGS = {"SUMMARY", "PROFESSIONAL EXPERIENCE", "EDUCATION", "PRODUCTS & AI BUILD", "TECHNICAL PROFICIENCY"}


class ResumeError(RuntimeError):
    pass


def _q(tag): return f"{{{W}}}{tag}"
def ptext(p) -> str: return "".join(p.xpath(".//w:t/text()", namespaces=NS))
def is_bullet(p) -> bool: return bool(p.xpath("./w:pPr/w:numPr", namespaces=NS))
def runs(p): return p.xpath("./w:r", namespaces=NS)


def set_run_text(run, text: str):
    """Replace the text of the run's FIRST <w:t>, leaving rPr, tabs and any later <w:t> (dates) untouched."""
    ts = run.xpath("./w:t", namespaces=NS)
    if not ts:
        raise ResumeError("run has no <w:t> to replace")
    ts[0].text = text
    ts[0].set(XML_SPACE, "preserve")


def _text_runs(p):
    return [r for r in runs(p) if r.xpath("./w:t", namespaces=NS)]


@dataclass
class Slots:
    summary: object = None
    titles: dict = field(default_factory=dict)       # role -> paragraph
    bullets: dict = field(default_factory=dict)      # role -> [paragraphs]   (experience + products)
    skills: object = None


def find_slots(body) -> Slots:
    ps = body.xpath("./w:p", namespaces=NS)
    s = Slots()
    section, role, expect_title = None, None, False
    for p in ps:
        t = ptext(p).strip()
        if t in HEADINGS:
            section, role = t, None
            continue
        if section == "SUMMARY" and t and s.summary is None:
            s.summary = p
        elif section == "PROFESSIONAL EXPERIENCE":
            for r, name in COMPANIES:
                if t.startswith(name):
                    role, expect_title = r, True
                    s.bullets[r] = []
                    break
            else:
                if role and expect_title and t:
                    s.titles[role] = p; expect_title = False
                elif role and is_bullet(p):
                    s.bullets[role].append(p)
        elif section == "PRODUCTS & AI BUILD" and is_bullet(p):
            s.bullets.setdefault("products", []).append(p)
        elif section == "TECHNICAL PROFICIENCY" and is_bullet(p):
            s.skills = p
    return s


def clean_title(raw: str) -> str:
    t = re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", raw)           # drop (Remote), [NYC] ...
    t = re.split(r"\s+[-–—|@]\s+|,\s*(?:remote|new york|nyc|us\b)", t, maxsplit=1, flags=re.I)[0]
    t = re.sub(r"\s+", " ", t).strip(" -–—,")
    small = {"and", "of", "the", "for", "in", "to", "a", "&"}
    words = [w if (w.isupper() and len(w) <= 4) or "/" in w else (w.lower() if w.lower() in small and i else w[:1].upper() + w[1:])
             for i, w in enumerate(t.split())]
    return " ".join(words)[:70]


@dataclass
class Plan:
    family: str                       # pmm | growth | product
    title: str                        # target job title (summary opens with it)
    bullet_ids: dict                  # role -> [ids]
    millennial_title: int = 0
    arya_title: int = 0
    use_short: set = field(default_factory=set)   # ids / "summary" using the short variant


def approved_by_id() -> dict:
    return {b["id"]: b for b in config.bank()["bullets"] if b.get("approved")}


def default_plan(job: Job, family: str, picks: dict | None = None) -> Plan:
    bank = config.bank()
    by_id = approved_by_id()
    jd = f"{job.title} {job.description}".lower()
    chosen = {}
    for role in ROLE_ORDER + ["products"]:
        n = bank["roles"][role]["count"]
        cands = [b for b in by_id.values() if b["role"] == role]
        want = [i for i in (picks or {}).get(role, []) if i in by_id and by_id[i]["role"] == role]
        def score(b):
            fam_bonus = 2 if family in b["tags"] else 0
            return fam_bonus + sum(1 for t in b["tags"] if t.lower() in jd)
        rest = sorted((b["id"] for b in cands if b["id"] not in want), key=lambda i: -score(by_id[i]))
        chosen[role] = (want + rest)[:n]
        if len(chosen[role]) < n:
            raise ResumeError(f"bank has only {len(chosen[role])} approved bullets for {role}, need {n}")
    return Plan(family=family, title=clean_title(job.title), bullet_ids=chosen,
                millennial_title=0 if family != "growth" else 1, arya_title=0 if family == "pmm" else 1)


def build_docx(plan: Plan, out_docx: Path, template: Path | None = None) -> dict:
    """Write the tailored DOCX. Returns {slot_name: {"text":..., "max_lines":...}} for layout verification."""
    template = template or config.TEMPLATE
    bank = config.bank()
    by_id = approved_by_id()
    zin = zipfile.ZipFile(template)
    root = etree.fromstring(zin.read("word/document.xml"))
    body = root.find(_q("body"))
    s = find_slots(body)
    checks: dict[str, dict] = {}

    if s.summary is None:
        raise ResumeError("template: summary paragraph not found")
    key = "summaries_short" if "summary" in plan.use_short else "summaries"
    summ = bank[key][plan.family].format(title=plan.title)
    set_run_text(_text_runs(s.summary)[0], summ)
    checks["summary"] = {"text": summ, "max_lines": 3}

    for role, spec in bank["roles"].items():
        if role == "products":
            continue
        paras = s.bullets.get(role, [])
        if len(paras) != spec["count"]:
            raise ResumeError(f"template has {len(paras)} bullet slots for {role}, expected {spec['count']} (3/1/2/2/2/1)")
        for p, bid in zip(paras, plan.bullet_ids[role]):
            b = by_id[bid]
            txt = b["short"] if bid in plan.use_short else b["text"]
            set_run_text(_text_runs(p)[0], txt)
            checks[bid] = {"text": txt, "max_lines": 2}
    # real titles only; bracketed function chosen from the whitelist in the bank
    for role, idx in (("arya", plan.arya_title), ("millennial", plan.millennial_title)):
        titles = bank["roles"][role]["titles"]
        set_run_text(_text_runs(s.titles[role])[0], titles[idx])

    prods = s.bullets.get("products", [])
    if len(prods) != bank["roles"]["products"]["count"]:
        raise ResumeError(f"template has {len(prods)} product slots")
    for p, bid in zip(prods, plan.bullet_ids["products"]):
        b = by_id[bid]
        tr = _text_runs(p)
        set_run_text(tr[0], b["label"])
        txt = b["short"] if bid in plan.use_short else b["text"]
        set_run_text(tr[1], txt)
        checks[bid] = {"text": b["label"] + txt, "max_lines": 2}

    sk = bank["skills"][plan.family]
    tr = _text_runs(s.skills)
    set_run_text(tr[0], sk["label"]); set_run_text(tr[1], sk["text"])
    checks["skills"] = {"text": sk["label"] + sk["text"], "max_lines": 1}

    out_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)
    return checks


def safe_company(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "Company"


def build_resume(job: Job, family: str, out_dir: Path, picks: dict | None = None, template: Path | None = None, max_rounds: int = 6) -> Path:
    """Build, render, verify; on spill swap the worst offender to its `short` variant (never touch fonts/margins)."""
    plan = default_plan(job, family, picks)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_name = f"Sandip_Prakash_Resume_{safe_company(job.company)}.pdf"
    work = out_dir / "work"
    work.mkdir(exist_ok=True)
    problems: list[str] = []
    for _ in range(max_rounds):
        docx = work / pdf_name.replace(".pdf", ".docx")
        checks = build_docx(plan, docx, template)
        pdf = render.docx_to_pdf(render.make_render_copy(docx, work / "render"), work / "render")
        problems = render.verify_layout(pdf, checks)
        if not problems:
            final = out_dir / pdf_name
            shutil.copyfile(pdf, final)
            return final
        progressed = False
        for pr in problems:
            name = pr.split(":")[0]
            if name == "page_count=2" or name.startswith("page_count"):
                # shorten everything that has a short variant, longest first
                cands = sorted((k for k in checks if k not in plan.use_short and k != "skills"),
                               key=lambda k: -len(checks[k]["text"]))
                for k in cands[:1]:
                    plan.use_short.add("summary" if k == "summary" else k); progressed = True
            elif name in checks and name not in plan.use_short and name != "skills":
                plan.use_short.add(name); progressed = True
        if not progressed:
            break
    raise ResumeError("layout check failed after trimming: " + "; ".join(problems))
