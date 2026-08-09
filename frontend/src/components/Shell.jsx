import { Link } from "react-router-dom";

export default function Shell({ children }) {
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">P</span>
          <span className="brand-name">Panel</span>
        </Link>
        <span className="brand-tag">AI Cohort &middot; 31 Days</span>
      </header>
      {children}
    </div>
  );
}
