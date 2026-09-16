# KendraPulse

Stress tracing for joint liability microfinance groups. When a borrower becomes stressed,
KendraPulse labels the cause as INDEX, TRANSMITTED or INDEPENDENT, finds the smallest
supportive intervention that stops the spread, and shows the counterfactual side by side.

The build contract lives in [CLAUDE.md](CLAUDE.md).

## Setup

```
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m pytest
```

```
cd frontend
npm install
npm run dev
```

Full setup notes, the data assumptions and every parameter with its source arrive in Phase 8.
