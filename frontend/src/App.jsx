import { Routes, Route } from "react-router-dom";
import { InterviewProvider } from "./lib/InterviewContext";
import Dashboard from "./pages/Dashboard";
import CandidateOverview from "./pages/CandidateOverview";
import Interview from "./pages/Interview";
import Report from "./pages/Report";
import Shell from "./components/Shell";
import "./App.styles.css";

export default function App() {
  return (
    <InterviewProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/candidates/:id" element={<CandidateOverview />} />
          <Route path="/interview" element={<Interview />} />
          <Route path="/report" element={<Report />} />
        </Routes>
      </Shell>
    </InterviewProvider>
  );
}
