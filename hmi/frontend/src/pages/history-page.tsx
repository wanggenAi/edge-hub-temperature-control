import { useEffect, useMemo, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useDevices, useSummaryHistory } from "@/routes/use-data";

export function HistoryPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialDeviceId = searchParams.get("deviceId") ? Number(searchParams.get("deviceId")) : undefined;
  const initialSummaryId = searchParams.get("summaryId") ? Number(searchParams.get("summaryId")) : undefined;
  const detailRef = useRef<HTMLDivElement | null>(null);
  const { devices } = useDevices();
  const {
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
  } = useSummaryHistory(1, initialDeviceId);

  useEffect(() => {
    if (initialDeviceId && initialDeviceId !== deviceId) {
      setDeviceId(initialDeviceId);
    }
  }, [initialDeviceId, deviceId, setDeviceId]);

  useEffect(() => {
    if (!initialSummaryId || Number.isNaN(initialSummaryId)) return;
    void loadDetail(initialSummaryId);
  }, [initialSummaryId, loadDetail]);

  useEffect(() => {
    if (!selected) return;
    detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selected]);

  function openDetail(summaryId: number) {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("summaryId", String(summaryId));
    setSearchParams(nextParams);
    void loadDetail(summaryId);
  }

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize]);
  const deviceTargetMap = useMemo(() => new Map(devices.map((d) => [d.id, d.target_temp])), [devices]);
  const chartData = useMemo(
    () =>
      selected?.metrics.map((m) => ({
        t: new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        temp: m.current_temp,
        target: m.target_temp,
      })) ?? [],
    [selected]
  );
  const selectedTargetTemp = useMemo(() => {
    if (!selected) return undefined;
    return selected.metrics[0]?.target_temp ?? deviceTargetMap.get(selected.summary.device_id);
  }, [selected, deviceTargetMap]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>History Summary Windows</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="max-w-sm"
              placeholder="Search by device code/name/trigger"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
            <Select
              value={deviceId ? String(deviceId) : "all"}
              onValueChange={(v) => {
                const next = v === "all" ? undefined : Number(v);
                setDeviceId(next);
                setPage(1);
                const nextParams = new URLSearchParams(searchParams);
                if (next) nextParams.set("deviceId", String(next));
                else nextParams.delete("deviceId");
                setSearchParams(nextParams);
              }}
            >
              <SelectTrigger className="min-w-56">
                <SelectValue placeholder="Filter by device" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Devices</SelectItem>
                {devices.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                setPageSize(Number(v));
                setPage(1);
              }}
            >
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="20">20 / page</SelectItem>
                <SelectItem value="50">50 / page</SelectItem>
                <SelectItem value="100">100 / page</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="ghost" onClick={reload}>Refresh</Button>
            <span className="text-xs text-mute">Total windows: {total}</span>
          </div>

          {loading && <p className="text-sm text-mute">Loading summaries...</p>}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-mute">
                <tr>
                  <th className="py-2">Device</th>
                  <th>Window</th>
                  <th>Target Temp</th>
                  <th>Samples</th>
                  <th>Avg Error</th>
                  <th>Max Overshoot</th>
                  <th>Settling</th>
                  <th>Saturation</th>
                  <th>Trigger</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => {
                  const targetTemp = deviceTargetMap.get(s.device_id);
                  return (
                    <tr
                      key={s.id}
                      className={`cursor-pointer border-t border-line/60 hover:bg-panel2/50 ${
                        selected?.summary.id === s.id ? "bg-neon/10" : ""
                      }`}
                      onClick={() => openDetail(s.id)}
                    >
                      <td className="py-2">{s.device_code} · {s.device_name}</td>
                      <td>{new Date(s.window_start).toLocaleTimeString()} - {new Date(s.window_end).toLocaleTimeString()}</td>
                      <td className="font-semibold text-accent">
                        {typeof targetTemp === "number" ? `${targetTemp.toFixed(1)}°C` : "--"}
                      </td>
                      <td>{s.sample_count}</td>
                      <td>{s.avg_error.toFixed(3)}°C</td>
                      <td>{s.max_overshoot_pct.toFixed(2)}%</td>
                      <td>{typeof s.observed_settling_sec === "number" ? `${Math.round(s.observed_settling_sec)}s` : "N/A"}</td>
                      <td>{s.saturation_ratio.toFixed(2)}</td>
                      <td>{s.trigger_event}</td>
                      <td className="text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            openDetail(s.id);
                          }}
                        >
                          View Detail
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</Button>
            <span className="text-xs text-mute">Page {page} / {totalPages}</span>
            <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </CardContent>
      </Card>

      {detailLoading && (
        <Card>
          <CardContent className="py-4 text-sm text-mute">Loading summary detail...</CardContent>
        </Card>
      )}

      {detailError && !detailLoading && (
        <Card>
          <CardContent className="py-4 text-sm text-danger">Failed to load detail: {detailError}</CardContent>
        </Card>
      )}

      {selected && (
        <Card ref={detailRef}>
          <CardHeader>
            <CardTitle>
              Window Detail · {selected.summary.device_code} · {selected.summary.trigger_event}
            </CardTitle>
            {typeof selectedTargetTemp === "number" && (
              <div className="rounded border border-accent/60 bg-accent/10 px-3 py-1 text-right">
                <div className="text-[11px] uppercase tracking-wide text-accent/80">Target Temp</div>
                <div className="text-xl font-bold text-accent">{selectedTargetTemp.toFixed(1)}°C</div>
              </div>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-end">
              <Button size="sm" variant="ghost" onClick={() => navigate(`/devices/${selected.summary.device_id}`)}>
                Open Device Detail
              </Button>
            </div>
            <div className="grid gap-2 md:grid-cols-5 text-sm">
              <Meta label="Window Start" value={new Date(selected.summary.window_start).toLocaleString()} />
              <Meta label="Window End" value={new Date(selected.summary.window_end).toLocaleString()} />
              <Meta label="Avg Temp" value={`${selected.summary.avg_temp.toFixed(2)}°C`} />
              <Meta label="Avg Error" value={`${selected.summary.avg_error.toFixed(3)}°C`} />
              <Meta
                label="Observed Settling (Window)"
                value={typeof selected.summary.observed_settling_sec === "number" ? `${Math.round(selected.summary.observed_settling_sec)}s` : "N/A"}
              />
            </div>

            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid stroke="rgba(41,240,255,0.15)" />
                  <XAxis dataKey="t" stroke="#7fa6b8" />
                  <YAxis stroke="#7fa6b8" />
                  <Tooltip />
                  <Line type="monotone" dataKey="temp" stroke="#29f0ff" dot={false} />
                  <Line type="monotone" dataKey="target" stroke="#19d398" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-left text-mute">
                  <tr>
                    <th className="py-2">Time</th>
                    <th>Current</th>
                    <th>Target</th>
                    <th>Error</th>
                    <th>PWM</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.metrics.map((m) => (
                    <tr key={m.id} className="border-t border-line/60">
                      <td className="py-2">{new Date(m.timestamp).toLocaleTimeString()}</td>
                      <td>{m.current_temp.toFixed(2)}</td>
                      <td>{m.target_temp.toFixed(2)}</td>
                      <td>{m.error.toFixed(3)}</td>
                      <td>{m.pwm_output.toFixed(1)}%</td>
                      <td>{m.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line/70 bg-panel2 p-2">
      <div className="text-xs text-mute">{label}</div>
      <div className="text-text">{value}</div>
    </div>
  );
}
