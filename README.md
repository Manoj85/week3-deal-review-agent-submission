# Week 3 Small Business Loan Review Assistant

Project 3B, code track. The current backend runs three Nebius-backed specialist roles: extraction, policy review with checked Python tools, and cited risk summary. Saved human review, clarification/resume, and revision history are implemented with local SQLite. The React + TypeScript + Vite workspace now supports the complete local review flow.

## User and workflow

**User:** a loan operations analyst preparing the daily small-business loan review queue. The application replaces copying proposal terms into a checklist, calculating ratios, locating supporting evidence, and drafting an initial review memo. No time-saving percentage has been measured.

**One-line goal:** help the analyst turn a proposal into a traceable six-rule review packet in a local web workspace, using three specialists and three model-selected read/calculation tools, then hand it to a human for clarification or review; the proposed acceptance target is a usable, correctly routed packet within two minutes with all six findings traceable, to be measured on reviewed cases in Week 4.

- **Extraction specialist:** identifies financial terms and explicit people/roles; Python verifies exact source spans and field consistency.
- **Policy specialist:** selects get_policy_rules and evaluate_policy; Python Decimal calculations own the six outcomes.
- **Risk specialist:** selects get_checked_evidence and drafts a cited summary; Python validates rule coverage, references and status-based actions.
- **Orchestrator:** an explicit LangGraph state machine sequences stages, chooses clarification/exception/ready routes, persists state and pauses for human input. It is deterministic orchestration, not a fourth model role.
- **Human:** supplies corrected source text, requests changes or marks a packet reviewed. SQLite preserves revisions and audit events across API restarts. No action approves or denies a loan.

Model-selected tool calls use validated JSON actions executed by Python, not native provider function calling. Reads/calculations are autonomous; source corrections and reviewer actions require explicit UI/API submissions.

## Fictional classroom policy and sample output

These six internal demonstration rules are not actual lending regulations:

| Rule | Check | Bakery sample result |
| --- | --- | --- |
| P01 | USD principal from 25,000 to 150,000 inclusive | PASS: 120,000 |
| P02 | At least 24 established operating months | PASS: 36 |
| P03 | Principal / latest-year revenue at most 0.25 | FLAG: 120,000 / 400,000 = 0.30 |
| P04 | Annual cash available / total annual debt service at least 1.25 | FLAG: 72,000 / (36,000 + 24,000) = 1.20 |
| P05 | Explicit allocation to equipment/operating working capital | PASS: 90,000 equipment + 30,000 working capital; debt refinancing/personal use explicitly excluded |
| P06 | Latest-year financials and latest three completed monthly bank statements included | FLAG: September 2026 bank statement explicitly missing |

**Sample source:** data/proposals/sample-001.md. **Complete request:** frontend/src/sample.json. Both describe the fictional Maple Street Bakery, submitted October 30, 2026. Keep that date when reproducing its document-completeness result. No real applicant data, credit-bureau dataset or external training corpus is used.

**Expected analysis:** EXCEPTIONS_FOR_REVIEW with P03/P04/P06 flagged. **Saved state:** AWAITING_REVIEW until a human action. Missing or conflicting required evidence returns UNKNOWN and routes to NEEDS_CLARIFICATION while preserving established flags. The live sample's three roles completed in six calls; that observation is not a general success-rate or latency benchmark.

## Local setup on Windows PowerShell

Use a terminal opened at this repository root, not inside backend/. The environment folder is **venv**. Replace C:\path\to\week3-deal-review-agent-submission below with your actual checkout path.

### 1 Open the project

```powershell
cd 'C:\path\to\week3-deal-review-agent-submission'
python --version
```

Python 3.14.2 is the runtime verified for this submission. Earlier development checkpoints also used Python 3.12; the full current submission has not been reverified on Python 3.12. Do not run venv creation over an existing environment when switching Python versions; use a fresh environment and reinstall dependencies.

### 2 Create the environment once

Run once on a fresh checkout. Skip only if this checkout already has a working venv using the correct Python version.

```powershell
python -m venv venv
```

Creating a venv does not install FastAPI, Uvicorn, or our application dependencies.

### 3 Activate the environment

Run this in every new PowerShell terminal used for the project:

```powershell
.\venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable)"
```

The printed interpreter must end in this project's `venv\Scripts\python.exe`. The prompt will usually show `(venv)`.

### 4 Install dependencies

Run after creating the environment, and again when dependencies change:

```powershell
python -m pip install -r backend/requirements-lock.txt
python -m uvicorn --version
```

Do not continue to startup if installation failed. Uvicorn is included in our dependency files; no global Uvicorn installation is needed.

### Configure the model before starting the backend

**Fresh checkout only:** create the ignored root .env from the safe template. Preserve an existing .env:

```powershell
if (!(Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

Open .env in your editor and fill in your own account settings:

```dotenv
EXTRACTION_MODE=nebius
NEBIUS_API_KEY=your-nebius-key
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_CHAT_MODEL=nvidia/Nemotron-3_5-Lightning
REVIEW_DATA_DIR=local_data
```

The model shown is the one used for recorded live checks; use an accessible model in your account. Keep .env private and never put its key in frontend files or Vite variables. Restart the API after editing it. Missing credentials stop processing; there is no silent offline fallback.

**Optional offline demonstration:** set EXTRACTION_MODE=offline_sample_parser in .env and restart. This uses the narrow sample-format parser and no model credits; it does not demonstrate the live three-agent behavior. Backend/browser tests explicitly select offline mode independently of the live .env.

### 5 Start the backend

Stay at the repository root with venv activated:

```powershell
python -m uvicorn backend.app.main:app --reload --reload-dir backend --host 127.0.0.1 --port 8013
```

Keep that terminal running. Open [API documentation](http://127.0.0.1:8013/docs) or [health check](http://127.0.0.1:8013/health). Stop the server with Ctrl+C. This opens the backend's API documentation. Start the React workspace in a second terminal using the steps below.

`backend.app.main` means `backend/app/main.py`; `:app` selects the FastAPI object named `app`. `--reload` restarts the server when source files change; `--reload-dir backend` watches our backend code rather than installed packages in venv. Here app/ is inside backend/, so use `backend.app.main:app` from the root.

## Start again on another day

Once dependencies are installed, you only need:

```powershell
cd 'C:\path\to\week3-deal-review-agent-submission'
.\venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --reload-dir backend --host 127.0.0.1 --port 8013
```

If activation is unavailable, this equivalent command selects the environment directly:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --reload-dir backend --host 127.0.0.1 --port 8013
```

## Run the sample and tests

In a second terminal, open the same repository root and activate venv, then run:

```powershell
python -m backend.run_sample
python -m pytest -q
```

**The CLI sample uses Nebius credits in live mode.** The tests are offline. The CLI sample is a one-shot preview, not a saved lifecycle record. It saves its full request/review under work/checkpoint-01/. Expected route: EXCEPTIONS_FOR_REVIEW, with P03, P04, and P06 flagged. To send the sample directly to the running server, use the tracked request below; this does not require a previous CLI run. Posting it is a separate analysis and uses credits in live mode:

```powershell
$body = Get-Content -LiteralPath 'frontend/src/sample.json' -Raw
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8013/reviews' -ContentType 'application/json' -Body $body
```

## Inspect the three specialist roles

The saved API response includes review_id, revision, lifecycle_status and packet. Inside packet are agent_runs, policy_review, risk_findings, aggregate model_calls and per-stage token metadata. Rule decisions and arithmetic remain authoritative Python outputs. Each live review now uses multiple calls, not just extraction.

## Start the React workspace

**Keep the backend running in Terminal A on port 8013.** Open Terminal B at this repository root, then run:

```powershell
cd frontend
npm ci
npm run dev
```

**Open [http://127.0.0.1:5173](http://127.0.0.1:5173).** A Python venv is not required in Terminal B. On later runs, skip npm ci unless dependencies changed. Node 25.4.0 was used locally; install a Node version supported by Vite.

1. Click **Load bakery sample** to populate the complete request.
2. Click **Build review packet** once; live analysis uses Nebius credits.
3. Inspect policy findings, calculations, exact source quotes and agent activity.
4. Enter a name/note to **Mark packet reviewed** or **Request changes**.
5. Submit the full corrected proposal when clarification is needed, then inspect its revision history.
6. Reopen records from **Saved reviews** or **Download JSON** for a local export.

**Windows certificate-chain error during npm ci:** in PowerShell run `$env:NODE_USE_SYSTEM_CA='1'`, then retry npm ci. Keep TLS verification enabled.

Model credentials remain in the backend's ignored .env. No frontend .env or new service account is needed.

**Frontend checks** (run from frontend/):

```powershell
npm run build
npm run format:check
npx playwright install chromium
npm test
```

Browser tests use isolated offline API data on ports 8014/5174 and spend no model credits. The local UI proxy is not deployment configuration; Vercel hosting and a deployed backend remain future work.

## Saved human review and resume

**Install updated dependencies and restart the API after pulling this checkpoint.**

POST /reviews still accepts document_id, submitted_on, and proposal_text. Its response now wraps the analysis inside **packet**, beside **review_id**, **revision**, **lifecycle_status**, history summaries and pending human action.

| Endpoint | Purpose |
| --- | --- |
| POST /reviews | Create, analyze and save a review, then pause for a human. |
| GET /reviews | List recent saved reviews without model calls. |
| GET /reviews/{review_id} | Reopen the saved state after a restart. |
| GET /reviews/{review_id}/history | Read complete accepted revision snapshots. |
| POST /reviews/{review_id}/actions | Clarify, request revision, or mark the packet reviewed. |
| POST /reviews/{review_id}/retry | Resume a failed processing stage from its checkpoint. |

Use the top-level review_id in URLs, not packet.run_id. Mark reviewed records a packet-review action, never a loan approval or denial.

SQLite files live in ignored **local_data/** and are not pushed to Git. The optional REVIEW_DATA_DIR setting changes that path. This is a local demo without verified reviewer identities or authentication. The React workspace uses these same saved-review endpoints.

## Connect Nebius

Use the model setup instructions above. Configuration defaults to nebius; missing or invalid settings produce an error instead of a parser fallback. Restart Uvicorn after changing .env. Model calls use API credits.

## Activate in other Windows shells

**Git Bash on Windows:**

```bash
source venv/Scripts/activate  #(Windows)
```

**PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

Use the activation syntax for your shell, then run the same `python -m ...` commands from the repository root.

## Developer checks

With venv activated, install the optional developer tools and check the code:

```powershell
python -m pip install -r backend/requirements-dev.txt
basedpyright
ruff check backend
ruff format --check backend
python -m pytest -q
```

## Troubleshooting

- **No module named uvicorn:** verify `python -c "import sys; print(sys.executable)"`, activate this repo's venv, then install backend/requirements-lock.txt using `python -m pip`.
- **uvicorn command not recognized:** use `python -m uvicorn ...` after activation, or the direct venv Python command above.
- **Cannot import backend:** run from the repository root. Do not change into backend/ for these commands.
- **Port 8013 already in use:** check /health; use the existing instance or stop its terminal before restarting. Alternatively choose another port and use that port in your browser.
- **Pydantic/native-extension import error after changing Python:** recreate the environment cleanly; do not reuse packages installed for another Python version.

If a request fails after submission, refresh saved reviews before creating another. A failed create has no idempotency key; human-action retries use an action ID to avoid duplicate actions.

## Recovery and practical limits

- Transient provider failures and invalid structured output have bounded retry/repair. Repeated failure saves ERROR_NEEDS_REVIEW and accepted earlier-stage work; the retry endpoint resumes the unfinished stage.
- Clarification supplies the whole corrected proposal and reruns analysis as a new revision. Reads and mark-reviewed actions do not call models.
- Local SQLite data is ignored by Git. Back it up separately if needed. An abruptly terminated in-flight operation may retain a 30-minute lease; a model call completed before its result was checkpointed can repeat during recovery.
- Actor names are self-reported. There is no authentication, shared-user deployment, streaming/background analysis, PDF/OCR intake or banking integration.
- Exact quote matching and numeric guards do not prove semantic faithfulness. Broad quality claims require the separate Week 4 evaluation.

## Repository layout

- backend/app/: FastAPI routes, specialist roles, models, tools, storage and LangGraph workflows.
- backend/tests/: offline unit and API/state-recovery integration tests.
- frontend/src/: React workspace, typed API client and synthetic input sample.
- frontend/tests/: Chromium tests against a real isolated offline API.
- data/proposals/: the synthetic Markdown proposal used by the CLI.
- .env.example: safe model/storage configuration template.

This submission retains the relevant application and main README history. Private development notes and AGENTS.md are excluded. Dependencies, local data and build/test output remain ignored. No model credentials or existing review database are supplied.

## Submit the complete request in Swagger

1. Keep the backend running and open [http://127.0.0.1:8013/docs](http://127.0.0.1:8013/docs).
2. Open frontend/src/sample.json in your editor and copy the entire JSON object.
3. Expand **POST /reviews**, click **Try it out**, replace the **Request body** with that object and click **Execute** once.
4. Confirm the actual **Server response** is 200. The documented 422 response shown elsewhere on Swagger is not a second response to the successful call.
5. Copy the top-level **review_id** for other endpoints. Do not use packet.run_id in those URLs.
6. Inspect packet.rules for P03/P04/P06 flags and lifecycle_status=AWAITING_REVIEW. Packet workflow status and saved human lifecycle status have different purposes.
7. Expand **GET /reviews/{review_id}**, enter that ID and execute to reopen the record. This read does not call the model.

The request must contain only document_id, submitted_on and proposal_text. Do not paste the returned packet back into POST /reviews; that produces an actual 422 validation failure before inference.

## Human review, corrections and retries

**In the React workspace:**

1. Open a saved review and inspect all policy findings and source evidence.
2. Enter your name and a review note, then choose **Mark packet reviewed** or **Request changes**.
3. A request for changes pauses for clarification. Read the reviewer request and edit the **Complete corrected proposal** field, supplying the entire source rather than only an answer sentence.
4. Enter the analyst name/note and click **Submit corrected proposal**. This reruns all three roles and creates a new revision, using credits in live mode.
5. Select an archived **Packet version** to inspect the old packet. Return to the current version to act; archived packets have no action form.
6. Click **Download JSON** to export the current saved record or selected archived version locally.

**API actions** use action_id, expected_revision, actor and note. The /actions endpoint also requires action=clarify, request_revision or mark_reviewed; clarify requires replacement_proposal_text containing the full corrected source. The /retry endpoint uses the common four fields without action, after a failed/interrupted processing stage. Use a new UUID for a new action, and repeat the identical ID/body when retrying an uncertain result. Reusing an ID with a different body is rejected.

**Recovery:**

- Missing/conflicting facts pause for clarification. A failed provider stage is a different state and uses **Retry failed stage**.
- A repeated human action sends the same payload safely. A stale expected_revision returns 409: reload and inspect the current record before making another action.
- **Reload record** discards unsent human-action form changes. Unsaved text and uncertain action IDs are held in browser memory; avoid reloading during submission.
- Reviewed records are terminal in this demo. Create a new review for another run.
- The sidebar shows the latest 100 saved records. Restarting the API preserves them in its local data directory.

## Verification and submission status

The submission extraction is based on learning-repo commit af78adbfe80ba072e3ddcbcdfdc1d3330a6ad922. Application files are retained byte-for-byte; this README has submission-specific setup/link cleanup. Filtered commits have new IDs while preserving the relevant code/README changes, authors and ordering. A submission-only .gitattributes rule keeps fresh checkouts at LF line endings for the formatter; application Git blobs remain unchanged.

The local build is separate from final course submission. A Google Doc and a live demo video of five minutes or less are still separate deliverables. GitHub publication/reviewer access is not configured by creating this local repo. Week 4 evaluations belong in a separate later project.


**Fresh-install verification:** Python 3.14.2 venv creation, pinned backend/developer installation and npm ci completed in this repository. All 41 backend tests, backend static/dependency checks, strict frontend build, formatting and four Chromium browser tests passed. The existing 13 third-party LangSmith deprecation warnings remain. Browser assertions use short readiness waits; an initial run under concurrent setup load timed out on two waits, and the complete suite passed when rerun on its own. These tests are offline and do not measure live semantic quality. No model key or prior local review database was copied here.
