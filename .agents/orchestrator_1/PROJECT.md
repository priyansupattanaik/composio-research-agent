# Project: Composio Research Agent Validation & Deliverable Execution

## Architecture
- **Data Extraction & Upstream**: `data/first_pass.json` (100 raw extracted apps).
- **Human Verification & Corrections**: `data/human_review_checklist.md` (20 reviewed apps across 10 categories). `agent/apply_corrections.py` merges human review verdicts, calculates accuracy metrics, updates `data/verification_log.json`, and writes `data/verified.json` and `data/accuracy_report.json`.
- **Pattern Analytics**: `agent/pattern_analyzer.py` calculates P1-P8 statistical insights (auth distribution, access models, buildability, easy wins, common blockers, MCP landscape, self-serve rates, and 5 headline insights) and writes `data/patterns.json`.
- **HTML Render Engine**: `render/build_html.py` inlines `data/verified.json`, `data/patterns.json`, and `data/accuracy_report.json` into a standalone Jinja2 template, producing `output/index.html` with zero backend/CORS dependencies.
- **Test Suite**: `tests/test_validation.py` validates schema completeness, enum adherence, logical consistency, human review accuracy, P8 headline rules, deliverable file health, and external evidence URL liveness.
- **Git Deployment**: Branches `main` and `gh-pages` synchronized with clean working tree.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Pipeline Execution & Reproduction | Sequential run of `apply_corrections.py`, `pattern_analyzer.py`, `build_html.py` with exit code 0 | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Verified Dataset Integrity | `data/verified.json` contains 100 apps, 10 categories, 19 schema keys, valid enums, consistent logic | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Pattern Insights Statistics | `data/patterns.json` contains P1-P8 statistics with 5 numbered headline insight sentences | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Accuracy Report Metrics | `data/accuracy_report.json` records 20 samples, 70% first-pass accuracy, 100% post-verification | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Standalone HTML Architecture | `output/index.html` operates standalone with inlined JSON data, zero local server/CORS dependency | M2 | ORIGINAL_REQUEST §R2 |
| 6 | 100-App Table Rendering | 100 rows rendered on initial load with dynamic counter ("Showing 100 of 100 apps") | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Client-Side Search & Filtering | Real-time name search, category dropdown (10 options), verdict dropdown (5 options) updating table | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Column Header Sorting | Alphabetical, numeric (ID 1-100), and boolean (has_mcp) sorting on table column click | M2 | ORIGINAL_REQUEST §R2 |
| 9 | 4 Chart.js Visualizations | Auth Donut, Buildability Breakdown, Access Model by Category, Self-Serve Rate with non-zero data | M2 | ORIGINAL_REQUEST §R2 |
| 10 | Section F Human Audit Table | 20 sampled apps with emerald/amber/rose verdict badges and detailed human audit notes | M2 | ORIGINAL_REQUEST §R2 |
| 11 | Zero Browser Console Errors | 0 console errors and 0 network failures during interactive execution | M2 | ORIGINAL_REQUEST §R2 |
| 12 | Automated Test Suite Clean Pass | All 9 tests in `tests/test_validation.py` pass with exit code 0 | M3 | ORIGINAL_REQUEST §R3 |
| 13 | Git Tree Cleanliness | Working tree clean on `main` (ignoring runtime `.agents/` via `.gitignore`) | M3 | ORIGINAL_REQUEST §R3 |
| 14 | Branch Synchronization | `output/index.html` on `main` matches `gh-pages:output/index.html` and `gh-pages:index.html` | M3 | ORIGINAL_REQUEST §R3 |
| 15 | Adversarial Verification & Integrity Audit | Independent adversarial challenge tests and forensic integrity verification | M4 | ORIGINAL_REQUEST Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Pipeline Execution & Data Integrity | Run `apply_corrections.py`, `pattern_analyzer.py`, `build_html.py`; verify datasets | None | DONE |
| 2 | M2: Interactive Deliverable Validation | Validate `output/index.html` standalone behavior, 100 rows, search/filter/sort, 4 charts, Section F table | M1 | DONE |
| 3 | M3: Automated Test Suite & Git Deployment Sync | Ensure clean tree (`.gitignore` `.agents/`), commit regenerated artifacts, sync `gh-pages`, pass `test_validation.py` | M1, M2 | DONE |
| 4 | M4: Final E2E Verification & Forensic Integrity Audit | Reviewers, Challengers, and Forensic Auditor verify all acceptance criteria and integrity | M1, M2, M3 | DONE |

## Interface Contracts
### `apply_corrections.py` -> `data/verified.json` & `data/accuracy_report.json`
- Input: `data/first_pass.json` (100 apps), `data/human_review_checklist.md` (20 apps table)
- Output: `data/verified.json` (100 apps list), `data/accuracy_report.json` (stats dict)
- Guarantees: 100 apps, 19 fields per app, 70% first pass accuracy, 100% post verification accuracy

### `pattern_analyzer.py` -> `data/patterns.json`
- Input: `data/verified.json`
- Output: `data/patterns.json`
- Guarantees: Keys `P1_auth_distribution` to `P8_headline_insights`, exactly 5 numbered sentences in P8

### `build_html.py` -> `output/index.html`
- Input: `data/verified.json`, `data/patterns.json`, `data/accuracy_report.json`
- Output: `output/index.html`
- Guarantees: Inlined `APP_DATA`, `PATTERNS`, `ACCURACY`, standalone operation, 100 records

### `tests/test_validation.py` -> Acceptance Verification
- Input: Filesystem data files and `output/index.html`
- Output: Exit code 0, 9 tests OK

## Code Layout
- `agent/`: Pipeline scripts (`apply_corrections.py`, `pattern_analyzer.py`, `verifier.py`, `researcher.py`, `extractor.py`)
- `render/`: HTML generation script (`build_html.py`)
- `data/`: Datasets (`first_pass.json`, `human_review_checklist.md`, `verified.json`, `patterns.json`, `accuracy_report.json`, `verification_log.json`, `raw/`)
- `output/`: Standalone deliverable (`index.html`)
- `tests/`: Automated unit tests (`test_validation.py`)
- `.agents/`: Agent coordination metadata ONLY
