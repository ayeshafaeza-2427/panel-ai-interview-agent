"""
Generates the final structured feedback object required by the spec:
{ summary, strengths, gaps, next }. Grounded entirely in the actual
transcript collected during the interview - no invented evaluation.
"""
from __future__ import annotations

from app.interview_state import InterviewState
from app.ai_provider import generate_json
from app.question_engine import SYSTEM_PROMPT, _format_candidate_profile, _format_transcript
from app.schemas import Feedback


def _validate_feedback(parsed: dict) -> bool:
    required = {"summary", "strengths", "gaps", "next"}
    if not required.issubset(parsed.keys()):
        return False
    if not isinstance(parsed["summary"], str) or not parsed["summary"]:
        return False
    for key in ("strengths", "gaps", "next"):
        if not isinstance(parsed[key], list):
            return False
        if not all(isinstance(x, str) for x in parsed[key]):
            return False
    return True


def generate_feedback(state: InterviewState) -> Feedback:
    covered = sorted(state.covered_days)
    day_titles = {qa.day: qa.day_title for qa in state.history}
    coverage_lines = "\n".join(f"- Day {d}: {day_titles.get(d, '')}" for d in covered)

    user_prompt = f"""CANDIDATE PROFILE:
{_format_candidate_profile(state.candidate)}

FULL INTERVIEW TRANSCRIPT ({state.question_count} questions, \
{len(covered)} curriculum days):
{_format_transcript(state)}

CURRICULUM DAYS COVERED:
{coverage_lines}

TASK:
Produce final structured interview feedback based ONLY on what the \
candidate actually said in the transcript above. Be specific and cite \
concrete evidence from their answers (paraphrased, not quoted). Do not \
invent achievements or gaps not supported by the transcript.

Reply with ONLY this JSON object:
{{
  "summary": "<2-4 sentence overall assessment of the candidate's technical understanding>",
  "strengths": ["<specific, evidence-based strength>", "..."],
  "gaps": ["<specific, evidence-based gap or weak area>", "..."],
  "next": ["<concrete, actionable next step for the candidate>", "..."]
}}"""

    parsed = generate_json(SYSTEM_PROMPT, user_prompt, validator=_validate_feedback)
    feedback = Feedback(**parsed)
    state.final_feedback = feedback.model_dump()
    return feedback
