const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (err) {
    throw new ApiError(
      "Could not reach the interview server. Check that the backend is running.",
      0,
      String(err),
    );
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    // no/invalid JSON body
  }

  if (!res.ok) {
    const detail = body?.detail || body?.error || `Request failed (${res.status})`;
    throw new ApiError(detail, res.status, body);
  }

  return body;
}

export const api = {
  listCandidates: () => request("/api/candidates"),
  getCurriculum: () => request("/api/curriculum"),
  fetchPlan: (candidate) =>
    request("/api/plan", {
      method: "POST",
      body: JSON.stringify(candidate),
    }),

  startInterview: (sessionId, candidate) =>
    request("/api/interview", {
      method: "POST",
      body: JSON.stringify({ sessionId, candidate }),
    }),

  sendMessage: (sessionId, message) =>
    request("/api/interview", {
      method: "POST",
      body: JSON.stringify({ sessionId, message }),
    }),
};

export { ApiError };
