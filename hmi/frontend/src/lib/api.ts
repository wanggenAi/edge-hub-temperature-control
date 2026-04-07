import type {
  AIRuntimeConfig,
  AIRuntimeRecommendationDebug,
  AIRuntimeStatus,
  AIPostEffectEvaluation,
  AITelemetryComparison,
  AIPreviewSimulation,
  AIRecommendationHistoryResponse,
  AIRecommendation,
  AIGeneratedRecommendation,
  Alarm,
  AlarmHistoryResponse,
  AlarmListResponse,
  AlarmRuleListResponse,
  AlarmRuleUpdateResponse,
  ActiveAlarmResponse,
  ControlEvaluation,
  Device,
  Me,
  Metric,
  MetricWindowStats,
  PagedDevices,
  Parameter,
  SummaryDetailResponse,
  SummaryListResponse,
  StorageRuleListResponse,
  StorageRuleMutationResponse,
  UserItem,
} from "@/types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 12000;
const APPLY_REQUEST_TIMEOUT_MS = 12000;

function toWsBase(httpBase: string): string {
  if (httpBase.startsWith("https://")) return `wss://${httpBase.slice("https://".length)}`;
  if (httpBase.startsWith("http://")) return `ws://${httpBase.slice("http://".length)}`;
  return httpBase;
}

export function buildDeviceStreamUrl(deviceId?: number): string | null {
  const token = localStorage.getItem("token");
  if (!token) return null;
  const wsBaseRaw = import.meta.env.VITE_WS_BASE_URL ?? toWsBase(API_BASE);
  const wsBase = wsBaseRaw.endsWith("/") ? wsBaseRaw : `${wsBaseRaw}/`;
  const url = new URL("stream/devices", wsBase);
  url.searchParams.set("token", token);
  if (typeof deviceId === "number" && Number.isFinite(deviceId) && deviceId > 0) {
    url.searchParams.set("device_id", String(deviceId));
  }
  return url.toString();
}

async function request<T>(path: string, init?: RequestInit, opts?: { timeoutMs?: number }): Promise<T> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (init?.headers && !Array.isArray(init.headers)) {
    Object.assign(headers, init.headers as Record<string, string>);
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timeoutMs = Math.max(1000, Number(opts?.timeoutMs ?? REQUEST_TIMEOUT_MS));
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Request timeout");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<Me>("/auth/me"),
  devices: () => request<Device[]>("/devices"),
  devicesManage: (params: { page?: number; page_size?: number; q?: string } = {}) =>
    request<PagedDevices>(
      `/devices/manage?page=${params.page ?? 1}&page_size=${params.page_size ?? 10}&q=${encodeURIComponent(
        params.q ?? ""
      )}`
    ),
  device: (id: number) => request<Device>(`/devices/${id}`),
  createDevice: (payload: {
    code: string;
    name: string;
    line: string;
    location: string;
    status?: string;
    target_temp?: number;
    current_temp?: number;
    pwm_output?: number;
    is_alarm?: boolean;
    is_online?: boolean;
  }) => request<Device>("/devices", { method: "POST", body: JSON.stringify(payload) }),
  updateDevice: (id: number, payload: Record<string, unknown>) =>
    request<Device>(`/devices/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteDevice: (id: number) => request<{ ok: boolean }>(`/devices/${id}`, { method: "DELETE" }),
  metrics: (id: number, params: { start_ms?: number; end_ms?: number; limit?: number } = {}) => {
    const sp = new URLSearchParams();
    if (typeof params.start_ms === "number") sp.set("start_ms", String(params.start_ms));
    if (typeof params.end_ms === "number") sp.set("end_ms", String(params.end_ms));
    if (typeof params.limit === "number") sp.set("limit", String(params.limit));
    const suffix = sp.toString() ? `?${sp.toString()}` : "";
    return request<Metric[]>(`/devices/${id}/metrics${suffix}`);
  },
  metricsStats: (
    id: number,
    params: { start_ms: number; end_ms: number; band: number; steady_window: number; limit?: number }
  ) => {
    const sp = new URLSearchParams();
    sp.set("start_ms", String(params.start_ms));
    sp.set("end_ms", String(params.end_ms));
    sp.set("band", String(params.band));
    sp.set("steady_window", String(params.steady_window));
    if (typeof params.limit === "number") sp.set("limit", String(params.limit));
    return request<MetricWindowStats>(`/devices/${id}/metrics/stats?${sp.toString()}`);
  },
  controlEval: (
    id: number,
    params: {
      start_ms?: number;
      end_ms?: number;
      band?: number;
      steady_window?: number;
      pwm_threshold?: number;
      saturation_warn?: number;
      saturation_high?: number;
      overshoot_limit?: number;
      limit?: number;
    } = {}
  ) => {
    const sp = new URLSearchParams();
    if (typeof params.start_ms === "number") sp.set("start_ms", String(params.start_ms));
    if (typeof params.end_ms === "number") sp.set("end_ms", String(params.end_ms));
    if (typeof params.band === "number") sp.set("band", String(params.band));
    if (typeof params.steady_window === "number") sp.set("steady_window", String(params.steady_window));
    if (typeof params.pwm_threshold === "number") sp.set("pwm_threshold", String(params.pwm_threshold));
    if (typeof params.saturation_warn === "number") sp.set("saturation_warn", String(params.saturation_warn));
    if (typeof params.saturation_high === "number") sp.set("saturation_high", String(params.saturation_high));
    if (typeof params.overshoot_limit === "number") sp.set("overshoot_limit", String(params.overshoot_limit));
    if (typeof params.limit === "number") sp.set("limit", String(params.limit));
    const suffix = sp.toString() ? `?${sp.toString()}` : "";
    return request<ControlEvaluation>(`/devices/${id}/control-eval${suffix}`);
  },
  parameters: (id: number) => request<Parameter>(`/devices/${id}/parameters`),
  updateParameters: (id: number, payload: Partial<Parameter> & { target_temp?: number }) =>
    request<Parameter>(`/devices/${id}/parameters`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  alarms: (id: number) => request<Alarm[]>(`/devices/${id}/alarms`),
  aiRecommendation: (id: number) => request<AIRecommendation>(`/devices/${id}/ai-recommendation`),
  aiRecommendationHistory: (params: { limit?: number; device_id?: number; start_ms?: number; end_ms?: number } = {}) => {
    const sp = new URLSearchParams();
    if (typeof params.limit === "number") sp.set("limit", String(params.limit));
    if (typeof params.device_id === "number") sp.set("device_id", String(params.device_id));
    if (typeof params.start_ms === "number") sp.set("start_ms", String(params.start_ms));
    if (typeof params.end_ms === "number") sp.set("end_ms", String(params.end_ms));
    const suffix = sp.toString() ? `?${sp.toString()}` : "";
    return request<AIRecommendationHistoryResponse>(`/devices/ai/recommendations/history${suffix}`);
  },
  generateAiRecommendation: (
    deviceId: number,
    params: { window_minutes?: number; end_ms?: number; limit?: number } = {}
  ) => {
    const sp = new URLSearchParams();
    if (typeof params.window_minutes === "number") sp.set("window_minutes", String(params.window_minutes));
    if (typeof params.end_ms === "number") sp.set("end_ms", String(params.end_ms));
    if (typeof params.limit === "number") sp.set("limit", String(params.limit));
    const suffix = sp.toString() ? `?${sp.toString()}` : "";
    return request<AIGeneratedRecommendation>(`/devices/${deviceId}/ai-recommendation/generate${suffix}`, { method: "POST" });
  },
  aiRecommendationPreview: (
    deviceId: number,
    params: {
      horizon_sec?: number;
      step_sec?: number;
      ambient_temp?: number;
      heating_gain?: number;
      cooling_coeff?: number;
    } = {}
  ) => {
    const sp = new URLSearchParams();
    if (typeof params.horizon_sec === "number") sp.set("horizon_sec", String(params.horizon_sec));
    if (typeof params.step_sec === "number") sp.set("step_sec", String(params.step_sec));
    if (typeof params.ambient_temp === "number") sp.set("ambient_temp", String(params.ambient_temp));
    if (typeof params.heating_gain === "number") sp.set("heating_gain", String(params.heating_gain));
    if (typeof params.cooling_coeff === "number") sp.set("cooling_coeff", String(params.cooling_coeff));
    const suffix = sp.toString() ? `?${sp.toString()}` : "";
    return request<AIPreviewSimulation>(`/devices/${deviceId}/ai-recommendation/preview${suffix}`, { method: "POST" });
  },
  evaluateAiRecommendationActual: (
    deviceId: number,
    recommendationId: number,
    payload: { observation_window_minutes?: number } = {}
  ) =>
    request<AIPostEffectEvaluation>(`/devices/${deviceId}/ai-recommendation/${recommendationId}/evaluate-actual`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  aiRecommendationTelemetryComparison: (
    deviceId: number,
    recommendationId: number,
    params: { start_ms?: number; end_ms?: number; baseline_window_minutes?: number; observation_window_minutes?: number } = {}
  ) => {
    const sp = new URLSearchParams();
    if (typeof params.start_ms === "number") sp.set("start_ms", String(params.start_ms));
    if (typeof params.end_ms === "number") sp.set("end_ms", String(params.end_ms));
    if (typeof params.baseline_window_minutes === "number") {
      sp.set("baseline_window_minutes", String(params.baseline_window_minutes));
    }
    if (typeof params.observation_window_minutes === "number") {
      sp.set("observation_window_minutes", String(params.observation_window_minutes));
    }
    const suffix = sp.toString() ? `?${sp.toString()}` : "";
    return request<AITelemetryComparison>(`/devices/${deviceId}/ai-recommendation/${recommendationId}/telemetry-comparison${suffix}`);
  },
  aiRuntimeConfig: () => request<AIRuntimeConfig>("/ai/runtime/config"),
  updateAiRuntimeConfig: (payload: Partial<AIRuntimeConfig>) =>
    request<AIRuntimeConfig>("/ai/runtime/config", { method: "PUT", body: JSON.stringify(payload) }),
  aiRuntimeStatus: () => request<AIRuntimeStatus>("/ai/runtime/status"),
  aiRuntimeRecommendationDebug: (params: { device_id?: number } = {}) => {
    const sp = new URLSearchParams();
    if (typeof params.device_id === "number") sp.set("device_id", String(params.device_id));
    const suffix = sp.toString() ? `?${sp.toString()}` : "";
    return request<AIRuntimeRecommendationDebug>(`/ai/runtime/recommendation-debug${suffix}`);
  },
  users: () => request<UserItem[]>("/users"),
  createUser: (payload: { username: string; email: string; password: string; roles: string[] }) =>
    request<UserItem>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: Record<string, unknown>) =>
    request<UserItem>(`/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteUser: (id: number) => request<{ ok: boolean }>(`/users/${id}`, { method: "DELETE" }),
  acknowledgeAlarm: (deviceId: number, alarmId: number) =>
    request<{ ok: boolean }>(`/devices/${deviceId}/alarms/${alarmId}/ack`, { method: "POST" }),
  applyAiRecommendation: (deviceId: number) =>
    request<Parameter>(`/devices/${deviceId}/ai-recommendation/apply`, { method: "POST" }, { timeoutMs: APPLY_REQUEST_TIMEOUT_MS }),
  alarmCenter: (params: { page?: number; page_size?: number; q?: string } = {}) =>
    request<AlarmListResponse>(
      `/alarms?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}&q=${encodeURIComponent(
        params.q ?? ""
      )}`
    ),
  alarmsActive: (params: { page?: number; page_size?: number; q?: string; status?: "active" | "all" } = {}) =>
    request<ActiveAlarmResponse>(
      `/alarms/active?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}&q=${encodeURIComponent(
        params.q ?? ""
      )}&status=${params.status ?? "active"}`
    ),
  alarmsHistory: (params: {
    page?: number;
    page_size?: number;
    q?: string;
    range_key?: "24h" | "7d";
    device_id?: number;
    severity?: string;
    alarm_type?: string;
    source?: string;
  } = {}) =>
    request<AlarmHistoryResponse>(
      `/alarms/history?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}&q=${encodeURIComponent(
        params.q ?? ""
      )}&range_key=${params.range_key ?? "24h"}${params.device_id ? `&device_id=${params.device_id}` : ""}${
        params.severity ? `&severity=${encodeURIComponent(params.severity)}` : ""
      }${params.alarm_type ? `&alarm_type=${encodeURIComponent(params.alarm_type)}` : ""}${
        params.source ? `&source=${encodeURIComponent(params.source)}` : ""
      }`
    ),
  alarmRules: () => request<AlarmRuleListResponse>("/alarms/rules"),
  updateAlarmRule: (
    id: number,
    payload: { threshold: string; hold_seconds: number; level: string; enabled: boolean }
  ) => request<AlarmRuleUpdateResponse>(`/alarms/rules/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  storageRules: () => request<StorageRuleListResponse>("/storage-rules"),
  createStorageRule: (payload: Record<string, unknown>) =>
    request<StorageRuleMutationResponse>("/storage-rules", { method: "POST", body: JSON.stringify(payload) }),
  updateStorageRule: (id: number, payload: Record<string, unknown>) =>
    request<StorageRuleMutationResponse>(`/storage-rules/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteStorageRule: (id: number) => request<{ ok: boolean }>(`/storage-rules/${id}`, { method: "DELETE" }),
  summaryList: (params: { page?: number; page_size?: number; q?: string; device_id?: number } = {}) =>
    request<SummaryListResponse>(
      `/history/summaries?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}&q=${encodeURIComponent(
        params.q ?? ""
      )}${params.device_id ? `&device_id=${params.device_id}` : ""}`
    ),
  summaryDetail: (id: number) => request<SummaryDetailResponse>(`/history/summaries/${id}`),
};
