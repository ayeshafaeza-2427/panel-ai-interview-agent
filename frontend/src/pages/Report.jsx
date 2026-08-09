import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useInterview } from "../lib/InterviewContext";
import "./Report.styles.css";

export default function Report() {
  const navigate = useNavigate();
  const { selectedCandidate, feedback, coveredDays, questionCount, turns, resetInterview } =
    useInterview();

  useEffect(() => {
    if (!feedback) {
      navigate("/");
    }
  }, [feedback, navigate]);

  if (!feedback || !selectedCandidate) return null;

  const { member } = selectedCandidate;
  const answeredCount = turns.filter((t) => t.role === "candidate").length;

  const handleRestart = () => {
    resetInterview();
    navigate("/");
  };

  return (
    <main className="page page-narrow">
      <span className="eyebrow">&#9679; Interview complete</span>
      <h1 className="report-title">Interview report</h1>
      <p className="report-sub">
        {member.name} &middot; {member.jobRole}
      </p>

      <div className="report-summary card">
        <h2 className="report-summary-title">Overall assessment</h2>
        <p className="report-summary-text">{feedback.summary}</p>

        <div className="report-stats">
          <div className="report-stat">
            <span className="mono report-stat-value">{questionCount}</span>
            <span className="report-stat-label">Questions asked</span>
          </div>
          <div className="report-stat">
            <span className="mono report-stat-value">{coveredDays.length}</span>
            <span className="report-stat-label">Curriculum days covered</span>
          </div>
          <div className="report-stat">
            <span className="mono report-stat-value">{answeredCount}</span>
            <span className="report-stat-label">Answers given</span>
          </div>
        </div>
      </div>

      <div className="report-grid">
        <FeedbackList title="Strengths" tone="success" items={feedback.strengths} empty="No specific strengths flagged." />
        <FeedbackList title="Areas to revisit" tone="warning" items={feedback.gaps} empty="No significant gaps found." />
      </div>

      <section className="report-section">
        <h2>Curriculum coverage</h2>
        <div className="coverage-chips">
          {coveredDays.map((d) => (
            <span key={d} className="badge badge-success mono">
              Day {d}
            </span>
          ))}
        </div>
      </section>

      <section className="report-section">
        <h2>Recommended next steps</h2>
        <ol className="next-steps">
          {feedback.next.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ol>
      </section>

      <div className="report-actions">
        <button className="btn btn-primary" onClick={handleRestart}>
          Start another interview
        </button>
      </div>
    </main>
  );
}

function FeedbackList({ title, tone, items, empty }) {
  return (
    <div className="card card-tight feedback-list-card">
      <h3 className={`feedback-list-title tone-${tone}`}>{title}</h3>
      {items && items.length > 0 ? (
        <ul className="feedback-list">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted small" style={{ marginBottom: 0 }}>
          {empty}
        </p>
      )}
    </div>
  );
}
