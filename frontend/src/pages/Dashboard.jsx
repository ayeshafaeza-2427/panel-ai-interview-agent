import { useEffect } from "react";
import { useInterview } from "../lib/InterviewContext";
import CandidateCard from "../components/CandidateCard";
import "./Dashboard.styles.css";

export default function Dashboard() {
  const { candidates, candidatesLoading, candidatesError, loadCandidates } = useInterview();

  useEffect(() => {
    loadCandidates();
  }, [loadCandidates]);

  return (
    <main className="page">
      <section className="hero">
        <span className="eyebrow">&#9679; Technical interview agent</span>
        <h1 className="hero-title">
          An interviewer that actually
          <br />
          read the cohort's work.
        </h1>
        <p className="hero-sub">
          Panel builds a live technical interview from each candidate's real 31-day
          learning journey &mdash; what they passed, what they skipped, and how they
          got there &mdash; then adapts every follow-up to what they just said.
        </p>
      </section>

      <div className="section-head">
        <h2>Select a candidate</h2>
        <span className="section-count mono">{candidates.length} available</span>
      </div>

      {candidatesLoading && <p className="muted">Loading candidates&hellip;</p>}
      {candidatesError && <div className="error-banner">{candidatesError}</div>}

      {!candidatesLoading && !candidatesError && (
        <div className="candidate-grid">
          {candidates.map((c) => (
            <CandidateCard key={c.member.id} candidate={c} />
          ))}
        </div>
      )}
    </main>
  );
}
