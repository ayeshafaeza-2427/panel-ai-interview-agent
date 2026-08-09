"""
Session-level interview state.

Persistent user accounts / long-term history are explicitly out of scope
per the hackathon problem statement, so this is a simple in-memory store
keyed by sessionId. State is lost on process restart, which is acceptable
for a hackathon demo.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.schemas import Candidate

MIN_QUESTIONS = 8
MIN_CURRICULUM_DAYS = 4


class InterviewStatus(str, Enum):
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass
class QAPair:
    question_number: int
    day: int
    day_title: str
    question: str
    answer: Optional[str] = None
    assessment: Optional[dict[str, Any]] = None  # {quality, notes}
    is_followup: bool = False


@dataclass
class InterviewState:
    session_id: str
    candidate: Candidate
    status: InterviewStatus = InterviewStatus.PLANNING

    # planning
    planned_days: list[int] = field(default_factory=list)

    # progress
    history: list[QAPair] = field(default_factory=list)
    covered_days: set[int] = field(default_factory=set)
    current_difficulty: str = "medium"  # easy | medium | hard
    pending_question: Optional[QAPair] = None

    # evaluation inputs accumulated as we go
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    final_feedback: Optional[dict[str, Any]] = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def question_count(self) -> int:
        return len(self.history)

    @property
    def meets_minimums(self) -> bool:
        return (
            self.question_count >= MIN_QUESTIONS
            and len(self.covered_days) >= MIN_CURRICULUM_DAYS
        )

    def record_question(self, qa: QAPair) -> None:
        self.pending_question = qa

    def record_answer(self, answer: str) -> None:
        if self.pending_question is None:
            raise ValueError("No pending question to answer")
        self.pending_question.answer = answer
        self.history.append(self.pending_question)
        self.covered_days.add(self.pending_question.day)
        self.pending_question = None


class InterviewStore:
    """Thread-safe in-memory session store."""

    def __init__(self) -> None:
        self._sessions: dict[str, InterviewState] = {}
        self._lock = threading.Lock()

    def create(self, session_id: str, candidate: Candidate) -> InterviewState:
        with self._lock:
            state = InterviewState(session_id=session_id, candidate=candidate)
            self._sessions[session_id] = state
            return state

    def get(self, session_id: str) -> Optional[InterviewState]:
        with self._lock:
            return self._sessions.get(session_id)

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions


# Single process-wide store instance used by the API layer.
store = InterviewStore()
