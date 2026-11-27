"""Render DOCX -> PDF with LibreOffice and verify layout (spec section 4)."""
from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


class RenderError(RuntimeError):
    pass


# Template bullets use "Noto Sans Symbols". LibreOffice lacks the bullet glyph in it and falls back to Inter,
# whose tall line metrics push every bullet line to ~15pt and spill the page (Word/Google Docs do not).
# For the PDF render ONLY we point the bullet glyph font at Calibri-metric Carlito. Text, fonts, spacing,
# margins and the delivered .docx are untouched.
RENDER_BULLET_FONT = "Carlito"


def make_render_copy(docx: Path, dest_dir: Path) -> Path:
    import zipfile
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / docx.name
    with zipfile.ZipFile(docx) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == "word/numbering.xml":
                data = data.decode("utf8").replace("Noto Sans Symbols", RENDER_BULLET_FONT).encode("utf8")
            zout.writestr(it, data)
    return out


def docx_to_pdf(docx: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RenderError("LibreOffice (soffice) not found; install libreoffice-writer and fonts-crosextra-carlito")
    with tempfile.TemporaryDirectory() as profile:  # isolated profile: avoids lock-ups between parallel runs
        r = subprocess.run([soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf",
                            "--outdir", str(out_dir), str(docx)], capture_output=True, text=True, timeout=180)
    pdf = out_dir / (docx.stem + ".pdf")
    if r.returncode != 0 or not pdf.exists():
        raise RenderError(f"soffice failed: {r.stderr or r.stdout}")
    return pdf


def page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))


def fonts(pdf: Path) -> list[str]:
    out = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout
    return [l.split()[0] for l in out.splitlines()[2:] if l.strip()]


def pdf_lines(pdf: Path) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def _toks(s: str) -> list[str]:
    return [t for t in (re.sub(r"[^a-z0-9]", "", w.lower()) for w in s.split()) if t]


def measure(lines: list[str], text: str) -> tuple[int, int] | None:
    """Locate `text` in the rendered lines. Returns (line_count, words_on_last_line) or None if not found."""
    want = _toks(text)
    if len(want) < 3:
        return None
    head = want[:4]
    ltoks = [_toks(l) for l in lines]
    for i, lt in enumerate(ltoks):
        # strip a leading bullet glyph (not alnum, so already dropped by _toks)
        if lt[:4] == head or (len(lt) >= 3 and lt[:3] == head[:3]):
            got, n, last = 0, 0, 0
            j = i
            while j < len(ltoks) and got < len(want):
                got += len(ltoks[j]); last = len(ltoks[j]); n += 1; j += 1
            return n, last
    return None


def verify_layout(pdf: Path, slots: dict[str, dict]) -> list[str]:
    """slots: name -> {"text": str, "max_lines": int}. Returns problems (empty = pass)."""
    problems = []
    pages = page_count(pdf)
    if pages != 1:
        problems.append(f"page_count={pages}")
    lines = pdf_lines(pdf)
    for name, s in slots.items():
        m = measure(lines, s["text"])
        if m is None:
            problems.append(f"{name}: not found in render")
            continue
        n, last = m
        if n > s["max_lines"]:
            problems.append(f"{name}: {n} lines (max {s['max_lines']})")
        elif n > 1 and last < 3:
            problems.append(f"{name}: orphan last line ({last} words)")
    return problems
