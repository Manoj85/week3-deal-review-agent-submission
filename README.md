# Week 3 Small Business Loan Review Assistant

Project 3B, code track. The current backend runs three Nebius-backed specialist roles: extraction, policy review with checked Python tools, and cited risk summary. Saved human review, clarification/resume, and revision history are implemented with local SQLite. The React + TypeScript + Vite workspace now supports the complete local review flow.

## Local setup on Windows PowerShell

Use a terminal opened at this repository root, not inside backend/. The environment folder is **venv**.

### 1 Open the project

```powershell
cd 'C:\Users\pmami\Documents\Sairam\GithubWorkspace\mai-certification-gen-academy-oct-cohort\week3-deal-review-agent'
python --version
```

Python 3.14.2 is used by the repaired local environment. The earlier checkpoint was also tested with Python 3.12. Do not run venv creation over an existing environment when switching Python versions; use a fresh environment and reinstall dependencies.

### 2 Create the environment once

Skip this step if this project's venv already exists. It has already been created on this machine.

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

### 5 Start the backend

Stay at the repository root with venv activated:

```powershell
python -m uvicorn backend.app.main:app --reload --reload-dir backend --host 127.0.0.1 --port 8013
```

Keep that terminal running. Open [API documentation](http://127.0.0.1:8013/docs) or [health check](http://127.0.0.1:8013/health). Stop the server with Ctrl+C. This opens the backend's API documentation. Start the React workspace in a second terminal using the steps below.

`backend.app.main` means `backend/app/main.py`; `:app` selects the FastAPI object named `app`. `--reload` restarts the server when source files change; `--reload-dir backend` watches our backend code rather than installed packages in venv. Your budgeting repo uses `app.main:app` because its app/ directory is directly under its repo root. Here app/ is inside backend/, so the prefix is `backend.app.main:app` when running from the root.

## Start again on another day

Once dependencies are installed, you only need:

```powershell
cd 'C:\Users\pmami\Documents\Sairam\GithubWorkspace\mai-certification-gen-academy-oct-cohort\week3-deal-review-agent'
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

The CLI sample is a one-shot preview, not a saved lifecycle record. It saves its full request/review under work/checkpoint-01/. Expected route: EXCEPTIONS_FOR_REVIEW, with P03, P04, and P06 flagged. To send the sample to the running server:

```powershell
$body = Get-Content -LiteralPath 'work/checkpoint-01/sample-request.json' -Raw
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8013/reviews' -ContentType 'application/json' -Body $body
```

## Inspect the three specialist roles

The saved API response includes review_id, revision, lifecycle_status and packet. Inside packet are agent_runs, policy_review, risk_findings, aggregate model_calls and per-stage token metadata. Rule decisions and arithmetic remain authoritative Python outputs. Each live review now uses multiple calls, not just extraction. See [the specialist walkthrough](docs/lessons/06-specialist-workflow.md).

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

See [the complete UI setup and walkthrough](docs/lessons/08-react-workspace.md), including Git Bash commands, failure recovery and browser tests. Model credentials remain in the backend's ignored .env. No frontend .env or new service account is needed.

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

Follow [the complete Swagger walkthrough and ready-to-copy JSON examples](docs/lessons/07-saved-human-review.md). Use the top-level review_id in URLs, not packet.run_id. Mark reviewed records a packet-review action, never a loan approval or denial.

SQLite files live in ignored **local_data/** and are not pushed to Git. The optional REVIEW_DATA_DIR setting changes that path. This is a local demo without verified reviewer identities or authentication. The React workspace uses these same saved-review endpoints.

## Connect Nebius

Follow [the step-by-step Nebius setup and lesson](docs/services/nebius-setup.md). Configuration defaults to nebius; missing or invalid settings produce an error instead of a parser fallback. Restart Uvicorn after changing .env. Model calls use API credits.

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

See [detailed local setup](docs/services/backend-local-setup.md) for environment recovery and activation help.

## Project and learning documentation

- [Documentation index](docs/README.md)
- [Scope and fictional policy](docs/planning/project-scope.md)
- [Backend inputs and outputs](docs/lessons/03-backend-input-output.md)
- [Project and test structure](docs/repository/project-structure.md)
- [Discussion from the beginning](docs/notes/conversation-guide.md)

Frontend: React + TypeScript + Vite. Backend: FastAPI + LangGraph. Both share this repository. Week 4 evaluations get a separate repository later. Nebius key/model settings are required for live mode; tests remain offline.

Private repository: https://github.com/Manoj85/week3-deal-review-agent.
