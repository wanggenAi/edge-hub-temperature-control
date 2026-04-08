import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { OpsOverview } from "@/types";

export function OpsPage() {
  const [data, setData] = useState<OpsOverview | null>(null);
  const [runtimeHistory, setRuntimeHistory] = useState<
    Array<{
      ts: string;
      heapUsedMb: number | null;
      heapMaxMb: number | null;
      nonHeapMb: number | null;
      gcCount: number | null;
      gcPauseMs: number | null;
      gcPauseMaxMs: number | null;
    }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const generatedAtText = useMemo(() => (data ? new Date(data.as_of).toLocaleString() : "-"), [data]);
  const dataHubChartRows = useMemo(
    () =>
      (data?.data_hub.trend ?? []).map((p) => ({
        ...p,
        time: shortTime(p.ts),
      })),
    [data]
  );

  const jvmChartRows = useMemo(
    () =>
      runtimeHistory.map((p, idx) => {
        const prev = idx > 0 ? runtimeHistory[idx - 1] : null;
        const nowMs = new Date(p.ts).getTime();
        const prevMs = prev ? new Date(prev.ts).getTime() : NaN;
        const deltaSec = Number.isFinite(nowMs) && Number.isFinite(prevMs) ? Math.max(1, (nowMs - prevMs) / 1000) : null;
        const gcCountDelta =
          prev && p.gcCount != null && prev.gcCount != null ? Math.max(0, p.gcCount - prev.gcCount) : null;
        const gcPauseDeltaMs =
          prev && p.gcPauseMs != null && prev.gcPauseMs != null ? Math.max(0, p.gcPauseMs - prev.gcPauseMs) : null;
        const gcPauseDeltaPerMinMs =
          gcPauseDeltaMs != null && deltaSec != null ? (gcPauseDeltaMs / deltaSec) * 60.0 : null;
        return {
          ...p,
          time: shortTime(p.ts),
          heapUsedPct:
            p.heapUsedMb != null && p.heapMaxMb != null && p.heapMaxMb > 0
              ? (p.heapUsedMb / p.heapMaxMb) * 100
              : null,
          gcCountDelta,
          gcPauseDeltaPerMinMs,
        };
      }),
    [runtimeHistory]
  );

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);
    try {
      const res = await api.opsOverview();
      setData(res);
      setRuntimeHistory((prev) => {
        const next = [
          ...prev,
          {
            ts: res.as_of,
            heapUsedMb: res.runtime.jvm_heap_used_mb ?? null,
            heapMaxMb: res.runtime.jvm_heap_max_mb ?? null,
            nonHeapMb: res.runtime.jvm_non_heap_used_mb ?? null,
            gcCount: res.runtime.jvm_gc_count ?? null,
            gcPauseMs: res.runtime.jvm_gc_pause_ms ?? null,
            gcPauseMaxMs: res.runtime.jvm_gc_pause_max_ms ?? null,
          },
        ];
        return next.slice(-120);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void load(true);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  if (loading) return <p className="text-sm text-mute">Loading Ops Console...</p>;
  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-mute">No ops data available.</p>;

  const { data_hub: hub, runtime, learning_loop: loop, models } = data;
  const dataHubCpuDisplay =
    hub.data_hub_cpu_usage_pct != null
      ? `${hub.data_hub_cpu_usage_pct.toFixed(1)}%`
      : runtime.process_cpu_usage_pct != null
        ? `${runtime.process_cpu_usage_pct.toFixed(1)}% (fallback)`
        : "N/A";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Developer Ops Console</CardTitle>
            <div className="mt-1 text-xs text-mute">
              Last refreshed: {generatedAtText} · Separate from device alarms/end-user views
            </div>
          </div>
          <Button variant="ghost" onClick={() => load(true)} disabled={refreshing}>
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Data Hub / MQTT / Ingestion</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
            <Stat title="MQTT Ingress TPS" value={fmtNum(hub.mqtt_ingress_tps)} />
            <Stat title="Consume TPS" value={fmtNum(hub.data_hub_consume_tps)} />
            <Stat
              title="Data Hub CPU"
              value={dataHubCpuDisplay}
            />
            <Stat title="Queue Depth" value={fmtInt(hub.queue_depth)} />
          </div>
          <div className="text-xs text-mute break-all">
            Source: {hub.source} · Available: {hub.available ? "Yes" : "No"} · Interval: {fmtNum(hub.interval_seconds)}s
          </div>
          <div className="rounded border border-line/70 bg-panel2/50 p-3 text-xs text-mute">
            Source Mapping:
            `Ingress TPS = mqtt[mqtt_received_delta] / interval`, `Consume TPS = accounting[accounted_delta] / interval`,
            `Queue Depth = buffer[current_buffer_size]`, `Data Hub CPU = process_cpu_usage/system_cpu_usage`.
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <OpsLineChart
              title="Ingress vs Consume TPS"
              data={dataHubChartRows}
              series={[
                { key: "mqtt_ingress_tps", name: "Ingress TPS", color: "#22d3ee" },
                { key: "consume_tps", name: "Consume TPS", color: "#34d399" },
              ]}
            />
            <OpsLineChart
              title="Queue Depth"
              data={dataHubChartRows}
              series={[{ key: "queue_depth", name: "Queue", color: "#60a5fa" }]}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>JVM Runtime (Memory / GC)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-mute">
            <Badge className="border-line text-mute">JVM Metrics: {runtime.jvm_metrics_available ? "Connected" : "Not Connected (MVP)"}</Badge>
            <Badge className="border-line text-mute">Runtime Metrics Source: {runtime.source}</Badge>
            <span>Auto refresh: 15s</span>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            <Stat title="JVM Heap Used" value={runtime.jvm_heap_used_mb == null ? "N/A" : `${runtime.jvm_heap_used_mb.toFixed(1)} MB`} />
            <Stat title="JVM Heap Max" value={runtime.jvm_heap_max_mb == null ? "N/A" : `${runtime.jvm_heap_max_mb.toFixed(1)} MB`} />
            <Stat title="JVM Non-Heap" value={runtime.jvm_non_heap_used_mb == null ? "N/A" : `${runtime.jvm_non_heap_used_mb.toFixed(1)} MB`} />
            <Stat title="JVM GC Count" value={fmtInt(runtime.jvm_gc_count)} />
            <Stat title="GC Pause Δ (1m est.)" value={fmtGcPausePerMin(jvmChartRows)} />
            <Stat title="GC Pause Max (single)" value={runtime.jvm_gc_pause_max_ms == null ? "N/A" : `${runtime.jvm_gc_pause_max_ms.toFixed(1)} ms`} />
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <OpsLineChart
              title="Heap Used (%) Trend"
              data={jvmChartRows}
              series={[{ key: "heapUsedPct", name: "Heap Used %", color: "#22d3ee" }]}
              yDomain={[0, 100]}
              yFormatter={(v) => `${Number(v).toFixed(0)}%`}
            />
            <OpsLineChart
              title="GC Pressure Trend"
              data={jvmChartRows}
              series={[
                { key: "gcCountDelta", name: "GC Count Δ", color: "#34d399" },
                { key: "gcPauseDeltaPerMinMs", name: "GC Pause Δ / min (ms)", color: "#f59e0b" },
                { key: "gcPauseMaxMs", name: "GC Pause Max (ms)", color: "#fb7185" },
              ]}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>AI Learning Loop</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-3 lg:grid-cols-6">
            <Stat title="Pending Overdue" value={fmtInt(loop.pending_overdue)} tone={toneByCount(loop.pending_overdue)} />
            <Stat title="Worker Processed 24h" value={fmtInt(loop.worker_processed_24h)} />
            <Stat title="Eligible Samples" value={fmtInt(loop.training_eligible_total)} />
            <Stat title="Eligible 7d" value={fmtInt(loop.training_eligible_7d)} />
            <Stat title="Retry Pending" value={fmtInt(loop.eval_jobs_by_status.retry_pending)} tone={toneByCount(loop.eval_jobs_by_status.retry_pending)} />
            <Stat title="Terminal Insufficient" value={fmtInt(loop.eval_jobs_by_status.terminal_insufficient)} tone={toneByCount(loop.eval_jobs_by_status.terminal_insufficient)} />
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <KeyCountList title="Control Action Source (Total)" rows={loop.control_actions_by_source_total} />
            <KeyCountList title="Control Action Source (24h)" rows={loop.control_actions_by_source_24h} />
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            <KeyCountList
              title="Eval Job Status"
              rows={[
                { key: "pending", count: loop.eval_jobs_by_status.pending },
                { key: "running", count: loop.eval_jobs_by_status.running },
                { key: "done", count: loop.eval_jobs_by_status.done },
                { key: "retry_pending", count: loop.eval_jobs_by_status.retry_pending },
                { key: "terminal_insufficient", count: loop.eval_jobs_by_status.terminal_insufficient },
                { key: "failed", count: loop.eval_jobs_by_status.failed },
              ]}
            />
            <KeyCountList title="Sample Quality" rows={loop.sample_quality_distribution} />
            <KeyCountList title="Actual Effect" rows={loop.actual_effect_distribution} />
          </div>
          <RecentJobsTable rows={loop.recent_jobs} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model / Runtime Health</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-6">
            <Stat title="Active Model" value={models.active_model_version || "N/A"} />
            <Stat title="Candidate Model" value={models.candidate_model_version || "N/A"} />
            <Stat title="Fallback Ratio" value={models.fallback_ratio == null ? "N/A" : `${(models.fallback_ratio * 100).toFixed(1)}%`} />
            <Stat title="Generated 24h" value={fmtInt(models.recommendation_generated_24h)} />
            <Stat title="Applied 24h" value={fmtInt(models.recommendation_applied_24h)} />
            <Stat title="Archived Artifacts" value={fmtInt(models.archived_model_artifact_count)} />
          </div>
          <div className="text-xs text-mute">
            Last trained: {fmtDate(models.last_trained_at)} · Last promoted: {fmtDate(models.last_promoted_at)}
          </div>
          <KeyCountList title="Runtime Source Breakdown" rows={models.runtime_source_breakdown} />
          {models.notes.length > 0 && (
            <div className="rounded border border-warning/50 bg-warning/10 p-3 text-xs text-warning">
              {models.notes.map((n) => (
                <div key={n}>{n}</div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ title, value, tone }: { title: string; value: string; tone?: "normal" | "warning" | "critical" }) {
  const cls = tone === "critical" ? "text-danger" : tone === "warning" ? "text-warning" : "text-text";
  return (
    <div className="rounded border border-line/70 bg-panel2/60 p-2">
      <div className="text-[11px] uppercase tracking-wide text-mute">{title}</div>
      <div className={`mt-1 text-sm font-semibold break-all ${cls}`}>{value}</div>
    </div>
  );
}

function KeyCountList({ title, rows }: { title: string; rows: Array<{ key: string; count: number }> }) {
  return (
    <div className="rounded border border-line/70 bg-panel2/50 p-3">
      <div className="mb-2 text-xs uppercase tracking-wide text-neon">{title}</div>
      {rows.length === 0 ? (
        <div className="text-xs text-mute">No data.</div>
      ) : (
        <div className="space-y-1 text-sm">
          {rows.map((r) => (
            <div key={r.key} className="flex items-center justify-between gap-2">
              <span className="text-mute break-all">{r.key}</span>
              <span className="font-semibold text-text">{r.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OpsLineChart({
  title,
  data,
  series,
  yDomain,
  yFormatter,
}: {
  title: string;
  data: Array<Record<string, unknown>>;
  series: Array<{ key: string; name: string; color: string }>;
  yDomain?: [number, number];
  yFormatter?: (value: number | string) => string;
}) {
  return (
    <div className="rounded border border-line/70 bg-panel2/50 p-3">
      <div className="mb-2 text-xs uppercase tracking-wide text-neon">{title}</div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.18)" />
            <XAxis dataKey="time" tick={{ fill: "rgb(148 163 184)", fontSize: 11 }} minTickGap={18} />
            <YAxis
              tick={{ fill: "rgb(148 163 184)", fontSize: 11 }}
              width={46}
              domain={yDomain}
              tickFormatter={yFormatter}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "rgb(7 31 44)", border: "1px solid rgba(34,211,238,0.25)", color: "rgb(226 232 240)" }}
              labelStyle={{ color: "rgb(148 163 184)" }}
              formatter={(value: number | string) => (yFormatter ? yFormatter(value) : value)}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: "rgb(148 163 184)" }} />
            {series.map((s) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RecentJobsTable({
  rows,
}: {
  rows: Array<{ job_id: number; control_action_id: number; device_id: number; source: string; status: string; attempt_count: number; scheduled_at: string; updated_at: string; last_error?: string | null }>;
}) {
  return (
    <div className="rounded border border-line/70 bg-panel2/50 p-3">
      <div className="mb-2 text-xs uppercase tracking-wide text-neon">Recent Eval Jobs</div>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-mute">
            <tr>
              <th className="py-1">Job</th>
              <th>Action</th>
              <th>Device</th>
              <th>Source</th>
              <th>Status</th>
              <th>Retry</th>
              <th>Updated</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.job_id} className="border-t border-line/50">
                <td className="py-1">{r.job_id}</td>
                <td>{r.control_action_id}</td>
                <td>{r.device_id}</td>
                <td>{r.source}</td>
                <td>{r.status}</td>
                <td>{r.attempt_count}</td>
                <td>{fmtDate(r.updated_at)}</td>
                <td className="max-w-[280px] truncate">{r.last_error || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function fmtNum(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "N/A";
  return Number(v).toFixed(2);
}

function fmtInt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "N/A";
  return String(Math.round(v));
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return "N/A";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString();
}

function shortTime(v: string | null | undefined): string {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtGcPausePerMin(
  rows: Array<{
    gcPauseDeltaPerMinMs?: number | null;
  }>
): string {
  const last = rows.length > 0 ? rows[rows.length - 1] : null;
  const value = last?.gcPauseDeltaPerMinMs;
  if (value == null || Number.isNaN(value)) return "N/A";
  return `${Number(value).toFixed(1)} ms/min`;
}

function toneByCount(v: number | null | undefined): "normal" | "warning" | "critical" {
  const n = Number(v ?? 0);
  if (n <= 0) return "normal";
  if (n <= 10) return "warning";
  return "critical";
}
