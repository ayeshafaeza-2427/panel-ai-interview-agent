from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import evaluator, question_engine
from app.curriculum_loader import load_curriculum
from app.candidate_loader import list_candidates
from app.interview_planner import plan_summary
from app.interview_state import InterviewStatus, store
from app.ai_provider import AIProviderMalformedResponseError, AIProviderUnavailableError
from app.schemas import Candidate, Feedback, InterviewRequest, InterviewResponse, TurnMeta

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("interview_agent.api")

app = FastAPI(title="AI Interview Agent", version="1.0.0")

allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# --- Supporting read-only endpoints for the frontend (NOT part of the -----
# --- required Technical Specification contract, which is /api/interview --
# --- alone). These simply expose the supplied hackathon data so the UI ----
# --- can render the dashboard/candidate selection without duplicating -----
# --- the JSON files client-side.                                          -
@app.get("/api/candidates")
def get_candidates() -> dict:
    return {"candidates": list_candidates()}


@app.get("/api/curriculum")
def get_curriculum() -> dict:
    return load_curriculum()


@app.post("/api/plan")
def get_plan(candidate: Candidate) -> dict:
    """Preview the interview coverage plan for a candidate before starting -
    used by the Candidate Overview screen. Uses the same planner the real
    interview uses, so what's shown is what will actually happen."""
    return {"plan": plan_summary(candidate)}


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    logger.warning("Validation error: %s", exc)
    return JSONResponse(
        status_code=422,
        content={"error": "invalid_request", "detail": "Malformed request body."},
    )


@app.post("/api/interview", response_model=InterviewResponse, response_model_exclude_none=True)
async def interview(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_json", "detail": "Request body must be valid JSON."},
        )

    try:
        payload = InterviewRequest.model_validate(body)
    except ValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_request", "detail": str(exc)},
        )

    session_id = payload.sessionId
    if not session_id:
        return JSONResponse(
            status_code=422,
            content={"error": "missing_session_id", "detail": "sessionId is required."},
        )

    existing = store.get(session_id)

    try:
        # --- Start turn: candidate provided, no existing session -----------
        if payload.candidate is not None:
            if existing is not None:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "session_already_exists",
                        "detail": f"Session '{session_id}' already started. "
                        "Send subsequent turns with 'message' instead of 'candidate'.",
                    },
                )
            state = store.create(session_id, payload.candidate)
            reply, meta = question_engine.start_interview(state)
            return InterviewResponse(reply=reply, done=False, meta=TurnMeta(**meta))

        # --- Conversation / end turn: message provided ----------------------
        if payload.message is not None:
            if existing is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "session_not_found",
                        "detail": f"No interview session found for sessionId "
                        f"'{session_id}'. Start an interview first by sending "
                        "'candidate' with this sessionId.",
                    },
                )
            if existing.status == InterviewStatus.COMPLETE:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "interview_already_complete",
                        "detail": "This interview session has already finished.",
                    },
                )
            if not payload.message.strip():
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": "empty_message",
                        "detail": "message cannot be empty.",
                    },
                )

            reply, done, meta = question_engine.process_answer(existing, payload.message)

            if not done:
                return InterviewResponse(reply=reply, done=False, meta=TurnMeta(**meta))

            feedback: Feedback = evaluator.generate_feedback(existing)
            return InterviewResponse(reply=reply, done=True, feedback=feedback)

        # --- Neither candidate nor message provided --------------------------
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_request",
                "detail": "Request must include either 'candidate' (to start) "
                "or 'message' (to continue).",
            },
        )

    except AIProviderUnavailableError as exc:
        logger.error("AI provider unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "ai_provider_unavailable", "detail": str(exc)},
        )
    except AIProviderMalformedResponseError as exc:
        logger.error("AI provider malformed response: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": "ai_provider_malformed_response", "detail": str(exc)},
        )
    except Exception:  # noqa: BLE001 - controlled catch-all, logged, no stack trace to client
        logger.exception("Unhandled error in /api/interview")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "An unexpected error occurred."},
        )
