import { useCallback, useEffect, useState } from "react";

import { api, buildDeviceStreamUrl } from "@/lib/api";
import type {
  AIRecommendation,
  Alarm,
  AlarmListItem,
  AlarmRuleItem,
  ActiveAlarmItem,
  AlarmHistoryItem,
  Device,
  Metric,
  Parameter,
  SummaryDetailResponse,
  SummaryItem,
  UserItem,
} from "@/types";

type DeviceSnapshot = Device & { snapshot_ts?: string | null };
type DeviceStreamMessage = {
  type: "device_snapshot";
  emitted_at: string;
  devices: DeviceSnapshot[];
};

function isDeviceStreamMessage(value: unknown): value is DeviceStreamMessage {
  if (!value || typeof value !== "object") return false;
  const msg = value as Partial<DeviceStreamMessage>;
  return msg.type === "device_snapshot" && Array.isArray(msg.devices);
}

export function useDevices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    api.devices().then(setDevices).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, []);

  useEffect(reload, [reload]);

  useEffect(() => {
    let closed = false;
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;

    const connect = () => {
      const wsUrl = buildDeviceStreamUrl();
      if (!wsUrl) return;
      socket = new WebSocket(wsUrl);
      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as unknown;
          if (!isDeviceStreamMessage(parsed)) return;
          setDevices(parsed.devices);
          setError(null);
          setLoading(false);
        } catch {
          // ignore malformed event and keep stream alive
        }
      };
      socket.onclose = () => {
        if (closed) return;
        reconnectTimer = window.setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      reload();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [reload]);

  return { devices, loading, error, reload };
}

export function useDeviceDetail(deviceId: number) {
  const [device, setDevice] = useState<Device | null>(null);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [parameters, setParameters] = useState<Parameter | null>(null);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [recommendation, setRecommendation] = useState<AIRecommendation | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    if (!deviceId) return;
    setLoading(true);
    Promise.all([
      api.device(deviceId),
      api.metrics(deviceId),
      api.parameters(deviceId),
      api.alarms(deviceId),
      api.aiRecommendation(deviceId).catch(() => null),
    ])
      .then(([d, m, p, a, r]) => {
        setDevice(d);
        setMetrics(m);
        setParameters(p);
        setAlarms(a);
        setRecommendation(r);
      })
      .finally(() => setLoading(false));
  }, [deviceId]);

  useEffect(reload, [reload]);

  useEffect(() => {
    if (!deviceId) return;
    let closed = false;
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;

    const connect = () => {
      const wsUrl = buildDeviceStreamUrl(deviceId);
      if (!wsUrl) return;
      socket = new WebSocket(wsUrl);
      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as unknown;
          if (!isDeviceStreamMessage(parsed) || parsed.devices.length === 0) return;
          const snapshot = parsed.devices[0];
          setDevice(snapshot);
          setMetrics((prev) => {
            const metricTs = snapshot.snapshot_ts ?? parsed.emitted_at;
            const nextMetric: Metric = {
              id: prev.length > 0 ? prev[prev.length - 1].id + 1 : 1,
              timestamp: metricTs,
              current_temp: snapshot.current_temp,
              target_temp: snapshot.target_temp,
              error: snapshot.current_temp - snapshot.target_temp,
              pwm_output: snapshot.pwm_output,
              status: "active",
              in_spec: Math.abs(snapshot.current_temp - snapshot.target_temp) <= 0.5,
              is_alarm: snapshot.is_alarm,
            };
            const last = prev[prev.length - 1];
            if (
              last &&
              last.timestamp === nextMetric.timestamp &&
              last.current_temp === nextMetric.current_temp &&
              last.target_temp === nextMetric.target_temp &&
              last.pwm_output === nextMetric.pwm_output &&
              last.is_alarm === nextMetric.is_alarm
            ) {
              return prev;
            }
            return [...prev, nextMetric].slice(-1000);
          });
          setLoading(false);
        } catch {
          // ignore malformed event and keep stream alive
        }
      };
      socket.onclose = () => {
        if (closed) return;
        reconnectTimer = window.setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [deviceId]);

  useEffect(() => {
    if (!deviceId) return;
    const timer = window.setInterval(() => {
      reload();
    }, 20000);
    return () => window.clearInterval(timer);
  }, [deviceId, reload]);

  return {
    device,
    metrics,
    parameters,
    alarms,
    recommendation,
    loading,
    reload,
    updateParameters: (payload: Partial<Parameter>) => api.updateParameters(deviceId, payload),
    acknowledgeAlarm: (alarmId: number) => api.acknowledgeAlarm(deviceId, alarmId),
    applyAiRecommendation: () => api.applyAiRecommendation(deviceId),
  };
}

export function useUsers() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    api.users().then(setUsers).finally(() => setLoading(false));
  }, []);

  useEffect(reload, [reload]);

  return {
    users,
    loading,
    reload,
    createUser: api.createUser,
    updateUser: api.updateUser,
    deleteUser: api.deleteUser,
  };
}

export function useDeviceManage(initialPage = 1) {
  const [items, setItems] = useState<Device[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(10);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    api
      .devicesManage({ page, page_size: pageSize, q })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [page, pageSize, q]);

  useEffect(reload, [reload]);

  return {
    items,
    total,
    page,
    pageSize,
    q,
    loading,
    setPage,
    setPageSize,
    setQ,
    reload,
    createDevice: api.createDevice,
    updateDevice: api.updateDevice,
    deleteDevice: api.deleteDevice,
  };
}

export function useAlarmCenter(initialPage = 1) {
  const [items, setItems] = useState<AlarmListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(20);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    api
      .alarmCenter({ page, page_size: pageSize, q })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [page, pageSize, q]);

  useEffect(reload, [reload]);

  return { items, total, page, pageSize, q, loading, setPage, setPageSize, setQ, reload };
}

export function useAlarmsHmi() {
  const [activeItems, setActiveItems] = useState<ActiveAlarmItem[]>([]);
  const [activeTotal, setActiveTotal] = useState(0);
  const [activeStats, setActiveStats] = useState({ active_total: 0, critical: 0, warning: 0 });
  const [activePage, setActivePage] = useState(1);
  const [activePageSize, setActivePageSize] = useState(20);
  const [activeStatus, setActiveStatus] = useState<"active" | "all">("active");
  const [activeQ, setActiveQ] = useState("");

  const [historyItems, setHistoryItems] = useState<AlarmHistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(20);
  const [historyQ, setHistoryQ] = useState("");
  const [historyRange, setHistoryRange] = useState<"24h" | "7d">("24h");
  const [historySeverity, setHistorySeverity] = useState<string | undefined>(undefined);
  const [historyType, setHistoryType] = useState<string | undefined>(undefined);
  const [historySource, setHistorySource] = useState<string | undefined>(undefined);

  const [rules, setRules] = useState<AlarmRuleItem[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.alarmsActive({
        page: activePage,
        page_size: activePageSize,
        q: activeQ,
        status: activeStatus,
      }),
      api.alarmsHistory({
        page: historyPage,
        page_size: historyPageSize,
        q: historyQ,
        range_key: historyRange,
        severity: historySeverity,
        alarm_type: historyType,
        source: historySource,
      }),
      api.alarmRules(),
    ])
      .then(([active, history, ruleRes]) => {
        setActiveItems(active.items);
        setActiveTotal(active.total);
        setActiveStats(active.stats);
        setHistoryItems(history.items);
        setHistoryTotal(history.total);
        setRules(ruleRes.items);
      })
      .finally(() => setLoading(false));
  }, [
    activePage,
    activePageSize,
    activeQ,
    activeStatus,
    historyPage,
    historyPageSize,
    historyQ,
    historyRange,
    historySeverity,
    historyType,
    historySource,
  ]);

  useEffect(reload, [reload]);

  return {
    loading,
    activeItems,
    activeTotal,
    activeStats,
    activePage,
    activePageSize,
    activeStatus,
    activeQ,
    setActivePage,
    setActivePageSize,
    setActiveStatus,
    setActiveQ,
    historyItems,
    historyTotal,
    historyPage,
    historyPageSize,
    historyQ,
    historyRange,
    historySeverity,
    historyType,
    historySource,
    setHistoryPage,
    setHistoryPageSize,
    setHistoryQ,
    setHistoryRange,
    setHistorySeverity,
    setHistoryType,
    setHistorySource,
    rules,
    reload,
    updateRule: (id: number, payload: { threshold: string; hold_seconds: number; level: string; enabled: boolean }) =>
      api.updateAlarmRule(id, payload),
  };
}

export function useSummaryHistory(initialPage = 1, initialDeviceId?: number) {
  const [items, setItems] = useState<SummaryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(20);
  const [q, setQ] = useState("");
  const [deviceId, setDeviceId] = useState<number | undefined>(initialDeviceId);
  const [selected, setSelected] = useState<SummaryDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    api
      .summaryList({ page, page_size: pageSize, q, device_id: deviceId })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [page, pageSize, q, deviceId]);

  useEffect(reload, [reload]);

  const loadDetail = useCallback(async (summaryId: number) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const detail = await api.summaryDetail(summaryId);
      setSelected(detail);
      return detail;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setDetailError(message);
      throw e;
    } finally {
      setDetailLoading(false);
    }
  }, []);

  return {
    items,
    total,
    page,
    pageSize,
    q,
    deviceId,
    selected,
    loading,
    detailLoading,
    detailError,
    setPage,
    setPageSize,
    setQ,
    setDeviceId,
    loadDetail,
    reload,
  };
}
