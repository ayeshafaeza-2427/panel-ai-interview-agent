import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useInterview } from "../lib/InterviewContext";
import { api, ApiError } from "../lib/api";
import "./CandidateOverview.styles.css";

export default function CandidateOverview() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { candidates, candidatesLoading, loadCandidates, selectedCandidate, selectCandidate, startInterview, busy, error } =
    useInterview();

  useEffect(() => {
    if (candidates.length === 0 && !candidatesLoading) loadCandidates();
  }, [candidates.length, candidatesLoading, loadCandidates]);

  const candidate =
    selectedCandidate?.member?.id === id
      ? selectedCandidate
      : candidates.find((c) => c.member.id === id);

  useEffect(() => {
    if (candidate && selectedCandidate?.member?.id !== id) selectCandidate(candidate);
  }, [candidate, id, selectedCandidate, selectCandidate]);

  if (!candidate) {
    return (
      <main className="page page-narrow">
        <p className="muted">
          {candidatesLoading ? "Loading candidate…" : (
            <>Candidate not found. Go back to the{" "}
              <span className="link" onClick={() => navigate("/")}>dashboard</span> to pick one.</>
          )}
        </p>
      </main>
    );
  }

  const { member, missions, signals } = candidate;
  const passed = missions.filter((m) => m.passed === true);
  const failed = missions.filter((m) => m.passed === false);
  const skipped = missions.filter((m) => m.skipped === true);

  const handleStart = async () => {
    const ok = await startInterview(candidate);
    if (ok) navigate("/interview");
  };

  return (
    <main className="page page-narrow">
      <span className="eyebrow">&#9679; Candidate overview</span>
      <h1 className="ov-title">{member.name}</h1>
      <p className="ov-role">
        {member.jobRole} &middot; {member.yearsExperience} yrs experience &middot; {member.education}
      </p>

      <div className="ov-signals">
        <div className="ov-signal">
          <span className="ov-signal-value mono">{signals?.missionsCompleted ?? "—"}</span>
          <span className="ov-signal-label">missions completed</span>
        </div>
        <div className="ov-signal">
          <span className="ov-signal-value mono">{signals?.commitDays ?? "—"}</span>
          <span className="ov-signal-label">active commit days</span>
        </div>
        <div className="ov-signal">
          <span className="ov-signal-value mono">{signals?.missionsFirstTry ?? "—"}</span>
          <span className="ov-signal-label">first-try passes</span>
        </div>
      </div>

      <section className="ov-section">
        <h3>Completed topics ({passed.length})</h3>
        <ul className="topic-list">
          {passed.map((m) => (
            <li key={m.day} className="topic-item">
              <span className="badge mono">Day {m.day}</span>
              <span className="topic-title">{m.title}</span>
              {m.attempts > 1 && <span className="topic-attempts mono">{m.attempts} attempts</span>}
            </li>
          ))}
        </ul>
      </section>

      {failed.length > 0 && (
        <section className="ov-section">
          <h3>Attempted, not passed ({failed.length})</h3>
          <ul className="topic-list">
            {failed.map((m) => (
              <li key={m.day} className="topic-item topic-item-warning">
                <span className="badge badge-warning mono">Day {m.day}</span>
                <span className="topic-title">{m.title}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {skipped.length > 0 && (
        <section className="ov-section">
          <h3>Skipped ({skipped.length})</h3>
          <p className="muted small">These topics will not be part of the interview.</p>
          <ul className="topic-list">
            {skipped.map((m) => (
              <li key={m.day} className="topic-item topic-item-muted">
                <span className="badge mono">Day {m.day}</span>
                <span className="topic-title">{m.title}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="ov-section">
        <h3>Interview coverage plan</h3>
        <p className="muted small">
          Built from {member.name.split(" ")[0]}'s own completed missions &mdash; drawn from across
          different curriculum modules for breadth. The interviewer may adapt this live based on
          how the conversation goes.
        </p>
        <PlanPreview candidate={candidate} />
      </section>

      {error && <div className="error-banner">{error}</div>}

      <button className="btn btn-primary btn-block" onClick={handleStart} disabled={busy}>
        {busy ? (
          <>
            <span className="spinner" /> Starting interview&hellip;
          </>
        ) : (
          "Start interview"
        )}
      </button>
    </main>
  );
}

function PlanPreview({ candidate }) {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    api
      .fetchPlan(candidate)
      .then((res) => {
        if (!cancelled) setPlan(res.plan);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof ApiError ? e.message : "Could not load plan preview.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [candidate]);

  if (loading) return <p className="muted small">Loading coverage plan&hellip;</p>;
  if (err) return <div className="error-banner">{err}</div>;
  if (!plan || plan.length === 0) return null;

  return (
    <div className="plan-rail">
      {plan.map((d) => (
        <div className="plan-node" key={d.day}>
          <span className="plan-node-dot" />
          <div>
            <span className="badge badge-accent mono">Day {d.day}</span>
            <p className="plan-node-title">{d.title}</p>
            <p className="plan-node-module">{d.module}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
