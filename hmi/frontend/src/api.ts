import type {
  AIPageResponse,
  AckRecord,
  DeleteResult,
  DevicePageResponse,
  DeviceStatsResponse,
  DeviceSummary,
  DeviceUpsertRequest,
  HistoryResponse,
  LoginResponse,
  ControlGoalsConfig,
  ManagedUser,
  OverviewResponse,
  ParameterCommandRequest,
  ParameterPageResponse,
  RealtimeSeriesResponse,
  RoleDefinition,
  RoleUpsertRequest,
  SystemAccessResponse,
  TelemetrySnapshot,
  UserPublic,
  UserUpsertRequest,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

function withQuery(path: string, query?: Record<string, string | number | undefined | null>) {
  if (!query) return path;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    params.set(key, String(value));
  });
  const queryString = params.toString();
  if (!queryString) return path;
  return `${path}?${queryString}`;
}

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
  getDevices() {
    return request<DeviceSummary[]>("/devices");
  },
  getManagedDevices(page: number, pageSize: number, q?: string) {
    return request<DevicePageResponse>(withQuery("/devices/managed", { page, page_size: pageSize, q }))
      .then((response) => ({
        ...response,
        items: dedupeDeviceItems(response.items),
      }));
  },
  getDeviceStats() {
    return request<DeviceStatsResponse>("/devices/stats");
  },
  createDevice(payload: DeviceUpsertRequest) {
    return request<DeviceSummary>("/devices", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateDevice(deviceId: string, payload: DeviceUpsertRequest) {
    return request<DeviceSummary>(`/devices/${encodeURIComponent(deviceId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  deleteDevice(deviceId: string) {
    return request<DeleteResult>(`/devices/${encodeURIComponent(deviceId)}`, {
      method: "DELETE",
    });
  },
  getOverview(deviceId?: string) {
    return request<OverviewResponse>(withQuery("/overview", { device_id: deviceId }));
  },
  getRealtimeSnapshot(deviceId?: string) {
    return request<TelemetrySnapshot>(withQuery("/realtime/snapshot", { device_id: deviceId }));
  },
  getRealtimeSeries(deviceId?: string) {
    return request<RealtimeSeriesResponse>(withQuery("/realtime/series", { device_id: deviceId }));
  },
  getHistory(deviceId?: string) {
    return request<HistoryResponse>(withQuery("/history", { device_id: deviceId }));
  },
  getParameters(deviceId?: string) {
    return request<ParameterPageResponse>(withQuery("/params", { device_id: deviceId }));
  },
  submitParameters(payload: ParameterCommandRequest) {
    return request<AckRecord>("/params/commands", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getRecommendations(deviceId?: string) {
    return request<AIPageResponse>(withQuery("/ai/recommendations", { device_id: deviceId }));
  },
  getSystemAccess() {
    return request<SystemAccessResponse>("/system/access");
  },
  saveUser(payload: UserUpsertRequest) {
    return request<ManagedUser>("/system/users", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  deleteUser(username: string) {
    return request<DeleteResult>(`/system/users/${encodeURIComponent(username)}`, {
      method: "DELETE",
    });
  },
  saveRole(payload: RoleUpsertRequest) {
    return request<RoleDefinition>("/system/roles", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getControlGoals() {
    return request<ControlGoalsConfig>("/system/control-goals");
  },
  updateControlGoals(payload: ControlGoalsConfig) {
    return request<ControlGoalsConfig>("/system/control-goals", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
};

function dedupeDeviceItems(items: DeviceSummary[]) {
  const seen = new Set<string>();
  const result: DeviceSummary[] = [];
  for (const item of items) {
    const key = item.device_id.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}
