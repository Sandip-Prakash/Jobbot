# Jobbot

Job application agent for Sandip Prakash. Discovers new postings every ~20 min, applies hard guardrails, scores fit,
tailors a one-page resume from his own DOCX, fills simple Ashby / Greenhouse / Lever forms, sends one short outreach
email per application, and logs everything to Notion. **Ships in dry-run: nothing submits or sends until you go live.**

```
discover ─► relevance ─► hard guardrails ─► score 0-10 ─► route ─► tailor resume ─► fill/submit ─► outreach ─► Notion
 (sources/)  (filters.py)  (filters.py)     (scoring.py)  7+ auto     (resume.py     (apply/forms.py) (apollo.py,  (notion.py)
                                                          5-6 review   render.py)                    outreach.py)
                                                          <5 drop
```

## Spec → code → test

| Spec rule | Where | Tested |
|---|---|---|
| Skip explicit "no sponsorship"; apply if silent | `filters.explicit_no_sponsorship` | `test_filters.py` (7 refusals, 6 non-refusals) |
| Skip U.S. Person / ITAR / clearance / citizenship | `filters.requires_us_status` | yes |
| Skip contract / 1099 / agency | `filters.is_contract` (type, title, JD text, agency list) | yes |
| Always answer Yes to sponsorship | `answers.answer` | yes, plus against a mock form |
| Blocklist never auto-applied | `guardrails.yaml: blocklist` → status `reserved`, no resume/outreach | yes (15 names + 6 look-alikes that must NOT match) |
| Active-thread flag, no application | `guardrails.yaml: active_threads`, `notify.py` | yes |
| Cap 15–20/day, never twice per company+role | `state.py`, hard ceiling 20 in `config.py` | yes |
| Salary = upper-middle of band; no band → hold | `answers.salary_pick` (70th percentile) | yes |
| Story questions held; never invent claims | `answers.needs_story`, `grounding.py` | yes |
| "7+ years", never "10+" | `profile.yaml`, `banned_phrases` | yes |
| One-page Calibri resume from his DOCX, run-by-run replace | `resume.py` (edits only `<w:t>` text; sectPr/fonts/sizes asserted unchanged) | yes (real LibreOffice render) |
| Order Arya→Samsung→Millennial→SPI→Kutung→GM, 3/1/2/2/2/1 | `resume.find_slots` fails loudly if the template differs | yes |
| Spill → trim text, never fonts/margins | `resume.build_resume` swaps bullets to `short` variants | yes |
| Summary opens with the target title; file `Sandip_Prakash_Resume_<Company>.pdf` | `resume.clean_title`, `safe_company` | yes |
| Outreach: 3 sentences, 1 real JD requirement, 1 real achievement, 15-min ask, 1–2 numbers, no sponsorship/relocation, no "30+ GTMs"/"6.5M vehicles" | `outreach.validate` rejects, never sends a failing draft | yes |
| Dry run first; go live on Ashby/Greenhouse/Lever only | `JOBBOT_MODE`, `pipeline.preflight`; everything else → review queue | yes (end-to-end offline) |

## Setup

1. **Secrets** (GitHub → Settings → Secrets → Actions): see `.env.example`. Keep this repo **private** (the resume template has your phone/email).
2. **Notion**: `python -m jobbot.cli init-notion --parent <page id>` creates the review-queue DB; put its id in `NOTION_DATABASE_ID` and share the DB with your Notion integration.
3. **Gmail**: `python scripts/gmail_auth.py` (send-only scope) → `GMAIL_REFRESH_TOKEN`.
4. **Boards**: add Ashby/Greenhouse/Lever slugs to `config/companies.yaml`.
5. **Fill `excluded_targets`** in `config/guardrails.yaml` (your top 10–15). Live mode refuses to start while it is empty.
6. Run the **jobbot** workflow with mode `dry_run` for a few days; review `Notion` rows + the run artifact (resume PDFs, form screenshots, `log.jsonl`).
7. Go live: set repo variable `JOBBOT_MODE=live`. `python -m jobbot.cli preflight` tells you what is missing.

Local: `pip install -e ".[dev]" && python -m pytest` (needs LibreOffice, poppler, Chromium). Try a resume: `python -m jobbot.cli resume --company Acme --title "Senior Product Marketing Manager"`.

## Hosting note
GitHub Actions, not Vercel: the PDF render needs LibreOffice and Chromium, which don't fit Vercel functions. State persists on the `jobbot-state` branch; `concurrency` prevents overlapping cycles.

## Not done / not verified (read before going live)
- **Form filling is tested against mock forms only**, not live Ashby/Greenhouse/Lever pages. Real boards use custom dropdowns and captchas/emailed security codes; the filler **holds** on any of those and on any required field it can't answer. Expect a meaningful share of roles to land in review at first. Treat the dry-run screenshots as the acceptance test.
- **Discovery**: Ashby/Greenhouse/Lever/HN are parsed against documented API shapes (fixture-tested, not hit live from this sandbox). Built In and career pages use JSON-LD and are best-effort (`builtin_enabled: false` by default). **Wellfound, YC Work at a Startup, Welcome to the Jungle are not implemented** (login / bot protection); roles from them appear only if they link to an Ashby/Greenhouse/Lever page that a listed board or career page covers. Workday is detected and always routed to review.
- **Apollo free plan** may not expose people-search / email-reveal over API. The code never guesses addresses; with no verified email the row says `no_contact`.
- **E-Verify** can't be checked automatically; only the contract/agency/1099 rules are enforced.
- **Source-of-truth files** `Sandip_Job_Search_Context.md` and `Session_Context_Nov26_2026.md` were not in the upload. The bullet bank is built only from the two resumes provided. Add those files and re-check `config/bullet_bank.yaml`.
- Added by me (not in the spec, easy to remove in `guardrails.yaml`): title-keyword + US-location relevance prefilter, 72h freshness window / first-run baseline (so the first run doesn't apply to an entire board's backlog), staffing-agency name list.

## Open questions for Sandip
1. **Years**: resumes say "8+ years", form answers must say "7+". Summary currently keeps your "8+" wording. Which wins on the resume?
2. **Unapproved bullets** (`approved: false`): the "28-person team / 20+ brands" bullet conflicts with "10+ clients"; the "paid social & **search** campaigns" bullet touches Google Ads, which isn't confirmed. Approve, edit or delete.
3. **Date conflicts**: Kutung is Mar 2021–Nov 2022 in the DOCX, Jan 2021–Dec 2022 in the PDF; Millennial title differs between files. Template dates are left as-is.
4. In the DOCX template the Shiv Nadar line wraps and leaves "2018" alone on a line (template quirk; not a slot I edit). Shorten that line in the template to remove it.
5. Your DOCX embeds the bullet font Noto Sans Symbols; LibreOffice lacks the glyph and its fallback inflates line height so the *unmodified* template spills to page 2. The PDF render therefore swaps only the bullet-glyph font to Carlito (`render.RENDER_BULLET_FONT`). Text, margins and sizes are untouched.
