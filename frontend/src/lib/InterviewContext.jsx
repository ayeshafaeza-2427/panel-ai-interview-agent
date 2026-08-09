import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { api, ApiError } from "./api";

const InterviewContext = createContext(null);

function makeSessionId() {
  return "sess-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export function InterviewProvider({ children }) {
  const [candidates, setCandidates] = useState([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesError, setCandidatesError] = useState(null);

  const [selectedCandidate, setSelectedCandidate] = useState(null);

  const [sessionId, setSessionId] = useState(null);
  const [turns, setTurns] = useState([]); // [{ role: 'interviewer'|'candidate', text }]
  const [questionCount, setQuestionCount] = useState(0);
  const [coveredDays, setCoveredDays] = useState([]);
  const [currentMeta, setCurrentMeta] = useState(null);
  const [done, setDone] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const loadCandidates = useCallback(async () => {
    setCandidatesLoading(true);
    setCandidatesError(null);
    try {
      const data = await api.listCandidates();
      setCandidates(data.candidates || []);
    } catch (err) {
      setCandidatesError(err instanceof ApiError ? err.message : "Failed to load candidates.");
    } finally {
      setCandidatesLoading(false);
    }
  }, []);

  const selectCandidate = useCallback((candidate) => {
    setSelectedCandidate(candidate);
  }, []);

  const resetInterview = useCallback(() => {
    setSessionId(null);
    setTurns([]);
    setQuestionCount(0);
    setCoveredDays([]);
    setCurrentMeta(null);
    setDone(false);
    setFeedback(null);
    setError(null);
  }, []);

  const startInterview = useCallback(async (candidate) => {
    resetInterview();
    setBusy(true);
    setError(null);
    const newSessionId = makeSessionId();
    try {
      const res = await api.startInterview(newSessionId, candidate);
      setSessionId(newSessionId);
      setTurns([{ role: "interviewer", text: res.reply }]);
      setQuestionCount(res.meta?.questionsAsked ?? 1);
      if (res.meta) {
        setCurrentMeta(res.meta);
        setCoveredDays(res.meta.coveredDays || []);
      }
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start interview.");
      return false;
    } finally {
      setBusy(false);
    }
  }, [resetInterview]);

  const sendAnswer = useCallback(async (answerText) => {
    if (!sessionId || !answerText.trim()) return;
    setBusy(true);
    setError(null);
    setTurns((t) => [...t, { role: "candidate", text: answerText }]);
    try {
      const res = await api.sendMessage(sessionId, answerText);
      setTurns((t) => [...t, { role: "interviewer", text: res.reply }]);
      if (res.meta) {
        setCurrentMeta(res.meta);
        setCoveredDays(res.meta.coveredDays || []);
        setQuestionCount(res.meta.questionsAsked);
      } else if (!res.done) {
        setQuestionCount((c) => c + 1);
      }
      if (res.done) {
        setDone(true);
        setFeedback(res.feedback || null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to send your answer.");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const value = useMemo(
    () => ({
      candidates,
      candidatesLoading,
      candidatesError,
      loadCandidates,
      selectedCandidate,
      selectCandidate,
      sessionId,
      turns,
      questionCount,
      coveredDays,
      currentMeta,
      done,
      feedback,
      busy,
      error,
      startInterview,
      sendAnswer,
      resetInterview,
    }),
    [
      candidates,
      candidatesLoading,
      candidatesError,
      loadCandidates,
      selectedCandidate,
      selectCandidate,
      sessionId,
      turns,
      questionCount,
      coveredDays,
      currentMeta,
      done,
      feedback,
      busy,
      error,
      startInterview,
      sendAnswer,
      resetInterview,
    ],
  );

  return <InterviewContext.Provider value={value}>{children}</InterviewContext.Provider>;
}

export function useInterview() {
  const ctx = useContext(InterviewContext);
  if (!ctx) throw new Error("useInterview must be used inside InterviewProvider");
  return ctx;
}
