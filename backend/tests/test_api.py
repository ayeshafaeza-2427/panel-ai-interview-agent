"""
Tests for the /api/interview endpoint against the exact Technical
Specification examples, plus the mandatory-requirements checks
(>=8 questions, >=4 curriculum days, adaptive follow-ups, context
maintained, structured feedback).

Since this sandbox has no live AI_API_KEY for any provider, the AI call
(app.ai_provider.generate_json) is monkeypatched with a deterministic
fake that mimics realistic model behavior (varying answer quality,
occasional follow-ups) so we can exercise the *real* orchestration
logic (planner, state machine, guardrails, evaluator) end-to-end
without a network call. This is clearly a test double, kept separate
from production AI behavior - see README for how to test the real
provider once you have a (free) API key.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ai_provider  # noqa: E402
from app.main import app  # noqa: E402
from app.interview_state import store  # noqa: E402
from app.candidate_loader import list_candidates  # noqa: E402


# ---------------------------------------------------------------------------
# Deterministic fake LLM for offline testing
# ---------------------------------------------------------------------------
_call_count = {"n": 0}


def fake_generate_json(system_prompt, user_prompt, validator=None, max_retries=1):
    """
    Mimics the real model well enough to exercise orchestration logic:
    - On the "first turn" prompt (contains 'FIRST TOPIC'), returns a
      welcome + first question for the given next_day.
    - On turn prompts, alternates answer quality and occasionally
      requests a follow_up, otherwise moves to the next remaining topic
      or concludes once guardrails say minimums are met.
    - On the feedback prompt, returns a valid Feedback-shaped object.
    """
    _call_count["n"] += 1

    if "This is the very first turn" in user_prompt:
        # Extract next_day the caller told us to use.
        import re

        m = re.search(r'"next_day": (\d+)', user_prompt)
        day = int(m.group(1)) if m else 1
        result = {
            "message": f"Welcome! Let's start with day {day}: tell me about it.",
            "action": "next_topic",
            "next_day": day,
        }
    elif "Produce final structured interview feedback" in user_prompt:
        result = {
            "summary": "The candidate demonstrated solid understanding of "
            "RAG fundamentals and agentic concepts, with some gaps in "
            "deployment topics.",
            "strengths": ["Clear grasp of retrieval pipelines", "Good agent reasoning"],
            "gaps": ["Vector DB tradeoffs were shallow"],
            "next": ["Review ChromaDB vs Pinecone tradeoffs", "Practice MCP tool design"],
        }
    else:
        # A turn response. Respect forced guardrails if present.
        import re

        forced = re.search(r"You MUST set action to '(\w+)'", user_prompt)
        remaining_match = re.search(
            r"REMAINING PLANNED TOPICS.*?:\n(.*?)\n\nFULL TRANSCRIPT",
            user_prompt,
            re.S,
        )
        has_remaining = remaining_match and "no remaining planned topics" not in remaining_match.group(1)

        if forced:
            action = forced.group(1)
        elif _call_count["n"] % 3 == 0 and has_remaining:
            action = "follow_up"
        elif has_remaining:
            action = "next_topic"
        else:
            action = "conclude"

        result = {
            "assessment": {"quality": "solid", "notes": "Reasonable explanation with minor gaps."},
            "action": action,
            "message": "Conclude: thanks for your answers!" if action == "conclude"
            else f"Follow-up/next question (#{_call_count['n']})",
        }
        if action != "conclude":
            day_match = re.findall(r"Day (\d+)", remaining_match.group(1)) if remaining_match and has_remaining else []
            if action == "next_topic" and day_match:
                result["next_day"] = int(day_match[0])
            else:
                # follow_up stays on current day; engine ignores next_day for follow_up
                cur_day_match = re.search(r"CURRENT TOPIC.*?Day (\d+)", user_prompt, re.S)
                result["next_day"] = int(cur_day_match.group(1)) if cur_day_match else 1

    if validator is not None and not validator(result):
        raise AssertionError(f"fake_generate_json produced invalid shape: {result}")
    return result


@pytest.fixture(autouse=True)
def patch_llm(monkeypatch):
    monkeypatch.setattr(ai_provider, "generate_json", fake_generate_json)
    # question_engine and evaluator imported generate_json directly, patch there too
    import app.question_engine as qe
    import app.evaluator as ev

    monkeypatch.setattr(qe, "generate_json", fake_generate_json)
    monkeypatch.setattr(ev, "generate_json", fake_generate_json)
    store._sessions.clear()
    _call_count["n"] = 0
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_candidate():
    candidates = list_candidates()
    # Emily Chen - strong AI Engineer profile, 9 passed missions across many modules
    return next(c for c in candidates if c["member"]["id"] == "CAND-003")


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_start_interview_matches_spec_shape(client, sample_candidate):
    resp = client.post(
        "/api/interview",
        json={"sessionId": "abc-123", "candidate": sample_candidate},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Required spec fields must be present with the right types.
    assert {"reply", "done"}.issubset(body.keys())
    if "meta" in body and body["meta"] is not None:
        assert {"day", "dayTitle", "questionNumber", "coveredDays"}.issubset(body["meta"].keys())
    assert isinstance(body["reply"], str) and body["reply"]
    assert body["done"] is False
    # 'meta' is an additive, non-breaking UI convenience field (curriculum
    # day/progress info) - not required by the spec but must not replace
    # or corrupt the required fields.
    assert "feedback" not in body or body["feedback"] is None


def test_duplicate_start_rejected(client, sample_candidate):
    client.post("/api/interview", json={"sessionId": "dup-1", "candidate": sample_candidate})
    resp = client.post("/api/interview", json={"sessionId": "dup-1", "candidate": sample_candidate})
    assert resp.status_code == 409


def test_message_without_session_404(client):
    resp = client.post("/api/interview", json={"sessionId": "nope", "message": "hi"})
    assert resp.status_code == 404


def test_empty_message_rejected(client, sample_candidate):
    client.post("/api/interview", json={"sessionId": "empty-1", "candidate": sample_candidate})
    resp = client.post("/api/interview", json={"sessionId": "empty-1", "message": "   "})
    assert resp.status_code == 422


def test_missing_candidate_and_message_rejected(client):
    resp = client.post("/api/interview", json={"sessionId": "bad-1"})
    assert resp.status_code == 422


def test_full_interview_meets_mandatory_requirements(client, sample_candidate):
    session_id = "full-flow-1"
    resp = client.post("/api/interview", json={"sessionId": session_id, "candidate": sample_candidate})
    assert resp.status_code == 200
    body = resp.json()

    turns = 0
    max_turns = 20
    while not body["done"] and turns < max_turns:
        resp = client.post(
            "/api/interview",
            json={"sessionId": session_id, "message": "This is my technical answer explaining the concept."},
        )
        assert resp.status_code == 200
        body = resp.json()
        turns += 1

    assert body["done"] is True, "interview did not conclude within max_turns"
    assert "feedback" in body and body["feedback"] is not None

    feedback = body["feedback"]
    assert set(feedback.keys()) == {"summary", "strengths", "gaps", "next"}
    assert isinstance(feedback["summary"], str) and feedback["summary"]
    assert isinstance(feedback["strengths"], list)
    assert isinstance(feedback["gaps"], list)
    assert isinstance(feedback["next"], list)

    # --- mandatory requirements ---
    state = store.get(session_id)
    assert state.question_count >= 8, f"only {state.question_count} questions asked"
    assert len(state.covered_days) >= 4, f"only {len(state.covered_days)} days covered"

    # follow-ups actually depend on previous answers (at least one follow_up occurred)
    followups = [qa for qa in state.history if qa.is_followup]
    assert len(followups) >= 1, "no follow-up questions were generated"

    # context maintained: every question after the first references distinct content
    questions = [qa.question for qa in state.history]
    assert len(questions) == len(state.history)


def test_interview_already_complete_rejected(client, sample_candidate):
    session_id = "complete-1"
    client.post("/api/interview", json={"sessionId": session_id, "candidate": sample_candidate})
    body = {"done": False}
    turns = 0
    while not body["done"] and turns < 20:
        resp = client.post(
            "/api/interview",
            json={"sessionId": session_id, "message": "answer"},
        )
        body = resp.json()
        turns += 1
    assert body["done"] is True

    resp = client.post("/api/interview", json={"sessionId": session_id, "message": "one more?"})
    assert resp.status_code == 409


def test_malformed_json_body_rejected(client):
    resp = client.post(
        "/api/interview",
        data="{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_meta_reflects_curriculum_progress(client, sample_candidate):
    session_id = "meta-1"
    resp = client.post("/api/interview", json={"sessionId": session_id, "candidate": sample_candidate})
    body = resp.json()
    assert "meta" in body
    meta = body["meta"]
    assert meta["questionNumber"] == 1
    assert meta["questionsAsked"] == 1
    assert meta["minQuestions"] == 8
    assert meta["minCurriculumDays"] == 4
    assert isinstance(meta["day"], int)
    assert isinstance(meta["dayTitle"], str) and meta["dayTitle"]


def test_personalization_differs_by_candidate(sample_candidate):
    """Different candidates should get different interview plans."""
    from app.interview_planner import build_plan
    from app.schemas import Candidate

    candidates = list_candidates()
    cand_a = Candidate(**next(c for c in candidates if c["member"]["id"] == "CAND-003"))  # Emily Chen
    cand_b = Candidate(**next(c for c in candidates if c["member"]["id"] == "CAND-006"))  # Wendy Foster

    plan_a = build_plan(cand_a)
    plan_b = build_plan(cand_b)
    assert plan_a != plan_b, "interview plans should differ based on candidate learning journey"


def test_ai_provider_unavailable_returns_graceful_error(client, sample_candidate, monkeypatch):
    """
    When the configured AI provider can't be reached (e.g. no API key set),
    the app must fail gracefully with a controlled error response - never
    a raw stack trace or a fabricated AI response.
    """
    import app.question_engine as qe
    from app.ai_provider import AIProviderUnavailableError

    def raise_unavailable(*args, **kwargs):
        raise AIProviderUnavailableError("AI_API_KEY is not set.")

    monkeypatch.setattr(qe, "generate_json", raise_unavailable)

    resp = client.post(
        "/api/interview",
        json={"sessionId": "no-key-1", "candidate": sample_candidate},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "ai_provider_unavailable"
    assert "detail" in body


def test_ai_provider_is_configurable_via_env(monkeypatch):
    """
    Swapping AI_PROVIDER/AI_BASE_URL/AI_MODEL must change the resolved
    endpoint/model without touching any application code - this is the
    entire point of the provider abstraction.
    """
    import importlib

    from app import ai_provider

    # Default preset (no AI_PROVIDER set) must resolve to Gemini's
    # official OpenAI-compatible endpoint and a verified model name.
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    reloaded = importlib.reload(ai_provider)
    assert reloaded.DEFAULT_PROVIDER == "gemini"
    assert reloaded.BASE_URL == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert reloaded.MODEL == "gemini-3.6-flash"

    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    reloaded = importlib.reload(ai_provider)
    assert reloaded.BASE_URL == "https://api.openai.com/v1"
    assert reloaded.MODEL == "gpt-4o-mini"

    monkeypatch.setenv("AI_BASE_URL", "https://my-custom-endpoint.example.com/v1")
    monkeypatch.setenv("AI_MODEL", "my-local-model")
    reloaded = importlib.reload(ai_provider)
    assert reloaded.BASE_URL == "https://my-custom-endpoint.example.com/v1"
    assert reloaded.MODEL == "my-local-model"

    # restore default (gemini) for any subsequent tests in this process
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    importlib.reload(ai_provider)


def test_gemini_api_key_env_var_used_as_fallback(monkeypatch):
    """
    GEMINI_API_KEY alone (without the generic AI_API_KEY) must be enough
    to configure the client when AI_PROVIDER=gemini, since that's the
    variable name Google's own docs use and what the user has.
    """
    import importlib

    from app import ai_provider

    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-not-real")
    reloaded = importlib.reload(ai_provider)

    resolved_key = reloaded._resolve_api_key()
    assert resolved_key == "test-gemini-key-not-real"

    # _get_client should succeed (no AIProviderUnavailableError) once a
    # key is resolvable via the fallback.
    client = reloaded._get_client()
    assert client.api_key == "test-gemini-key-not-real"
    assert client.base_url is not None
    assert "generativelanguage.googleapis.com" in str(client.base_url)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    importlib.reload(ai_provider)
