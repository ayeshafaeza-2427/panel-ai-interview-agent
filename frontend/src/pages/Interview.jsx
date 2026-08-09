import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useInterview } from "../lib/InterviewContext";
import "./Interview.styles.css";

const MIN_QUESTIONS = 8;
const MIN_DAYS = 4;

export default function Interview() {
  const navigate = useNavigate();
  const {
    selectedCandidate,
    sessionId,
    turns,
    questionCount,
    coveredDays,
    currentMeta,
    done,
    feedback,
    busy,
    error,
    sendAnswer,
  } = useInterview();

  const [draft, setDraft] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!sessionId) {
      navigate("/");
    }
  }, [sessionId, navigate]);

  useEffect(() => {
    if (done && feedback) {
      navigate("/report");
    }
  }, [done, feedback, navigate]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  if (!selectedCandidate || !sessionId) return null;

  const { member } = selectedCandidate;
  const progressPct = Math.min(100, Math.round((questionCount / MIN_QUESTIONS) * 100));

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!draft.trim() || busy) return;
    sendAnswer(draft);
    setDraft("");
  };

  return (
    <main className="page interview-page">
      <div className="interview-header">
        <div>
          <span className="eyebrow">&#9679; Live interview &middot; {member.name}</span>
          <h1 className="interview-title">Technical interview</h1>
        </div>
        <div className="interview-progress-block">
          <span className="mono progress-label">
            Question {questionCount} &middot; {MIN_QUESTIONS}+ required
          </span>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
        </div>
      </div>

      {currentMeta && (
        <div className="topic-strip">
          <span className="badge badge-accent mono">
            Day {currentMeta.day} &middot; {currentMeta.dayTitle}
          </span>
          {currentMeta.isFollowUp && (
            <span className="badge mono">Follow-up based on your previous answer</span>
          )}
          <span className="badge mono">{coveredDays.length} curriculum {coveredDays.length === 1 ? "area" : "areas"} covered</span>
        </div>
      )}

      <div className="interview-layout">
        <div className="transcript-panel card">
          <div className="transcript-scroll" ref={scrollRef}>
            {turns.map((t, i) => (
              <TurnBubble key={i} turn={t} />
            ))}
            {busy && (
              <div className="bubble bubble-interviewer bubble-pending">
                <span className="bubble-role mono">Interviewer</span>
                <span className="thinking">
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                  adapting to your answer
                </span>
              </div>
            )}
          </div>

          {error && <div className="error-banner interview-error">{error}</div>}

          <form className="answer-form" onSubmit={handleSubmit}>
            <textarea
              className="answer-input"
              placeholder="Type your answer…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  handleSubmit(e);
                }
              }}
              rows={3}
              disabled={busy}
            />
            <button className="btn btn-primary" type="submit" disabled={busy || !draft.trim()}>
              {busy ? <span className="spinner" /> : null}
              Submit answer
            </button>
          </form>
        </div>

        <aside className="interview-sidebar">
          <div className="card card-tight">
            <h3 className="sidebar-title">Candidate</h3>
            <p className="sidebar-name">{member.name}</p>
            <p className="sidebar-role">{member.jobRole}</p>
          </div>

          <div className="card card-tight">
            <h3 className="sidebar-title">Coverage requirement</h3>
            <RequirementRow label="Questions" current={questionCount} min={MIN_QUESTIONS} />
            <RequirementRow label="Curriculum days" current={coveredDays.length} min={MIN_DAYS} />
            {coveredDays.length > 0 && (
              <div className="covered-days-list mono">
                {coveredDays.map((d) => (
                  <span key={d} className="badge badge-success">
                    Day {d}
                  </span>
                ))}
              </div>
            )}
            <p className="sidebar-hint">
              The interviewer adapts each question to your last answer &mdash; going
              deeper on strong answers, clarifying incomplete ones, and moving
              topics once an area is well covered.
            </p>
          </div>
        </aside>
      </div>
    </main>
  );
}

function TurnBubble({ turn }) {
  const isInterviewer = turn.role === "interviewer";
  return (
    <div className={`bubble ${isInterviewer ? "bubble-interviewer" : "bubble-candidate"}`}>
      <span className="bubble-role mono">{isInterviewer ? "Interviewer" : "You"}</span>
      <p className="bubble-text">{turn.text}</p>
    </div>
  );
}

function RequirementRow({ label, current, min }) {
  const met = current !== null && current >= min;
  return (
    <div className="requirement-row">
      <span className="requirement-label">{label}</span>
      <span className={`requirement-value mono ${met ? "tone-success" : ""}`}>
        {current}/{min}
      </span>
    </div>
  );
}
