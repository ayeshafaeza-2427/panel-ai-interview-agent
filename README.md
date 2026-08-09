# Panel — The Interview Agent

Built for the ABTalks Vibe Code Hackathon, Problem Statement #2.

## Problem

The AI Cohort is a 31-day enterprise AI engineering program (RAG, vector
databases, prompt engineering, agentic AI, MCP, deployment). The
hackathon asks for an AI Interview Agent that conducts a realistic,
multi-turn technical interview personalized to each candidate's actual
learning journey through the cohort — not a static quiz, and not a
generic chatbot.

## Solution

Panel reads a candidate's real mission history (what they passed,
failed, or skipped) and the real 31-day curriculum, builds a coverage
plan across at least 4 curriculum days the candidate actually
completed, and interviews them through a single stateful HTTP endpoint.
Each turn, an LLM decides — based on the transcript so far — whether to
go deeper on the current topic, move to a new one, or conclude, subject
to code-level guardrails that guarantee the mandatory minimums (≥8
questions, ≥4 curriculum days) regardless of what the model decides.
The interview ends with structured, evidence-based feedback grounded in
what the candidate actually said.

## Key Features

- **Personalized interviews** — the coverage plan is built from each
  candidate's own passed/failed/skipped missions; two different
  candidates get two different interviews.
- **Curriculum-aware questioning** — every question is grounded in the
  real objectives/tools/type of the curriculum day it targets, not
  invented content.
- **Adaptive follow-ups** — strong answers go deeper, incomplete
  answers get clarifying follow-ups, incorrect answers get probed, and
  the interviewer moves on rather than repeating a well-covered topic.
- **Context-aware conversation** — the full transcript is passed to the
  model on every turn so later questions can reference earlier answers.
- **Structured evaluation** — the final response contains a summary,
  strengths, gaps, and concrete next steps, all derived from the actual
  transcript, not generic advice.
- **Guardrailed, not just prompted** — the ≥8 questions / ≥4 days
  requirements are enforced in code as a safety net around the LLM's
  judgement, so the interview can't accidentally under-deliver.

## Architecture

```
backend/
  app/
    schemas.py            Pydantic models — the exact spec contract
    curriculum_loader.py   Reads curriculum.json (source of truth)
    candidate_loader.py    Reads candidates.json (source of truth)
    interview_planner.py   Picks which curriculum days to interview on,
                            personalized per candidate
    interview_state.py     In-memory session state (no persistence —
                            out of scope per the problem statement)
    ai_provider.py          The ONLY module that talks to an AI API.
                             Provider-agnostic (OpenAI-compatible wire
                             format); JSON-mode calls, validation, one
                             retry on malformed output
    question_engine.py     The adaptive interview loop: assess the last
                            answer, decide follow-up/next-topic/conclude,
                            generate the next question, enforce minimums
    evaluator.py            Generates the final structured feedback
    main.py                 FastAPI app; implements POST /api/interview
                             exactly per the Technical Specification
  data/                     Copies of the supplied curriculum/candidate
                             JSON (source of truth, never modified)
  tests/test_api.py         API tests incl. mandatory-requirement checks

frontend/
  src/
    lib/api.js               Backend API client
    lib/InterviewContext.jsx React context holding live interview state
    pages/Dashboard.jsx       Candidate list + product intro
    pages/CandidateOverview.jsx  Profile, completed/skipped topics, plan
    pages/Interview.jsx       The live interview screen
    pages/Report.jsx          Final structured feedback report
```

The only requirement from the Technical Specification is a single
endpoint, `POST /api/interview`. The backend also exposes three small
read-only support endpoints (`/api/candidates`, `/api/curriculum`,
`/api/plan`) purely so the frontend can render the dashboard and a
coverage-plan preview without duplicating the JSON files client-side —
these are additive and not part of the required contract.

No vector database is used. The curriculum is 31 short JSON records; an
in-memory dict lookup by day number is simpler and just as reliable as
a vector store for a dataset this size, and avoids adding a dependency
that wouldn't actually improve retrieval quality here.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Pydantic, the official `openai`
  Python SDK (used generically — see AI Provider below), pytest
- **Frontend:** React 19, Vite, React Router — plain CSS (no UI
  framework), to keep the design fully custom and dependencies minimal
- **AI provider:** Configurable, defaults to **Google Gemini** via its
  official OpenAI-compatible API (free tier, no credit card required)
  — see [AI Provider](#ai-provider) below

## AI Provider

The app talks to AI models through one abstraction layer,
`backend/app/ai_provider.py`, and nowhere else. Nothing in
`question_engine.py`, `evaluator.py`, or any other module imports a
vendor SDK directly — they all call the single `generate_json()`
function this module exposes:

```
AI Provider (ai_provider.py)
       │
       ├── Question Generation   (question_engine.py)
       ├── Answer Evaluation     (question_engine.py, per-turn assessment)
       ├── Follow-up Generation  (question_engine.py)
       └── Final Evaluation      (evaluator.py)
```

**Why Gemini, by default:** Google publishes an official
OpenAI-compatible endpoint for the Gemini API
(https://ai.google.dev/gemini-api/docs/openai) — same
chat-completions wire format as OpenAI, Groq, Together AI, Fireworks,
OpenRouter, and local runtimes like Ollama, so the same client code
works against any of them, no per-vendor branches needed. Gemini
specifically has a genuinely free API tier (create a key at
[Google AI Studio](https://aistudio.google.com/apikey), no credit card
required), and the model verified against Google's current official
docs, `gemini-3.6-flash`, is capable of structured JSON generation —
which made it the right fit for "works with a normal, free API key I
already have" without changing anything else about the app.

**Switching providers** is three environment variables, not a code
change:

| Variable | Purpose |
|---|---|
| `AI_API_KEY` | Generic API key override — works for any provider. |
| `GEMINI_API_KEY` | Gemini-specific key variable (used automatically as a fallback when `AI_PROVIDER=gemini` and `AI_API_KEY` isn't set — this is the variable name Google's own docs use). |
| `AI_PROVIDER` | Convenience preset: `gemini` (default) or `openai`. Fills in `AI_BASE_URL`/`AI_MODEL` defaults. |
| `AI_BASE_URL` / `AI_MODEL` | Set these directly to use any other OpenAI-compatible endpoint (Groq, Together AI, Fireworks, OpenRouter, a local Ollama/vLLM server, OpenAI itself) — they always override the preset. |

Get a free Gemini key at **https://aistudio.google.com/apikey** (sign
in with a Google account, no payment method required, click "Create
API key").

## Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GEMINI_API_KEY to a free key from https://aistudio.google.com/apikey
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env             # sets VITE_API_URL, defaults to localhost:8000
```

## Environment Variables

**backend/.env**

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | yes (with default provider) | — | Gemini API key from Google AI Studio. Never hardcoded, never committed. |
| `AI_API_KEY` | no | — | Generic override; takes priority over `GEMINI_API_KEY` if both are set. Required if using a provider outside the `gemini`/`openai` presets. |
| `AI_PROVIDER` | no | `gemini` | Preset: `gemini` or `openai`. Fills in base URL/model unless overridden below. |
| `AI_BASE_URL` | no | (from preset) | Any OpenAI-compatible endpoint. Overrides the preset. |
| `AI_MODEL` | no | (from preset) | Model name for the configured provider. Overrides the preset. |
| `AI_MAX_TOKENS` | no | `1024` | Max tokens per AI call. |
| `AI_TEMPERATURE` | no | `0.7` | Sampling temperature. |
| `CORS_ALLOWED_ORIGINS` | no | `http://localhost:5173` | Comma-separated list of allowed frontend origins. |
| `LOG_LEVEL` | no | `INFO` | Backend log verbosity. |

**frontend/.env**

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `VITE_API_URL` | no | `http://localhost:8000` | Base URL of the backend API. |

## Running Locally

```bash
# Terminal 1
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm run dev
```

Then open the URL Vite prints (default `http://localhost:5173`).

## API

**`POST /api/interview`** — the single endpoint required by the
Technical Specification. No authentication.

**Start a session:**
```json
POST /api/interview
{ "sessionId": "abc-123", "candidate": { "member": {...}, "missions": [...], "signals": {...} } }
```
```json
{ "reply": "Welcome. Let's begin your interview.", "done": false }
```

**Continue a session:**
```json
POST /api/interview
{ "sessionId": "abc-123", "message": "RAG retrieves relevant context before generation." }
```
```json
{ "reply": "How would that retrieved context...", "done": false }
```

**Final turn:**
```json
{
  "reply": "Interview completed.",
  "done": true,
  "feedback": {
    "summary": "...",
    "strengths": ["..."],
    "gaps": ["..."],
    "next": ["..."]
  }
}
```

Responses also include an optional `meta` object (question number,
curriculum day/title, follow-up flag, covered days) used by the
frontend's progress UI. It's additive — not part of the required
contract — and safe to ignore.

**Error responses** use `{"error": "<code>", "detail": "<message>"}`
with an appropriate status code: `422` for malformed/missing fields,
`404` for an unknown session, `409` for a duplicate/already-completed
session, `503` (`ai_provider_unavailable`) if the configured AI
provider is unreachable or misconfigured, `502`
(`ai_provider_malformed_response`) if the model returns unparseable
output after a retry, `500` for anything unexpected (with no stack
trace exposed to the client).

## AI Usage

This project was built with AI-assisted development throughout — see
[`PROMPTS.md`](./PROMPTS.md) for the actual, unedited log of the
prompts used and what was built/tested/fixed at each stage.

## Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

11 tests cover: the spec's exact request/response shapes, the
mandatory ≥8-questions/≥4-days requirement, adaptive follow-up
generation, session lifecycle errors (duplicate start, unknown
session, already-complete session, empty message, malformed JSON), and
that different candidates get different, personalized interview plans.
2 additional tests cover the AI provider layer: that the app returns a
graceful `503 ai_provider_unavailable` (not a crash) when no key is
configured, and that `AI_PROVIDER`/`AI_BASE_URL`/`AI_MODEL` resolve
correctly from the environment — including that the default preset
(no `AI_PROVIDER` set) resolves to Gemini's official OpenAI-compatible
endpoint and the verified `gemini-3.6-flash` model. A third new test
confirms `GEMINI_API_KEY` alone (without the generic `AI_API_KEY`) is
enough to configure the client, since that's the variable name the
user actually has.

Since this environment has no live `GEMINI_API_KEY` (confirmed via
`env | grep`), the AI call itself is replaced with a deterministic
test double for the interview-flow tests so the real orchestration
logic (planner, guardrails, state machine, evaluator) can be exercised
end-to-end offline — this fallback exists **only** inside
`tests/test_api.py` (via `monkeypatch`) and is never reachable in
production code; `app/ai_provider.py` has no mock/fallback path of its
own. **What remains to be tested with a real key:** an actual live
Gemini call — question quality/relevance from the live model, and
end-to-end latency under real network conditions. The live server was
verified to start, serve `/health`, and return a correct, graceful
`503` (mentioning `GEMINI_API_KEY` specifically and linking to
Google AI Studio) without crashing when no key is present.

`npm run build` in `frontend/` was run and completes successfully.
The frontend was not changed by the AI-provider refactor — it only
talks to `POST /api/interview`, which kept its exact required shape.

## Deployment

Not yet deployed — see the audit below for what's outstanding.

**Backend** (FastAPI) is a standard ASGI app and deploys as-is to
Render, Railway, Fly.io, or similar: set `GEMINI_API_KEY` and
`CORS_ALLOWED_ORIGINS` (to the deployed frontend's URL) as environment
variables, and run `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

**Frontend** (static Vite build) deploys to Vercel or Netlify: set
`VITE_API_URL` to the deployed backend's URL as a build-time
environment variable, build command `npm run build`, output directory
`dist`. `frontend/vercel.json` includes the SPA rewrite rule needed for
client-side routing (React Router) on Vercel.

Config files included for a quick deploy:
- `backend/Procfile` — start command for Render/Railway/Heroku-style platforms
- `backend/render.yaml` — Render blueprint (set `GEMINI_API_KEY` and
  `CORS_ALLOWED_ORIGINS` in the Render dashboard; they're marked
  `sync: false` so they're never committed)
- `frontend/vercel.json` — SPA rewrite rule for Vercel

**Not yet verified:** an actual deploy to a live URL, and an actual
live Gemini API call (no key available in this build environment). The
configs above are written correctly for these platforms' documented
conventions but have not been exercised against a real account.
