import { useNavigate } from "react-router-dom";
import { useInterview } from "../lib/InterviewContext";

const TOTAL_DAYS = 31;

export default function CandidateCard({ candidate }) {
  const navigate = useNavigate();
  const { selectCandidate } = useInterview();
  const { member, signals } = candidate;
  const pct = Math.round(((signals?.missionsCompleted || 0) / TOTAL_DAYS) * 100);

  const handleClick = () => {
    selectCandidate(candidate);
    navigate(`/candidates/${member.id}`);
  };

  return (
    <button className="candidate-card" onClick={handleClick}>
      <div className="candidate-card-top">
        <div>
          <h3 className="candidate-name">{member.name}</h3>
          <p className="candidate-role">{member.jobRole}</p>
        </div>
        <span className="candidate-id mono">{member.id}</span>
      </div>

      <div className="candidate-progress">
        <div className="candidate-progress-track">
          <div className="candidate-progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="candidate-progress-label mono">
          {signals?.missionsCompleted ?? 0}/{TOTAL_DAYS} days &middot; {pct}%
        </span>
      </div>

      <div className="candidate-meta">
        <span>{member.yearsExperience} yrs exp</span>
        <span className="dot">&middot;</span>
        <span>{member.education}</span>
      </div>
    </button>
  );
}
