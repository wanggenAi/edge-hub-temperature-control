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
  StorageRuleItem,
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

const DETAIL_METRICS_WINDOW_MS = 5 * 60 * 1000;
const DETAIL_METRICS_LIMIT = 20000;
const DETAIL_STREAM_WINDOW_MS = 5 * 60 * 1000;
const METRIC_VALUE_EPSILON = 0.000001;

function isDeviceStreamMessage(value: unknown): value is DeviceStreamMessage {
  if (!value || typeof value !== "object") return false;
  const msg = value as Partial<DeviceStreamMessage>;
  return msg.type === "device_snapshot" && Array.isArray(msg.devices);
}

function calcErrorC(targetTemp: number, currentTemp: number): number {
  return targetTemp - currentTemp;
}

function metricTimestampMs(metric: Pick<Metric, "timestamp">): number {
  return new Date(metric.timestamp).getTime();
}

function isValidMetricTimestamp(metric: Pick<Metric, "timestamp">): boolean {
  return Number.isFinite(metricTimestampMs(metric));
}

function numbersClose(left: number, right: number): boolean {
  return Math.abs(left - right) <= METRIC_VALUE_EPSILON;
}

function sameMetricValues(left: Metric, right: Metric): boolean {
  return (
    left.timestamp === right.timestamp &&
    numbersClose(left.current_temp, right.current_temp) &&
    numbersClose(left.target_temp, right.target_temp) &&
    numbersClose(left.pwm_output, right.pwm_output) &&
    left.is_alarm === right.is_alarm
  );
}

function normalizeMetrics(rows: Metric[], limit = DETAIL_METRICS_LIMIT): Metric[] {
  const byTime = new Map<number, Metric>();
  for (const row of rows) {
    const ts = metricTimestampMs(row);
    if (!Number.isFinite(ts)) continue;
    byTime.set(ts, row);
  }
  const sorted = Array.from(byTime.values()).sort((a, b) => metricTimestampMs(a) - metricTimestampMs(b));
  return sorted.slice(-limit);
}

function mergeLiveMetric(prev: Metric[], nextMetric: Metric): Metric[] {
  if (!isValidMetricTimestamp(nextMetric)) return prev;
  const latestSeenMs = Math.max(
    metricTimestampMs(nextMetric),
    ...prev.map(metricTimestampMs).filter((value) => Number.isFinite(value))
  );
  const cutoffMs = latestSeenMs - DETAIL_STREAM_WINDOW_MS;
  const recent = prev.filter((metric) => {
    const ts = metricTimestampMs(metric);
    return Number.isFinite(ts) && ts >= cutoffMs;
  });
  const existing = recent.find((metric) => metricTimestampMs(metric) === metricTimestampMs(nextMetric));
  if (existing && sameMetricValues(existing, nextMetric)) {
    return normalizeMetrics(recent);
  }
  return normalizeMetrics(
    [...recent.filter((metric) => metricTimestampMs(metric) !== metricTimestampMs(nextMetric)), nextMetric],
    DETAIL_METRICS_LIMIT
  );
}

export function useDevices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback((opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false;
    if (!silent) setLoading(true);
    api
      .devices()
      .then((rows) => {
        setDevices(rows);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => {
        if (!silent) setLoading(false);
      });
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

  // Keep hook order stable during fast-refresh while polling is intentionally disabled.
  useEffect(() => {}, []);

  return { devices, loading, error, reload };
}

export function useDeviceDetail(deviceId: number) {
  const [device, setDevice] = useState<Device | null>(null);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [parameters, setParameters] = useState<Parameter | null>(null);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [recommendation, setRecommendation] = useState<AIRecommendation | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback((opts?: { silent?: boolean }) => {
    if (!deviceId) return;
    const silent = opts?.silent ?? false;
    if (!silent) setLoading(true);
    const endMs = Date.now();
    const startMs = endMs - DETAIL_METRICS_WINDOW_MS;
    api
      .device(deviceId)
      .then(async (d) => {
        const [m, p, a, r] = await Promise.all([
          api.metrics(deviceId, { start_ms: startMs, end_ms: endMs, limit: DETAIL_METRICS_LIMIT }).catch(() => [] as Metric[]),
          api.parameters(deviceId).catch(() => null as Parameter | null),
          api.alarms(deviceId).catch(() => [] as Alarm[]),
          api.aiRecommendation(deviceId).catch(() => null),
        ]);
        setDevice(d);
        setMetrics(normalizeMetrics(m));
        if (p) setParameters(p);
        setAlarms(a);
        setRecommendation(r);
      })
      .catch(() => {
        if (!silent) setDevice(null);
      })
      .finally(() => {
        if (!silent) setLoading(false);
      });
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
          const metricTs = snapshot.snapshot_ts;
          if (metricTs) {
            setMetrics((prev) => {
              const error = calcErrorC(snapshot.target_temp, snapshot.current_temp);
              const nextMetric: Metric = {
                id: prev.length > 0 ? prev[prev.length - 1].id + 1 : 1,
                timestamp: metricTs,
                current_temp: snapshot.current_temp,
                target_temp: snapshot.target_temp,
                error,
                pwm_output: snapshot.pwm_output,
                status: "active",
                in_spec: Math.abs(error) <= 0.5,
                is_alarm: snapshot.is_alarm,
              };
              return mergeLiveMetric(prev, nextMetric);
            });
          }
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

  // Keep hook order stable during fast-refresh while polling is intentionally disabled.
  useEffect(() => {}, [deviceId]);

  return {
    device,
    metrics,
    parameters,
    alarms,
    recommendation,
    loading,
    reload,
    updateParameters: (payload: Partial<Parameter> & { target_temp?: number }) => api.updateParameters(deviceId, payload),
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

export function useAlarmsHmi(initialQ = "") {
  const [activeItems, setActiveItems] = useState<ActiveAlarmItem[]>([]);
  const [activeTotal, setActiveTotal] = useState(0);
  const [activeStats, setActiveStats] = useState({ active_total: 0, critical: 0, warning: 0 });
  const [activePage, setActivePage] = useState(1);
  const [activePageSize, setActivePageSize] = useState(20);
  const [activeStatus, setActiveStatus] = useState<"active" | "all">("active");
  const [activeQ, setActiveQ] = useState(initialQ);

  const [historyItems, setHistoryItems] = useState<AlarmHistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(20);
  const [historyQ, setHistoryQ] = useState(initialQ);
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

export function useStorageRules() {
  const [items, setItems] = useState<StorageRuleItem[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    api
      .storageRules()
      .then((res) => setItems(res.items))
      .finally(() => setLoading(false));
  }, []);

  useEffect(reload, [reload]);

  return {
    items,
    loading,
    reload,
    createRule: (payload: Record<string, unknown>) => api.createStorageRule(payload),
    updateRule: (id: number, payload: Record<string, unknown>) => api.updateStorageRule(id, payload),
    deleteRule: (id: number) => api.deleteStorageRule(id),
  };
}
