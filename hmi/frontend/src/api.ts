import type {
  AIRecommendation,
  HistoryResponse,
  LoginResponse,
  OverviewResponse,
  ParameterCommandRequest,
  ParameterPageResponse,
  RealtimeSeriesResponse,
  TelemetrySnapshot,
  UserPublic,
  AckRecord,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("edgehub_hmi_token");
  const headers = new Headers(options.headers ?? {});
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login(username: string, password: string) {
    return request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },
  me() {
    return request<UserPublic>("/auth/me");
  },
  getOverview() {
    return request<OverviewResponse>("/overview");
  },
  getRealtimeSnapshot() {
    return request<TelemetrySnapshot>("/realtime/snapshot");
  },
  getRealtimeSeries() {
    return request<RealtimeSeriesResponse>("/realtime/series");
  },
  getHistory() {
    return request<HistoryResponse>("/history");
  },
  getParameters() {
    return request<ParameterPageResponse>("/params");
  },
  submitParameters(payload: ParameterCommandRequest) {
    return request<AckRecord>("/params/commands", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getRecommendations() {
    return request<AIRecommendation[]>("/ai/recommendations");
  },
};
