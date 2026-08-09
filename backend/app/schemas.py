"""
Pydantic models for the /api/interview endpoint.

The Candidate/InterviewRequest/InterviewResponse/Feedback shapes mirror
technical-spec.md verbatim - those are the required contract. TurnMeta is
an additive, optional field used only for the UI's progress display (see
its docstring); it never replaces or hides the required fields.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CandidateMission(BaseModel):
    day: int
    title: str
    passed: Optional[bool] = None
    attempts: Optional[int] = None
    skipped: Optional[bool] = None


class CandidateMember(BaseModel):
    id: str
    name: str
    jobRole: str
    yearsExperience: int
    education: str
    status: str


class CandidateSignals(BaseModel):
    commitDays: Optional[int] = None
    missionsCompleted: Optional[int] = None
    missionsFirstTry: Optional[int] = None


class Candidate(BaseModel):
    """Matches one entry of candidates.json exactly."""
    member: CandidateMember
    missions: list[CandidateMission]
    signals: CandidateSignals


class InterviewRequest(BaseModel):
    """
    Single request body for POST /api/interview.

    - Start turn: sessionId + candidate
    - Subsequent turns: sessionId + message
    Both fields are optional at the schema level so a single endpoint can
    dispatch on which one is present, per the spec's two request shapes.
    """
    sessionId: str
    candidate: Optional[Candidate] = None
    message: Optional[str] = None


class Feedback(BaseModel):
    summary: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next: list[str] = Field(default_factory=list)


class TurnMeta(BaseModel):
    """
    Additive UI metadata, NOT part of the required Technical Specification
    contract (which only requires reply/done/feedback). Included so the
    Interview screen can show which curriculum day/topic is being
    assessed, whether a question is a follow-up, and live progress
    against the mandatory minimums, per the product's UI requirements.
    Consumers that only care about the spec's required fields can safely
    ignore this object.
    """
    questionNumber: int
    day: int
    dayTitle: str
    isFollowUp: bool
    coveredDays: list[int]
    questionsAsked: int
    minQuestions: int
    minCurriculumDays: int


class InterviewResponse(BaseModel):
    reply: str
    done: bool
    feedback: Optional[Feedback] = None
    meta: Optional[TurnMeta] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
