# Week 3 Small Business Loan Review Assistant

Project 3B, code track. First offline backend checkpoint implemented; live AI agents and UI remain planned.

Target user: a loan operations analyst preparing the daily initial-review queue. Intended application: three specialized agents extract terms, check fictional policy, and draft an evidence-backed review packet.

Current slice: FastAPI request validation, a real LangGraph with sample-format extraction, Decimal policy checks, conditional routing, deterministic summary, and source evidence. Fifteen tests pass; type, lint, and formatting checks are clean. No provider/model calls, PDF ingestion, durable human review, or React implementation yet.

Planned UI: React + TypeScript + Vite in frontend/. Backend: backend/. Both share this repository. Week 4 evaluation gets a separate repository later.

Start with [the documentation index](docs/README.md), [backend contract lesson](docs/lessons/03-backend-input-output.md), and [local run instructions](docs/services/backend-local-setup.md). See [the scope](docs/planning/project-scope.md) for the full intended design, and [discussion history](docs/notes/conversation-guide.md) for decisions. Collaboration rules are in AGENTS.md.

Private remote: https://github.com/Manoj85/week3-deal-review-agent.

## Run locally

Open PowerShell in this repository root. The current local .venv is already installed. Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8013
```

Open [interactive API docs](http://127.0.0.1:8013/docs) or [health](http://127.0.0.1:8013/health). Stop with Ctrl+C. If port 8013 is already occupied by our running backend, use that server or stop it before starting another. The React UI is not implemented yet.

For a fresh clone, first install Python 3.12 and create the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
```

In a second terminal, execute the sample and tests:

```powershell
.\.venv\Scripts\python.exe -m backend.run_sample
.\.venv\Scripts\python.exe -m pytest -q
```

The sample creates work/checkpoint-01/sample-request.json and sample-review.json. To send it to the running API:

```powershell
$body = Get-Content -LiteralPath 'work/checkpoint-01/sample-request.json' -Raw
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8013/reviews' -ContentType 'application/json' -Body $body
```

Expected result: EXCEPTIONS_FOR_REVIEW with P03, P04, P06 flagged. No model credentials are needed for this offline slice.

## Developer checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\basedpyright.exe
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
.\.venv\Scripts\python.exe -m pytest -q
```

The existing sandbox .venv was bootstrapped without its own pip. If its pip command fails, use the bundled-pip fallback in [detailed setup](docs/services/backend-local-setup.md).

Open this repository as your editor workspace and select .venv/Scripts/python.exe if Python imports remain red. An already selected interpreter may need manual reselection.

See [backend/test structure](docs/repository/project-structure.md) for the current package layout and growth plan, and [diagnostics lesson](docs/lessons/04-code-diagnostics.md) for the issues found and fixed.
