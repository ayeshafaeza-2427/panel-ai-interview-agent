# PROMPTS.md

This file documents the actual prompts used to build The Interview Agent
("Panel") during the ABTalks Vibe Code Hackathon, in the order they were
used. It exists to satisfy the hackathon's authenticity requirement — no
entries here are fabricated or backdated.

---

## Stage 1 — Problem framing & Phase 1 inspection

**Prompt (paraphrased, first message):** A long system-style brief
describing the hackathon problem statement (The Interview Agent), the
mandatory requirements (≥8 questions, ≥4 curriculum days, adaptive
follow-ups, structured feedback, exact API contract), the product
vision, and an instruction to inspect the repository/resources and
report findings — but explicitly to STOP after Phase 1 and wait for
approval before writing code.

**What happened:** No project files existed yet in the workspace at
that point. Claude searched the filesystem, found nothing, and reported
back that `curriculum.json`, `candidates.json`, and the Technical
Specification were all missing, asking the user to supply them rather
than inventing their contents.

## Stage 2 — Resources supplied, Phase 1 completed

**Prompt:** The user uploaded `candidates.json`, `curriculum.json`, and
`technical-spec.md`.

**What happened:** Claude read all three files in full (including the
previously-truncated middle section of `curriculum.json`, days 13–16),
confirmed there was no existing project structure, and produced a Phase
1 report covering: the real schema of each resource, the exact
`/api/interview` request/response contract from the spec, flagged
ambiguities (e.g. how the frontend picks a candidate — not specified,
left to our design), and a recommended architecture (FastAPI backend,
in-memory session state, no vector DB since the curriculum is small,
Anthropic API via env var, React/Vite frontend). Stopped again to wait
for approval, per the brief's explicit instruction.

## Stage 3 — Build authorization

**Prompt (paraphrased):** A second system-style brief for the same
hackathon problem, this time explicitly authorizing full build
permissions ("You have permission to inspect the entire repository,
create and modify files, install required dependencies, run commands,
run tests, fix errors, and continue iterating") and instructing Claude
not to stop after planning but to build, run, test, fix, and report at
the end.

**What happened:** Claude began full implementation:

- Verified current Anthropic API model naming via web search
  (`claude-sonnet-5`) before hardcoding a model string, since training
  data on model names is frequently stale.
- Built the backend module by module: `schemas.py` (spec-exact request/
  response models), `curriculum_loader.py`, `candidate_loader.py`,
  `interview_planner.py` (personalizes topic coverage per candidate's
  actual passed/failed/skipped missions), `interview_state.py`
  (in-memory session store), `llm_client.py` (Anthropic SDK wrapper with
  JSON validation + retry), `question_engine.py` (the adaptive
  follow-up/next-topic/conclude decision logic with code-level
  guardrails enforcing the ≥8/≥4 minimums even if the model ignores
  them), `evaluator.py` (final structured feedback), and `main.py`
  (the FastAPI app implementing `/api/interview` exactly).
- Installed dependencies into a venv, ran `python -c` sanity checks
  against the real curriculum/candidate JSON to confirm the planner
  actually personalizes per candidate (verified Emily Chen vs. Wendy
  Foster get different interview plans).
- Wrote `tests/test_api.py` with a deterministic fake LLM (since no
  live `ANTHROPIC_API_KEY` exists in the build sandbox) to exercise the
  real orchestration logic — planner, state machine, guardrails,
  evaluator — end to end without a network call. Ran the suite, found
  one failure (the spec-shape test expected exactly `{reply, done}` but
  FastAPI's `response_model` was serializing the unset `feedback: null`
  field too), fixed it with `response_model_exclude_none=True`, reran
  to green.
- Booted the actual `uvicorn` server and hit it with `curl` to verify
  real HTTP behavior beyond the test client: confirmed a graceful `503
  llm_unavailable` (not a crash) when `ANTHROPIC_API_KEY` is unset,
  and correct `422`/`404`/`400` responses for missing fields, unknown
  sessions, and malformed JSON, with the server staying alive
  throughout.

## Stage 4 — Continuing after a tool-call limit interruption

**Prompt:** "Continue"

**What happened:** The previous turn had been cut off mid-build with
the backend complete and tested, but the frontend only partially built
(Dashboard done; `CandidateOverview`/`Interview`/`Report` referenced
undefined context fields, and one file had a stray syntax error from an
interrupted edit). Claude:

- Discovered the required UI element "curriculum topic/day being
  assessed" per question couldn't be derived from the spec's minimal
  `{reply, done}` response, so extended the response with an **additive,
  optional** `meta` object (day, day title, question number, follow-up
  flag, covered days, progress vs. minimums) — documented in the schema
  docstring as not part of the required contract, verified this doesn't
  break the spec-shape test (updated to check the required fields are a
  *subset* of the response, not an exact match).
- Found and fixed a duplicated/corrupted `TurnMeta`/`InterviewResponse`
  definition in `schemas.py` left over from an interrupted edit,
  rewriting the file cleanly.
- Reconciled `question_engine.py` and `main.py` so metadata is built in
  one place (the question engine, which has the actual `QAPair` data)
  instead of being redundantly reconstructed in the API layer.
- Fixed a leftover bug in `Interview.jsx` (`questionTurns` referenced
  but never defined).
- Rewrote `CandidateOverview.jsx` cleanly after an earlier corrupted
  draft (dead code, an unused `api.request?.()` no-op) and rewrote its
  stylesheet to match the component's actual class names, since the
  existing CSS file used a completely different naming scheme
  (`overview-*`/`mission-*` vs. the JSX's `ov-*`/`topic-*`/`plan-*`).
- Ran `npm run build` — succeeded on the first attempt after these
  fixes.
- Booted the backend and frontend dev servers together in the same
  shell (background processes were being killed between separate
  `bash_tool` calls, so this required starting both and running the
  verification `curl` calls within a single invocation), and confirmed:
  health check, CORS preflight behavior (correctly rejects an
  unlisted origin), `/api/candidates` returning all 20 real candidates,
  the Vite dev server serving HTTP 200, and `/api/plan` returning a
  real, correctly-computed coverage plan for a sample candidate.

*(This file is updated incrementally as the build continues — later
stages, including the final compliance audit, README, and deployment
prep, will be appended here rather than backfilled.)*

## Stage 5 — Removing the Anthropic hard dependency

**Prompt (paraphrased):** The user does not have an Anthropic API key
and does not want to purchase one. Instructed Claude not to stop the
project, to refactor the AI layer into a provider abstraction (AI
Provider → Question Generation / Answer Evaluation / Follow-up
Generation / Final Evaluation) so the rest of the app doesn't depend on
Anthropic directly, to get it working with an alternative provider
that has a free/accessible API key, and to keep all existing mandatory
functionality, the exact API contract, and personalization/adaptivity
behavior unchanged. Also asked for the Anthropic dependency to be
removed if no longer needed, no hardcoded keys, no fake AI responses
used to pass tests, all tests re-run, and the actual AI integration
tested if a key is available.

**What happened:** Claude first inspected the existing integration
(`grep`) and found it was already isolated to a single module
(`llm_client.py`, used only by `question_engine.py` and
`evaluator.py` — never imported elsewhere), which made the refactor a
contained change:

- Replaced `llm_client.py` with `app/ai_provider.py` — a provider
  abstraction that speaks the OpenAI-compatible chat-completions wire
  format (via the `openai` Python SDK's configurable `base_url`)
  rather than writing a bespoke client per vendor. That one format is
  implemented by Groq, OpenAI, Together AI, Fireworks, OpenRouter, and
  local runtimes (Ollama/vLLM), so "the provider" reduces to three env
  vars (`AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`) with `AI_PROVIDER` as
  a convenience preset.
- Chose **Groq** as the default preset specifically because it has a
  genuinely free API tier with no credit card required to sign up —
  directly satisfying "do not require me to purchase an API key" —
  while keeping the exact same `generate_json(system_prompt,
  user_prompt, validator, max_retries)` function signature so
  `question_engine.py` and `evaluator.py` needed only an import-path
  change, not a logic change.
- Added a defensive fallback in `_call_model`: if a provider rejects
  the `response_format: json_object` parameter (some OpenAI-compatible
  providers/models don't support it), it retries once without that
  parameter rather than failing outright — the existing JSON-parse/
  validate/retry loop still catches malformed output either way.
- Updated `main.py`'s exception handling to catch
  `AIProviderUnavailableError`/`AIProviderMalformedResponseError`
  instead of the old Anthropic-specific exception names, keeping the
  same HTTP status codes (503/502) and response shape — this changes
  only the internal `error` string in the JSON body (e.g.
  `ai_provider_unavailable` instead of `llm_unavailable`), which is
  not part of the required Technical Specification contract.
- Removed `anthropic` from `requirements.txt` (confirmed via `pip show
  anthropic` after a clean reinstall that it's genuinely not
  installed) and added `openai` in its place.
- Rewrote `backend/.env.example` and `README.md` (Tech Stack, a new
  "AI Provider" section, Setup, Environment Variables, API error
  codes, Testing, Deployment) to reflect `AI_API_KEY`/`AI_PROVIDER`/
  `AI_BASE_URL`/`AI_MODEL` instead of the old Anthropic-specific
  variables, and updated `backend/render.yaml` the same way.
- Re-ran the full test suite after a clean `pip install`: **13/13
  pass** (11 existing + 2 new provider tests — one confirming a
  missing key produces a graceful `503`, not a crash, and one
  confirming `AI_PROVIDER`/`AI_BASE_URL`/`AI_MODEL` are actually read
  from the environment via `importlib.reload`). Ran `pyflakes` on the
  backend — no issues. The test suite's deterministic AI double lives
  only in `tests/test_api.py` via `monkeypatch.setattr(ai_provider,
  "generate_json", ...)` — `app/ai_provider.py` itself has no
  fallback/mock path, so nothing fake ships in the production code
  path.
- Booted the live server and confirmed with `curl`, in a single shell
  session (background processes were being lost between separate tool
  invocations, so start+test had to happen together): `/health`
  returns 200, and starting an interview with no `AI_API_KEY` set
  returns a graceful `503 ai_provider_unavailable` with an actionable
  message pointing at `console.groq.com`, and the server stays healthy
  afterward.
- **Not tested:** an actual live call to Groq (or any provider) — no
  `AI_API_KEY` was present in this environment (`env | grep` came back
  empty), and the user confirmed they don't have one. Real question
  quality/relevance from a live model remains unverified until the
  user adds a free Groq key.

## Stage 6 — Correction: Groq → Gemini (the user's actual key)

**Prompt (paraphrased):** The user corrected Stage 5: they do not have
a Groq key, but do have a Gemini API key from Google AI Studio.
Instructed Claude to make Gemini the default production provider,
keep the existing `openai`-SDK-based abstraction (since Gemini
officially supports the OpenAI-compatible API), use
`AI_PROVIDER=gemini`, base URL
`https://generativelanguage.googleapis.com/v1beta/openai/`, env var
`GEMINI_API_KEY`, and a currently-supported Gemini model verified
against Google's official docs rather than invented from memory.
Explicitly required: remove Groq as the default and remove all
Groq-specific production config, keep the generic abstraction and all
existing interview/API-contract behavior, keep all 13 tests (updating
as needed), no hardcoded key, key stays server-side only, and to run
the full verification suite (tests, frontend build, lint, server
startup, missing-key behavior, provider config, and a real Gemini call
if a key happens to be available) before repackaging.

**What happened:**

- **Verified the model, not guessed it.** Web-searched, then
  `web_fetch`'d the live page at
  `https://ai.google.dev/gemini-api/docs/openai` directly (page
  timestamp: last updated 2026-07-21 UTC). Every single code example
  on that page — chat completions, streaming, function calling, image
  understanding, structured output, batch API, list/retrieve models —
  uses `model="gemini-3.6-flash"`. That's the model this build now
  uses; it was not pulled from training-data memory, which could have
  been stale by the time of this conversation.
- Rewrote `app/ai_provider.py`: replaced the `groq` preset with a
  `gemini` preset (`base_url`, `model`, and a new `key_env` field per
  preset). Added `_resolve_api_key()`: the generic `AI_API_KEY` wins if
  set, otherwise it falls back to the active preset's `key_env`
  (`GEMINI_API_KEY` for the `gemini` preset, `OPENAI_API_KEY` for the
  `openai` preset) — this satisfies "use `GEMINI_API_KEY`" and "keep
  the generic abstraction" simultaneously, since neither requirement
  had to be dropped for the other. Changed `DEFAULT_PROVIDER` fallback
  from `"groq"` to `"gemini"`. Updated the missing-key error message to
  name `GEMINI_API_KEY` specifically and point at
  `aistudio.google.com/apikey`.
- Left `question_engine.py`, `evaluator.py`, `main.py`, and the entire
  frontend **untouched** — the only thing that changed is which preset
  `ai_provider.py` resolves to and where it looks for a key, which was
  exactly the point of building the abstraction in Stage 5.
- Updated `tests/test_api.py`: added an explicit assertion in
  `test_ai_provider_is_configurable_via_env` that the *default* preset
  (no `AI_PROVIDER` set) resolves to Gemini's base URL and
  `gemini-3.6-flash`; changed the "restore default" line at the end
  from `groq` to `gemini`; added a new test,
  `test_gemini_api_key_env_var_used_as_fallback`, that sets only
  `GEMINI_API_KEY` (no `AI_API_KEY`) and confirms `_resolve_api_key()`
  and `_get_client()` both work correctly from that alone. Removed an
  unused `import json` left over in the test file (caught by
  `pyflakes`). Result: **14/14 tests pass** (13 original/renamed + 1
  new) — one more than the 13 the user asked to keep, since the new
  Gemini-key-fallback behavior needed its own coverage.
- Removed every Groq-specific value from production config: `.env.example`
  (rewrote the AI Provider block — `GEMINI_API_KEY` as the primary var,
  `AI_PROVIDER=gemini`, commented `AI_BASE_URL`/`AI_MODEL` showing the
  Gemini values as the documented default rather than requiring them),
  `render.yaml` (`GEMINI_API_KEY` instead of the old `AI_API_KEY`/`groq`
  entries), and `README.md` (Tech Stack line, the "AI Provider" section
  rewritten with the verified model and the "why Gemini" reasoning,
  Setup, Environment Variables table, Testing section, Deployment
  section). Confirmed via `grep -in groq README.md` that the only two
  remaining mentions are in the "you can also point this at Groq/Together/
  etc." interoperability sentences — accurate, not defaults.
- Ran `pip show anthropic` again — still not installed (no regression
  from Stage 5's removal).
- Ran the full verification pass: `pytest` (14/14 pass), `pyflakes`
  on `app/` and `tests/` (clean), `npm run build` in `frontend/`
  (succeeds, output unchanged — confirming the frontend truly wasn't
  touched), `npx oxlint` (0 errors, the same pre-existing harmless
  Fast-Refresh convention warning as before). Booted the live server
  and hit it with `curl` in a single shell session: `/health` → 200;
  starting an interview with no key set → graceful `503
  ai_provider_unavailable` whose message now says "Set GEMINI_API_KEY
  ... get a free Gemini API key at
  https://aistudio.google.com/apikey"; `/health` again → 200,
  confirming the server survived the error.
- **Not tested:** an actual live Gemini API call. `env | grep -iE
  "GEMINI|AI_API_KEY|AI_PROVIDER"` came back empty in this build
  environment — no key is available here, so real question
  quality/relevance and latency from `gemini-3.6-flash` remain
  unverified until the user adds their own `GEMINI_API_KEY` locally
  and runs one real interview.
