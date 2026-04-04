import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  AIRecommendation,
  Alarm,
  AlarmListItem,
  Device,
  Metric,
  Parameter,
  SummaryDetailResponse,
  SummaryItem,
  UserItem,
} from "@/types";

export function useDevices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    api.devices().then(setDevices).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, []);

  useEffect(reload, [reload]);

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
