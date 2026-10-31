# Week 3 Small Business Loan Review Assistant

Project 3B, code track. First offline backend checkpoint implemented; live AI agents and UI remain planned.

Target user: a loan operations analyst preparing the daily initial-review queue. Intended application: three specialized agents extract terms, check fictional policy, and draft an evidence-backed review packet.

Current slice: FastAPI request validation, a real LangGraph with sample-format extraction, Decimal policy checks, conditional routing, deterministic summary, and source evidence. Twelve tests pass. No provider/model calls, PDF ingestion, durable human review, or React implementation yet.

Planned UI: React + TypeScript + Vite in frontend/. Backend: backend/. Both share this repository. Week 4 evaluation gets a separate repository later.

Start with [the documentation index](docs/README.md), [backend contract lesson](docs/lessons/03-backend-input-output.md), and [local run instructions](docs/services/backend-local-setup.md). See [the scope](docs/planning/project-scope.md) for the full intended design, and [discussion history](docs/notes/conversation-guide.md) for decisions. Collaboration rules are in AGENTS.md.

Private remote: https://github.com/Manoj85/week3-deal-review-agent.
