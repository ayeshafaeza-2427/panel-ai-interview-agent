"""
Adaptive question generation.

Each turn, we hand the LLM: the candidate's profile, the curriculum plan,
the full transcript so far, and progress counters. The LLM decides how
to react to the candidate's last answer (follow up / move to a new
topic / conclude) and writes the actual interviewer message. We enforce
the hard requirements (>=8 questions, >=4 days) as code-level guardrails
around the LLM's judgement rather than trusting it blindly.
"""
from __future__ import annotations

import logging

from app.curriculum_loader import get_day
from app.interview_planner import build_plan
from app.interview_state import (
    MIN_CURRICULUM_DAYS,
    MIN_QUESTIONS,
    InterviewState,
    QAPair,
)
from app.ai_provider import generate_json
from app.schemas import Candidate

logger = logging.getLogger("interview_agent.question_engine")

MAX_QUESTIONS_HARD_CAP = 14  # safety valve so the interview can't run forever
MAX_FOLLOWUPS_PER_DAY = 2


SYSTEM_PROMPT = """You are a senior technical interviewer for an enterprise AI \
engineering cohort. You are interviewing a real candidate about material \
they actually completed during a 31-day AI engineering program (RAG, \
vector databases, prompt engineering, agentic AI, MCP, deployment).

Your interviewing style:
- Professional, warm, direct. Like a real senior engineer, not a quiz bot.
- Ask ONE question at a time.
- Base every question on the actual curriculum day content provided to you.
- When reacting to the candidate's last answer: if it's strong, go deeper \
or raise difficulty; if it's incomplete, ask a clarifying follow-up; if \
it's incorrect, probe gently to see if they can self-correct; avoid \
repeating a topic more than necessary.
- Never invent curriculum content that wasn't given to you.
- Keep questions concise (1-3 sentences).

You must always reply with a single JSON object and nothing else."""


def _format_candidate_profile(candidate: Candidate) -> str:
    m = candidate.member
    passed = [
        f"Day {ms.day} ({ms.title})"
        for ms in candidate.missions
        if ms.passed is True
    ]
    failed = [
        f"Day {ms.day} ({ms.title})"
        for ms in candidate.missions
        if ms.passed is False
    ]
    skipped = [
        f"Day {ms.day} ({ms.title})"
        for ms in candidate.missions
        if ms.skipped is True
    ]
    return (
        f"Name: {m.name}\n"
        f"Role: {m.jobRole} ({m.yearsExperience} yrs experience, {m.education})\n"
        f"Passed missions: {', '.join(passed) if passed else 'none'}\n"
        f"Failed attempts: {', '.join(failed) if failed else 'none'}\n"
        f"Skipped: {', '.join(skipped) if skipped else 'none'}\n"
        f"Signals: commitDays={candidate.signals.commitDays}, "
        f"missionsCompleted={candidate.signals.missionsCompleted}, "
        f"missionsFirstTry={candidate.signals.missionsFirstTry}"
    )


def _format_transcript(state: InterviewState) -> str:
    if not state.history:
        return "(no questions asked yet)"
    lines = []
    for qa in state.history:
        tag = "follow-up" if qa.is_followup else "new topic"
        lines.append(
            f"Q{qa.question_number} [Day {qa.day} - {qa.day_title}, {tag}]: "
            f"{qa.question}\nA{qa.question_number}: {qa.answer}"
        )
    return "\n\n".join(lines)


def _day_context(day_number: int) -> str:
    d = get_day(day_number)
    if not d:
        return f"Day {day_number}: (no curriculum data found)"
    return (
        f"Day {d['day']}: {d['title']} (type: {d['type']})\n"
        f"Tools: {', '.join(d.get('tools', []))}\n"
        f"Objectives: {'; '.join(d.get('objectives', []))}"
    )


def _remaining_plan_days(state: InterviewState) -> list[int]:
    plan = build_plan(state.candidate)
    return [d for d in plan if d not in state.covered_days]


def _followups_asked_on(state: InterviewState, day: int) -> int:
    return sum(1 for qa in state.history if qa.day == day and qa.is_followup)


def _validate_turn_response(parsed: dict) -> bool:
    required = {"message", "action"}
    if not required.issubset(parsed.keys()):
        return False
    if parsed["action"] not in ("follow_up", "next_topic", "conclude"):
        return False
    if parsed["action"] != "conclude" and "next_day" not in parsed:
        return False
    return isinstance(parsed["message"], str) and len(parsed["message"]) > 0


def start_interview(state: InterviewState) -> tuple[str, dict]:
    """Generates the welcome message + first question. Returns (reply, meta)."""
    plan = build_plan(state.candidate)
    first_day = plan[0]
    day_ctx = _day_context(first_day)

    user_prompt = f"""CANDIDATE PROFILE:
{_format_candidate_profile(state.candidate)}

PLANNED CURRICULUM COVERAGE (candidate's own completed days, in interview order):
{', '.join(f'Day {d}' for d in plan)}

FIRST TOPIC TO ASK ABOUT:
{day_ctx}

This is the very first turn. Write a brief, warm welcome (1-2 sentences) \
that references the candidate by first name and the interview's purpose, \
followed by your first technical question about the FIRST TOPIC above. \
Combine the welcome and the question into a single natural message.

Reply with ONLY this JSON object:
{{
  "message": "<welcome + first question, as one message>",
  "action": "next_topic",
  "next_day": {first_day}
}}"""

    parsed = generate_json(
        SYSTEM_PROMPT, user_prompt, validator=_validate_turn_response
    )

    qa = QAPair(
        question_number=1,
        day=first_day,
        day_title=get_day(first_day)["title"] if get_day(first_day) else "",
        question=parsed["message"],
        is_followup=False,
    )
    state.record_question(qa)
    state.status = state.status.IN_PROGRESS

    meta = {
        "questionNumber": qa.question_number,
        "day": qa.day,
        "dayTitle": qa.day_title,
        "isFollowUp": qa.is_followup,
        "coveredDays": sorted(state.covered_days),
        "questionsAsked": state.question_count + 1,  # +1: pending question not yet answered
        "minQuestions": MIN_QUESTIONS,
        "minCurriculumDays": MIN_CURRICULUM_DAYS,
    }
    return parsed["message"], meta


def process_answer(state: InterviewState, answer: str) -> tuple[str, bool, dict | None]:
    """
    Records the candidate's answer to the pending question, decides the
    next action, and either returns the next question or signals that
    the interview is complete (caller then triggers final evaluation).

    Returns (reply_text, done, meta). meta is None when done=True since
    the final turn's structured feedback (generated separately) covers
    that information instead.
    """
    state.record_answer(answer)

    remaining_days = _remaining_plan_days(state)
    can_conclude = state.meets_minimums
    must_continue = state.question_count < MIN_QUESTIONS or (
        len(state.covered_days) < MIN_CURRICULUM_DAYS and remaining_days
    )
    hard_cap_reached = state.question_count >= MAX_QUESTIONS_HARD_CAP

    last_qa = state.history[-1]
    followups_on_day = _followups_asked_on(state, last_qa.day)
    allow_followup = followups_on_day < MAX_FOLLOWUPS_PER_DAY

    if hard_cap_reached:
        forced_action = "conclude"
    elif must_continue and not remaining_days:
        # Out of new topics but still short of minimums -> must follow up.
        forced_action = "follow_up"
    else:
        forced_action = None  # let the LLM decide, within guardrails below

    day_ctx = _day_context(last_qa.day)
    remaining_ctx = (
        "\n".join(_day_context(d) for d in remaining_days)
        if remaining_days
        else "(no remaining planned topics)"
    )

    guardrail_notes = []
    if not allow_followup:
        guardrail_notes.append(
            f"Day {last_qa.day} has already had {followups_on_day} follow-ups; "
            "do not choose follow_up for this day again, choose next_topic or conclude."
        )
    if must_continue:
        guardrail_notes.append(
            f"The interview REQUIRES at least {MIN_QUESTIONS} questions across "
            f"{MIN_CURRICULUM_DAYS} curriculum days. So far: "
            f"{state.question_count} questions, {len(state.covered_days)} days "
            f"covered ({sorted(state.covered_days)}). Do NOT choose 'conclude' yet."
        )
    if can_conclude and not remaining_days:
        guardrail_notes.append(
            "Minimums are met and there are no remaining planned topics. "
            "Prefer 'conclude' unless one more follow-up would meaningfully "
            "improve the assessment."
        )
    if forced_action:
        guardrail_notes.append(f"You MUST set action to '{forced_action}'.")

    user_prompt = f"""CANDIDATE PROFILE:
{_format_candidate_profile(state.candidate)}

CURRENT TOPIC (the question just answered):
{day_ctx}

REMAINING PLANNED TOPICS (not yet covered):
{remaining_ctx}

FULL TRANSCRIPT SO FAR:
{_format_transcript(state)}

PROGRESS: {state.question_count} questions asked, \
{len(state.covered_days)} curriculum days covered so far \
({sorted(state.covered_days)}).

GUARDRAILS:
{chr(10).join('- ' + n for n in guardrail_notes) if guardrail_notes else '- none'}

TASK:
1. Assess the candidate's most recent answer (to the current topic question).
2. Decide the next action:
   - "follow_up": ask a deeper/clarifying question on the SAME day/topic, \
because the answer was strong (go deeper), incomplete (clarify), or \
incorrect (probe understanding).
   - "next_topic": move to a new day from REMAINING PLANNED TOPICS.
   - "conclude": end the interview (only if minimums are already met).
3. Write the actual next interviewer message (the follow-up or new \
question), or a brief closing line if concluding.

Reply with ONLY this JSON object:
{{
  "assessment": {{"quality": "strong|solid|incomplete|incorrect", "notes": "<1-2 sentences>"}},
  "action": "follow_up|next_topic|conclude",
  "next_day": <curriculum day number this question targets, omit if action is conclude>,
  "message": "<the next question, or closing line if concluding>"
}}"""

    parsed = generate_json(
        SYSTEM_PROMPT, user_prompt, validator=_validate_turn_response
    )

    # Enforce guardrails at the code level even if the LLM ignored them.
    action = parsed["action"]
    if forced_action:
        action = forced_action
    if action == "conclude" and not can_conclude:
        action = "follow_up" if allow_followup else "next_topic"
    if action == "follow_up" and not allow_followup:
        action = "next_topic" if remaining_days else "conclude"
    if action == "next_topic" and not remaining_days and not can_conclude:
        action = "follow_up" if allow_followup else "conclude"

    last_qa.assessment = parsed.get("assessment")
    if last_qa.assessment:
        quality = last_qa.assessment.get("quality", "")
        note = last_qa.assessment.get("notes", "")
        if quality in ("strong", "solid") and note:
            state.strengths.append(f"Day {last_qa.day} ({last_qa.day_title}): {note}")
        elif quality in ("incomplete", "incorrect") and note:
            state.weaknesses.append(f"Day {last_qa.day} ({last_qa.day_title}): {note}")

    if action == "conclude":
        state.status = state.status.COMPLETE
        return parsed["message"], True, None

    if action == "follow_up":
        next_day = last_qa.day
        is_followup = True
    else:  # next_topic
        next_day = parsed.get("next_day") or (
            remaining_days[0] if remaining_days else last_qa.day
        )
        if next_day not in remaining_days and remaining_days:
            next_day = remaining_days[0]
        is_followup = False

    qa = QAPair(
        question_number=state.question_count + 1,
        day=next_day,
        day_title=get_day(next_day)["title"] if get_day(next_day) else "",
        question=parsed["message"],
        is_followup=is_followup,
    )
    state.record_question(qa)
    meta = {
        "questionNumber": qa.question_number,
        "day": qa.day,
        "dayTitle": qa.day_title,
        "isFollowUp": qa.is_followup,
        "coveredDays": sorted(state.covered_days),
        "questionsAsked": state.question_count,  # last one is pending (unanswered)
        "minQuestions": MIN_QUESTIONS,
        "minCurriculumDays": MIN_CURRICULUM_DAYS,
    }
    return parsed["message"], False, meta
