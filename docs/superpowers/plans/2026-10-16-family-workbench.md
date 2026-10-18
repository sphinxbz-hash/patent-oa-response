# Family response workbench implementation plan

> For agentic workers: execute the approved design with subagent-driven-development. Continue through verification without another plan approval. This implements the user's 2026-10-16 three-step workflow.

**Goal:** A local web application that accepts any jurisdiction's patent number, retrieves accessible family evidence, accepts missing documents, and produces an English family-reuse response package without model calls.

**Architecture:** Python HTTP server bound to localhost, atomic per-case JSON storage, bounded public-site retrieval, evidence-preserving text extraction, deterministic claim diffs and document assembly. The existing agent skill remains a separate usable entry point; no case data enters source control.

**Tech stack:** Python 3.10+, standard library HTTP/HTML/ZIP/JSON; pypdf for PDFs; python-docx for Word output; vanilla HTML/CSS/JS UI. No API key, model SDK, hosted database or external font required.

## Approved requirements

- Input number is separate from target application. Default target is Brazil, output English, summary Chinese.
- Family report is Markdown; actual originals downloaded when available, otherwise source-specific manual instructions, never invented filenames or dates.
- Retrieve latest substantive OA plus latest complete corresponding response cycle; do not assert the latest OA has a response.
- Select actual claim versions with role/status metadata, not date alone. Publication text is provisional; post-grant claims are a reference rather than target pending claims.
- Default reuse of a selected foreign response and claim set. Optional review does not block generation. Missing evidence is labelled, not fabricated.
- Fixed outputs: English response, marked claims, clean claims plus support table, Chinese summary. Preserve raw source text/citations and disclose unresolved target-specific issues.
- Rule parsing extracts OA headings/citations and applies explicit rule-based classifications. Open-ended semantic assessment is not represented as implemented.
- Version-aware deadline and fee calculation requires source, trigger and inputs. Absent supported rule/inputs reports unverified, never zero fees or guessed deadlines.
- Changes in existing claims use underline/strike. US formal listings use statuses and clean new claims. Default output to Brazil is counsel work product.

## API contract

Case object: `id,input_number,target_country,target_application,title,status,family,documents,events,settings,exports,analysis,gaps,created_at,updated_at`.

Family row: `country,publication,application,status,url,status_source` (missing values empty; status reports source).

Document: `id,title,country,date,role,status,url,filename,local_path,text,pages,version_status,language,sha256,notes`.
`pages` is a list of `{number,text}`. Status: `downloaded`, `imported`, `manual_required`, `discovered`. Role: `oa`, `response`, `claims`, `publication`, `original`, `other`. Version status: `unknown`, `pending`, `granted`, `reference`, `publication`, `not_entered`, `auxiliary`. Text extraction can be blank for scans and must say so.

Settings: `source_member,selected_response_id,selected_claims_id,pending_claims_id,target_oa_id,original_id,review_enabled,response_override,claims_override,support_rows,deadline`.
Support row: `{claim,change,basis,source_id,page}`; an unfilled source remains unverified. Deadline: `{rule_id,trigger_date,source_url,extra_holidays,entity_status}`.

- `GET /api/cases` -> `{cases:[case summaries]}`.
- `POST /api/cases {application_number,target_country,auto_research}` -> full case. Start background research by default.
- `GET /api/cases/{id}` -> full case; poll while status is researching/generating.
- `POST /api/cases/{id}/research {}` -> case with background work started.
- `POST /api/cases/{id}/documents {filename,data_base64,role,country,date,title,source_url,version_status,language}` -> case. PDF/TXT/MD/DOCX only, 25MB limit. Also accepts `text` instead of binary with a .txt name.
- `POST /api/cases/{id}/settings {supported setting keys, target_application?}` -> case.
- `POST /api/cases/{id}/generate {}` -> case with background generation; exports populated on completion.
- `GET /api/cases/{id}/files/{document_id}` -> original file, or 404.
- `GET /api/cases/{id}/exports/{filename}` -> output with safe paths.
- `GET /api/cases/{id}/bundle` -> ZIP.
- `POST /api/demo {}` -> clearly labelled fictional complete example, generated without network. Does not claim real case success.
- JSON errors `{error:message}` with appropriate HTTP status. Mutations require same-origin browser requests; reject non-local Host and foreign Origin.

## Tasks and acceptance

- [x] Core tests first: normalization, claim segmentation/diff round-trip, version selection, blocked fetch, safe upload, unsafe path, and scan-with-no-text.
- [x] `workbench/storage.py`, `claims.py`, `retrieval.py`: bounded retrieval and persistent provenance; never accept an HTML challenge as PDF.
- [x] `workbench/research.py`: Google Patents family + publication discovery, EPO directory + matched cycle download attempts, official portal fallback guides. Preserve prior imports and log failures. Core tests use saved/public-format fixtures; real probes separate.
- [x] `workbench/analysis.py`, `drafting.py`: test complete and incomplete cases, original support provenance, target redline baseline, English output with Chinese summary, fees/deadlines unverified when missing.
- [x] `workbench/server.py`, `__main__.py`: safe localhost API and background job lifecycle; integration test create/import/configure/generate/download/reload.
- [x] `workbench/static/`: responsive Chinese case workspace with clear three-step navigation, source/version selection, upload, optional review and downloads. No fake success counters.
- [x] `workbench/README.md`, requirements, Windows launcher and CI. Document tested/unsupported source adapters and how to resume after manual downloads.
- [x] Run all tests, skill baseline check, real BR112023019754A2 probe, and import existing public evidence. Confirm missing BR OA/claims and missing EP response remain visible.
- [ ] DOCX page rendering blocked: bundled Windows runtime has no LibreOffice. Browser smoke test desktop/mobile, metadata editing, import/generate/export and blocked-network state completed; HTML redline inspected. See workbench/VERIFICATION.md.
- [x] Independent spec review then code quality review; fix material findings and rerun affected tests. Commit locally, do not publish without a separate publication action.

## Verification commands

```powershell
python -m unittest discover -s workbench/tests -v
python scripts/package_skill.py --check
python -m workbench --port 8765
```

## Portable launch

`python -m pip install -r workbench/requirements.txt` then `python -m workbench`. Windows launcher detects a local project environment, bundled runtime if present, then system Python; user data defaults to ignored `workbench-data` and is configurable with `--data-dir`.
