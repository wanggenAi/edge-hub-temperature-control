import type {
  AIRecommendation,
  Alarm,
  AlarmHistoryResponse,
  AlarmListResponse,
  AlarmRuleListResponse,
  AlarmRuleUpdateResponse,
  ActiveAlarmResponse,
  Device,
  Me,
  Metric,
  PagedDevices,
  Parameter,
  SummaryDetailResponse,
  SummaryListResponse,
  UserItem,
} from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 12000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (init?.headers && !Array.isArray(init.headers)) {
    Object.assign(headers, init.headers as Record<string, string>);
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
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
  metrics: (id: number) => request<Metric[]>(`/devices/${id}/metrics`),
  parameters: (id: number) => request<Parameter>(`/devices/${id}/parameters`),
  updateParameters: (id: number, payload: Partial<Parameter>) =>
    request<Parameter>(`/devices/${id}/parameters`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  alarms: (id: number) => request<Alarm[]>(`/devices/${id}/alarms`),
  aiRecommendation: (id: number) => request<AIRecommendation>(`/devices/${id}/ai-recommendation`),
  users: () => request<UserItem[]>("/users"),
  createUser: (payload: { username: string; email: string; password: string; roles: string[] }) =>
    request<UserItem>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: Record<string, unknown>) =>
    request<UserItem>(`/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteUser: (id: number) => request<{ ok: boolean }>(`/users/${id}`, { method: "DELETE" }),
  acknowledgeAlarm: (deviceId: number, alarmId: number) =>
    request<{ ok: boolean }>(`/devices/${deviceId}/alarms/${alarmId}/ack`, { method: "POST" }),
  applyAiRecommendation: (deviceId: number) =>
    request<Parameter>(`/devices/${deviceId}/ai-recommendation/apply`, { method: "POST" }),
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
  summaryList: (params: { page?: number; page_size?: number; q?: string; device_id?: number } = {}) =>
    request<SummaryListResponse>(
      `/history/summaries?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}&q=${encodeURIComponent(
        params.q ?? ""
      )}${params.device_id ? `&device_id=${params.device_id}` : ""}`
    ),
  summaryDetail: (id: number) => request<SummaryDetailResponse>(`/history/summaries/${id}`),
};
