# Composio Research Agent

> **Evaluation Reviewers**: See [**`SUBMISSION.md`**](SUBMISSION.md) for the complete Technical Submission Dossier, architecture deep dive, anti-hallucination verification specs, and Composio Product Ops strategic roadmap.  
> **Live Deployed Deliverable**: [https://priyansupattanaik.github.io/composio-research-agent/](https://priyansupattanaik.github.io/composio-research-agent/)  
> **Test Status**: 35/35 automated tests passing (`OK`) across validation, adversarial, and CDP browser suites.

An autonomous research and verification pipeline designed for Composio's AI Product Ops engineering evaluation. The agent systematically audits 100 SaaS applications across 10 business software categories to determine their integration buildability for Composio toolkits, auditing API architecture, authentication schemes (OAuth2, API keys, basic auth), developer credential gating (self-serve vs enterprise sales), and Model Context Protocol (MCP) support. Built to produce reproducible, honest findings, the system couples high-throughput concurrent search and extraction with an automated cross-validation verification loop and human-in-the-loop sampling.

## Architecture

```text
apps.json (100 input apps)
       │
       ▼
[agent/researcher.py] ───────► data/raw/{id}_search.json & {id}_page.txt
       │                       (Serper search + BeautifulSoup scraping + NVIDIA Nemotron)
       ▼
data/first_pass.json
       │
       ▼
[agent/verifier.py --auto]
     ├── Check A: Evidence URL Liveness (HEAD/GET validation)
     ├── Check B: Corpus Auth Keyword Matching
     ├── Check C: Official Vendor MCP Verification
     └── Check D: Access Model vs Pricing Conflict Detection
     │
     ├──► data/verification_log.json
     └──► data/human_review_checklist.md (20 stratified apps)
               │
               ▼ [Human Review & Fact-Checking]
               │
[agent/apply_corrections.py]
       │
       ▼
data/verified.json (100 validated records)
       ├──► data/accuracy_report.json (Audit trail & metrics)
       │
       ▼
[agent/pattern_analyzer.py]
       │
       ▼
data/patterns.json (Distributions P1-P7 & 5 Headline Insights P8)
       │
       ▼
[render/build_html.py]
       │
       ▼
output/index.html ───────────► Static Hosting / Deployment
```

## Setup

```bash
git clone https://github.com/priyansupattanaik/composio-research-agent.git
cd composio-research-agent
cp .env.example .env
# Fill in your keys in .env:
# NVIDIA_API_KEY=nvapi-...          (preferred: NVIDIA Nemotron)
# NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
# SERPER_API_KEY=...
# Optional fallbacks: ANTHROPIC_API_KEY, OPENAI_API_KEY
pip install -r requirements.txt
```

## Quickstart (One-Command Verification)

To execute pipeline regeneration, schema integrity checks, and the automated test suite in a single command:

```bash
python scripts/verify_pipeline.py
```

## Automated Testing

The repository includes a comprehensive 35-test verification suite covering schema compliance, anti-hallucination heuristics, adversarial edge cases, and headless browser automation:

```bash
# Run validation and adversarial test suites
python -m unittest discover -s tests

# Run headless browser CDP test suite (verifies sorting, filtering, and Chart.js rendering in Chrome/Edge)
python -m unittest tests/test_interactive_deliverable.py
```

## Run the full pipeline

```bash
# Step 1: Research all 100 apps
python agent/researcher.py

# Step 2: Run auto-verification
python agent/verifier.py --auto

# Step 3: Complete human review checklist
# Open data/human_review_checklist.md
# Fill in Human Verdict and Notes columns for 20 apps
# Takes ~30 minutes

# Step 4: Apply corrections
python agent/apply_corrections.py

# Step 5: Analyze patterns
python agent/pattern_analyzer.py

# Step 6: Build HTML page
python render/build_html.py

# Step 7: Deploy
cd output && vercel --yes
```

## Estimated runtime

- `researcher.py`: ~25-40 minutes (100 apps x ~20s each with batching)
- `verifier.py`: ~10 minutes
- `human review`: ~30 minutes
- `pattern_analyzer.py` & `build_html.py`: < 1 minute

## API Keys Required

- `NVIDIA_API_KEY`: NVIDIA NIM key for Nemotron extraction (`nvidia/nemotron-3.5-lightning-30b-a3b`, with Super/Mistral-Nemotron fallbacks)
- `SERPER_API_KEY`: Google Serper API (`serper.dev` — free tier: 2,500 queries)
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`: Optional fallbacks if NVIDIA is unavailable
- `COMPOSIO_API_KEY`: Optional, for Composio platform toolkit verification

## Cost estimate

- **NVIDIA Nemotron**: hosted NIM usage for 100 structured extractions
- **Serper API**: ~300 searches used (well within free tier)
- **Total cost**: < $2.00

## Where the agent needed human help

1. **Self-serve vs Paid-only ambiguity**: Several marketing and sales tools (e.g., Ahrefs, GoHighLevel) offer free signups or standard self-serve dashboards, but gate API tokens behind premium or enterprise pricing tiers.
2. **First-party vs Community MCP servers**: LLMs frequently flag community open-source GitHub repositories as "official" vendor MCP implementations unless strictly verified against vendor namespaces.
3. **Open-Source CLI vs Hosted Services**: Applications like Sherlock are open-source Python command-line tools without a hosted API endpoint; the agent initially attempted to discover cloud endpoints before human guidance classified it as "No Public API".
4. **Institutional Fintech Underwriting**: Platforms like Ramp, Brex, and Paygent Connect allow self-serve documentation and sandbox creation, but issuing live operational credentials requires merchant agreements, KYC underwriting, or account manager approval.

## Live result

- **Live Deployed Case Study**: [https://priyansupattanaik.github.io/composio-research-agent/](https://priyansupattanaik.github.io/composio-research-agent/)
- **GitHub Repository**: [https://github.com/priyansupattanaik/composio-research-agent](https://github.com/priyansupattanaik/composio-research-agent)
