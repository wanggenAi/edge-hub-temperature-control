import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { AI_OPS_RUNBOOK_REGISTRY, type RunbookModuleKey } from "@/runbooks/ai-ops/registry";
import type { OpsAiModelEvaluation, OpsAiObservability, OpsOverview } from "@/types";

export function OpsPage() {
  const [activeTab, setActiveTab] = useState<"platform" | "ai">(() => {
    if (typeof window === "undefined") return "platform";
    const tab = new URLSearchParams(window.location.search).get("tab");
    return tab === "ai" ? "ai" : "platform";
  });
  const [data, setData] = useState<OpsOverview | null>(null);
  const [aiObs, setAiObs] = useState<OpsAiObservability | null>(null);
  const [aiObsLoading, setAiObsLoading] = useState(false);
  const [aiObsError, setAiObsError] = useState<string | null>(null);
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

  const loadAiObservability = useCallback(async (silent = false) => {
    if (!silent) setAiObsLoading(true);
    setAiObsError(null);
    try {
      const res = await api.opsAiObservability();
      setAiObs(res);
    } catch (e) {
      setAiObsError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiObsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void load(true);
      if (activeTab === "ai") {
        void loadAiObservability(true);
      }
    }, 15000);
    return () => window.clearInterval(timer);
  }, [activeTab, load, loadAiObservability]);

  useEffect(() => {
    if (activeTab === "ai" && !aiObs && !aiObsLoading) {
      void loadAiObservability();
    }
  }, [activeTab, aiObs, aiObsLoading, loadAiObservability]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (activeTab === "platform") {
      url.searchParams.delete("tab");
    } else {
      url.searchParams.set("tab", activeTab);
    }
    window.history.replaceState({}, "", url.toString());
  }, [activeTab]);

  if (loading) return <p className="text-sm text-mute">Loading Ops Console...</p>;
  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-mute">No ops data available.</p>;

  const { data_hub: hub, runtime } = data;
  const dataHubCpuDisplay =
    hub.data_hub_cpu_usage_pct != null
      ? fmtCpuPct(hub.data_hub_cpu_usage_pct)
      : runtime.process_cpu_usage_pct != null
        ? `${fmtCpuPct(runtime.process_cpu_usage_pct)} (fallback)`
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
          <Button
            variant="ghost"
            onClick={() => {
              void load(true);
              if (activeTab === "ai") {
                void loadAiObservability(true);
              }
            }}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <div className="text-xs uppercase tracking-wide text-mute">Ops Views</div>
        </CardHeader>
        <CardContent>
          <div role="tablist" aria-label="Ops sections" className="flex flex-wrap gap-2">
            <TabButton
              active={activeTab === "platform"}
              onClick={() => setActiveTab("platform")}
              label="Platform"
              id="ops-tab-platform"
              controls="ops-panel-platform"
            />
            <TabButton
              active={activeTab === "ai"}
              onClick={() => setActiveTab("ai")}
              label="AI"
              id="ops-tab-ai"
              controls="ops-panel-ai"
            />
          </div>
        </CardContent>
      </Card>

      {activeTab === "platform" && (
        <div id="ops-panel-platform" role="tabpanel" aria-labelledby="ops-tab-platform" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Data Hub / MQTT / Ingestion</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
                <Stat title="MQTT Ingress TPS" value={fmtNum(hub.mqtt_ingress_tps)} />
                <Stat title="Consume TPS" value={fmtNum(hub.data_hub_consume_tps)} />
                <Stat title="Data Hub CPU" value={dataHubCpuDisplay} />
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
        </div>
      )}

      {activeTab === "ai" && (
        <div id="ops-panel-ai" role="tabpanel" aria-labelledby="ops-tab-ai" className="space-y-4">
          {aiObsLoading && !aiObs ? <p className="text-sm text-mute">Loading AI observability...</p> : null}
          {aiObsError ? <p className="text-sm text-danger">{aiObsError}</p> : null}
          {aiObs ? <AiObservabilityView data={aiObs} /> : null}
        </div>
      )}
    </div>
  );
}

function AiObservabilityView({ data }: { data: OpsAiObservability }) {
  const [activeRunbook, setActiveRunbook] = useState<RunbookModuleKey | null>(null);
  const hs = data.health_summary;
  const offline = data.offline_evaluation;
  const online = data.online_outcome_quality;
  const drift = data.drift_data_health;
  const runtime = data.runtime_reliability;
  const judgments = {
    offlineQuality: data.offline_quality,
    evidenceConfidence: data.evidence_confidence,
    onlineUsefulness: data.online_usefulness,
    runtimeInfluence: data.runtime_influence,
    driftSummary: data.drift_summary,
    labelDriftSummary: data.label_drift_summary,
  };
  const onlineInsufficient = data.online_usefulness.value === "Unknown";
  const validationWarning =
    data.evidence_confidence.value === "Low" || data.evidence_confidence.value === "Medium"
      ? data.evidence_confidence.reason
      : null;

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>AI Ops Summary</CardTitle>
            <div className="flex flex-wrap gap-1">
              <RunbookTrigger label="Offline" onClick={() => setActiveRunbook("offline_model_quality")} />
              <RunbookTrigger label="Evidence" onClick={() => setActiveRunbook("evidence_confidence")} />
              <RunbookTrigger label="Online" onClick={() => setActiveRunbook("online_usefulness")} />
              <RunbookTrigger label="Runtime" onClick={() => setActiveRunbook("runtime_influence")} />
            </div>
          </div>
          <div className="text-xs text-mute">Prioritized for one question: is AI trustworthy and useful right now?</div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            <Stat title="Offline Model Quality" value={judgments.offlineQuality.value} tone={toneFromServer(judgments.offlineQuality.tone)} />
            <Stat title="Evidence Confidence" value={judgments.evidenceConfidence.value} tone={toneFromServer(judgments.evidenceConfidence.tone)} />
            <Stat title="Online Usefulness" value={judgments.onlineUsefulness.value} tone={toneFromServer(judgments.onlineUsefulness.tone)} />
            <Stat title="Runtime Influence" value={judgments.runtimeInfluence.value} tone={toneFromServer(judgments.runtimeInfluence.tone)} />
          </div>
          <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-5">
            <MiniStat title="Success Macro F1" value={fmtPct(hs.success_model_macro_f1)} />
            <MiniStat title="Gap Macro F1" value={fmtPct(hs.preview_gap_model_macro_f1)} />
            <MiniStat title="Recall(worse)" value={fmtPct(hs.recall_worse)} />
            <MiniStat title="Recall(high)" value={fmtPct(hs.recall_high_gap)} />
            <MiniStat title="Fallback Ratio" value={fmtPct(hs.fallback_ratio)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Why This Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-text">{judgments.offlineQuality.reason}</p>
          <p className="text-text">{judgments.evidenceConfidence.reason}</p>
          <p className="text-text">{judgments.onlineUsefulness.reason}</p>
          <p className="text-text">{judgments.runtimeInfluence.reason}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Offline Model Evaluation (Compact)</CardTitle>
            <div className="flex flex-wrap gap-1">
              <RunbookTrigger onClick={() => setActiveRunbook("offline_model_quality")} />
              <RunbookTrigger label="Dangerous Recall" onClick={() => setActiveRunbook("dangerous_class_recall")} />
            </div>
          </div>
          <div className="text-xs text-mute">Macro F1 and dangerous-class recall are primary; accuracy is secondary.</div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 xl:grid-cols-2">
            <CompactOfflineModelCard
              title="Success Model"
              model={offline.success_model}
              dangerClass="worse"
              validationWarning={validationWarning}
            />
            <CompactOfflineModelCard
              title="Preview Gap Model"
              model={offline.preview_gap_model}
              dangerClass="high"
              validationWarning={validationWarning}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Runtime Influence / Reliability</CardTitle>
            <div className="flex flex-wrap gap-1">
              <RunbookTrigger label="Influence" onClick={() => setActiveRunbook("runtime_influence")} />
              <RunbookTrigger label="Fallback" onClick={() => setActiveRunbook("runtime_reliability_fallback")} />
            </div>
          </div>
          <div className="text-xs text-mute">Shows whether AI ranking is meaningfully changing final decisions.</div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-5">
            <Stat title="Runtime Influence" value={judgments.runtimeInfluence.value} tone={toneFromServer(judgments.runtimeInfluence.tone)} />
            <Stat title="Ranking Used Ratio" value={fmtPct(runtime.ranking_used_ratio)} />
            <Stat title="Fallback Ratio" value={fmtPct(runtime.runtime_fallback_ratio)} tone={toneByInverse(runtime.runtime_fallback_ratio, 0.25, 0.4)} />
            <Stat title="Rule Center Selected %" value={fmtPct(runtime.rule_center_selected_ratio)} />
            <Stat title="Baseline Hold Selected %" value={fmtPct(runtime.baseline_hold_selected_ratio)} />
          </div>
          <details className="rounded border border-line/70 bg-panel2/30 p-3 text-xs">
            <summary className="cursor-pointer text-mute">Show candidate distribution details</summary>
            <div className="mt-2 grid gap-3 xl:grid-cols-2">
              <KeyCountList title="Candidate Selection Distribution" rows={runtime.candidate_selection_distribution} />
              <div className="rounded border border-line/70 bg-panel2/50 p-3">
                <div className="mb-2 text-xs uppercase tracking-wide text-neon">Candidate Strategy Mix</div>
                <div className="grid gap-2 md:grid-cols-3">
                  <MiniStat title="Conservative" value={fmtPct(runtime.conservative_selected_ratio)} />
                  <MiniStat title="Aggressive" value={fmtPct(runtime.aggressive_selected_ratio)} />
                  <MiniStat title="Balance" value={fmtPct(runtime.balance_selected_ratio)} />
                </div>
              </div>
            </div>
          </details>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Online Outcome Quality</CardTitle>
            <RunbookTrigger onClick={() => setActiveRunbook("online_usefulness")} />
          </div>
        </CardHeader>
        <CardContent>
          {onlineInsufficient ? (
            <div className="rounded border border-line/70 bg-panel2/40 p-3">
              <div className="text-sm font-semibold text-text">Online Usefulness: Unknown</div>
              <div className="mt-1 text-xs text-mute">
                Insufficient recent evaluated AI/manual samples in the selected window. Avoid high-confidence online conclusions.
              </div>
            </div>
          ) : (
            <div className="grid gap-2 md:grid-cols-3 lg:grid-cols-5">
              <Stat title="AI Improved Ratio (7d)" value={fmtPct(online.window_7d.ai.improved_ratio)} />
              <Stat title="Manual Improved Ratio (7d)" value={fmtPct(online.window_7d.manual.improved_ratio)} />
              <Stat title="AI vs Manual Δ (7d)" value={fmtPct(online.window_7d.ai_vs_manual_improved_delta)} />
              <Stat title="AI Worse Ratio (7d)" value={fmtPct(online.window_7d.ai.worse_ratio)} />
              <Stat title="Evaluated Samples (AI/Manual 7d)" value={`${fmtInt(online.window_7d.ai.total)} / ${fmtInt(online.window_7d.manual.total)}`} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Drift & Data Health</CardTitle>
            <div className="flex flex-wrap gap-1">
              <RunbookTrigger label="Feature" onClick={() => setActiveRunbook("feature_drift")} />
              <RunbookTrigger label="Label" onClick={() => setActiveRunbook("label_drift")} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-3">
            <Stat title="Feature Drift" value={judgments.driftSummary.value} tone={toneFromServer(judgments.driftSummary.tone)} />
            <Stat title="Label Drift" value={judgments.labelDriftSummary.value} tone={toneFromServer(judgments.labelDriftSummary.tone)} />
            <Stat title="Recent Feedback Samples (7d)" value={fmtInt(drift.data_quality.recent_feedback_sample_count)} />
          </div>
          <div className="rounded border border-line/70 bg-panel2/40 p-3 text-xs text-mute">
            {judgments.driftSummary.reason}
          </div>
          <details className="rounded border border-line/70 bg-panel2/30 p-3 text-xs">
            <summary className="cursor-pointer text-mute">Show full drift and sample-health details</summary>
            <div className="mt-2 space-y-3">
              <div className="rounded border border-line/70 bg-panel2/50 p-3">
                <div className="mb-2 text-xs uppercase tracking-wide text-neon">Feature Drift (curated)</div>
                <div className="overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="text-left text-mute">
                      <tr>
                        <th className="py-1">Feature</th>
                        <th>Baseline Mean</th>
                        <th>Recent Mean</th>
                        <th>Baseline P95</th>
                        <th>Recent P95</th>
                        <th>Delta</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {drift.feature_drift.map((row) => (
                        <tr key={row.feature} className="border-t border-line/50">
                          <td className="py-1 text-text">{row.feature}</td>
                          <td>{fmtNum(row.baseline_mean, 3)}</td>
                          <td>{fmtNum(row.recent_mean, 3)}</td>
                          <td>{fmtNum(row.baseline_p95, 3)}</td>
                          <td>{fmtNum(row.recent_p95, 3)}</td>
                          <td>{fmtPct(row.delta_ratio, 1)}</td>
                          <td className={toneClass(toneByLevel(row.status))}>{row.status || "Unknown"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="grid gap-3 xl:grid-cols-2">
                <div className="rounded border border-line/70 bg-panel2/50 p-3">
                  <div className="mb-2 text-xs uppercase tracking-wide text-neon">Label Drift</div>
                  <div className="overflow-auto">
                    <table className="w-full text-xs">
                      <thead className="text-left text-mute">
                        <tr>
                          <th className="py-1">Group</th>
                          <th>Label</th>
                          <th>Training</th>
                          <th>Recent</th>
                          <th>|Δ|</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {drift.label_drift.map((row) => (
                        <tr key={`${row.label_group}-${row.label}`} className="border-t border-line/50">
                          <td className="py-1">{row.label_group}</td>
                          <td>{row.label}</td>
                          <td>{fmtPct(row.training_ratio)}</td>
                          <td>{fmtPct(row.recent_ratio)}</td>
                          <td>{fmtPct(row.delta_abs)}</td>
                          <td className={toneClass(toneByLevel(row.status))}>{row.status}</td>
                        </tr>
                      ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="rounded border border-line/70 bg-panel2/50 p-3">
                  <div className="mb-2 text-xs uppercase tracking-wide text-neon">Sample Health</div>
                  <div className="space-y-1 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-mute">Usable-for-Training Ratio</span>
                      <span className="text-text font-semibold">{fmtPct(drift.data_quality.usable_for_training_ratio)}</span>
                    </div>
                    <div className="flex items-center justify-between gap-2 border-t border-line/40 pt-1">
                      <span className="text-mute">Label Coverage</span>
                      <span className="text-text font-semibold">{drift.data_quality.label_coverage || "N/A"}</span>
                    </div>
                    {drift.data_quality.sample_quality_distribution.map((row) => (
                      <div key={row.key} className="flex items-center justify-between gap-2 border-t border-line/40 pt-1">
                        <span className="text-mute">{row.key}</span>
                        <span className="text-text font-semibold">{row.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </details>
        </CardContent>
      </Card>

      <details className="rounded border border-line/70 bg-panel2/30 p-3 text-xs">
        <summary className="cursor-pointer text-mute">Show deeper offline details (per-class + confusion)</summary>
        <div className="mt-2 grid gap-3 xl:grid-cols-2">
          <div className="space-y-3">
            <PerClassTable title="Success Model Per-Class" model={offline.success_model} dangerClass="worse" />
            <ConfusionMatrixPanel title="Success Model Confusion Matrix" model={offline.success_model} />
          </div>
          <div className="space-y-3">
            <PerClassTable title="Preview Gap Model Per-Class" model={offline.preview_gap_model} dangerClass="high" />
            <ConfusionMatrixPanel title="Preview Gap Model Confusion Matrix" model={offline.preview_gap_model} />
          </div>
        </div>
      </details>
      <RunbookDialog
        moduleKey={activeRunbook}
        onClose={() => setActiveRunbook(null)}
        statusContext={buildRunbookStatusContext(data)}
      />
    </>
  );
}

function RunbookTrigger({ onClick, label = "Runbook" }: { onClick: () => void; label?: string }) {
  return (
    <Button variant="ghost" size="sm" onClick={onClick} className="h-7 px-2 text-xs">
      {label === "Runbook" ? "Runbook" : `Runbook · ${label}`}
    </Button>
  );
}

function RunbookDialog({
  moduleKey,
  onClose,
  statusContext,
}: {
  moduleKey: RunbookModuleKey | null;
  onClose: () => void;
  statusContext: Record<RunbookModuleKey, { value: string; tone: string; reason: string }>;
}) {
  if (!moduleKey) return null;
  const entry = AI_OPS_RUNBOOK_REGISTRY[moduleKey];
  const ctx = statusContext[moduleKey];
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 p-0" onClick={onClose}>
      <div
        className="h-full w-full max-w-2xl overflow-auto border-l border-line bg-panel p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <div className="text-xs uppercase tracking-wide text-neon">Runbook</div>
            <h3 className="text-lg font-semibold text-text">{entry.title}</h3>
            <div className="mt-1 text-xs text-mute">
              Current status: <span className={toneClass(toneFromServer(ctx.tone))}>{ctx.value}</span>
            </div>
            <div className="mt-1 text-xs text-mute">Reason: {ctx.reason}</div>
            <div className="mt-1 text-[11px] text-mute">
              Section: <span className="text-text">{entry.section}</span> · Tags: {entry.tags.join(", ")}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="rounded border border-line/70 bg-panel2/30 p-3">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h1 className="mb-3 text-xl font-semibold text-text">{children}</h1>,
              h2: ({ children }) => <h2 className="mb-2 mt-4 text-sm font-semibold text-neon">{children}</h2>,
              p: ({ children }) => <p className="mb-2 text-xs leading-6 text-mute">{children}</p>,
              ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 text-xs text-mute">{children}</ul>,
              ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 text-xs text-mute">{children}</ol>,
              li: ({ children }) => <li>{children}</li>,
              code: ({ children }) => (
                <code className="rounded bg-panel px-1 py-0.5 text-[11px] text-neon">{children}</code>
              ),
              pre: ({ children }) => <pre className="mb-2 overflow-auto rounded border border-line/70 bg-panel p-2 text-xs">{children}</pre>,
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noreferrer" className="text-neon underline">
                  {children}
                </a>
              ),
            }}
          >
            {entry.markdown}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

function buildRunbookStatusContext(data: OpsAiObservability): Record<RunbookModuleKey, { value: string; tone: string; reason: string }> {
  return {
    offline_model_quality: data.offline_quality,
    evidence_confidence: data.evidence_confidence,
    online_usefulness: data.online_usefulness,
    runtime_influence: data.runtime_influence,
    feature_drift: data.drift_summary,
    label_drift: data.label_drift_summary,
    runtime_reliability_fallback: {
      value:
        data.runtime_reliability.runtime_fallback_ratio == null
          ? "Unknown"
          : data.runtime_reliability.runtime_fallback_ratio >= 0.6
            ? "Elevated fallback"
            : data.runtime_reliability.runtime_fallback_ratio >= 0.25
              ? "Moderate fallback"
              : "Stable runtime path",
      tone:
        data.runtime_reliability.runtime_fallback_ratio == null
          ? "warning"
          : data.runtime_reliability.runtime_fallback_ratio >= 0.6
            ? "critical"
            : data.runtime_reliability.runtime_fallback_ratio >= 0.25
              ? "warning"
              : "normal",
      reason:
        data.runtime_reliability.runtime_fallback_ratio == null
          ? "Fallback ratio is unavailable; inspect runtime telemetry availability."
          : `Runtime fallback ratio is ${fmtPct(data.runtime_reliability.runtime_fallback_ratio)}; investigate service health if elevated.`,
    },
    dangerous_class_recall: {
      value: (() => {
        const worse = findRecall(data.offline_evaluation.success_model, "worse");
        const high = findRecall(data.offline_evaluation.preview_gap_model, "high");
        if (worse == null || high == null) return "Unknown";
        if (worse >= 0.6 && high >= 0.6) return "Acceptable";
        if (worse < 0.45 || high < 0.45) return "Low";
        return "Moderate";
      })(),
      tone: (() => {
        const worse = findRecall(data.offline_evaluation.success_model, "worse");
        const high = findRecall(data.offline_evaluation.preview_gap_model, "high");
        if (worse == null || high == null) return "warning";
        if (worse < 0.45 || high < 0.45) return "critical";
        if (worse < 0.6 || high < 0.6) return "warning";
        return "normal";
      })(),
      reason: (() => {
        const worse = findRecall(data.offline_evaluation.success_model, "worse");
        const high = findRecall(data.offline_evaluation.preview_gap_model, "high");
        return `Current recalls: worse=${fmtPct(worse)}, high=${fmtPct(high)}.`;
      })(),
    },
  };
}

function CompactOfflineModelCard({
  title,
  model,
  dangerClass,
  validationWarning,
}: {
  title: string;
  model: OpsAiModelEvaluation;
  dangerClass: string;
  validationWarning?: string | null;
}) {
  return (
    <div className="rounded border border-line/70 bg-panel2/50 p-3 space-y-2">
      <div className="text-xs uppercase tracking-wide text-neon">{title}</div>
      <div className="text-xs text-mute break-all">
        Model: {model.model_name || "N/A"} · Key: {model.model_key || "N/A"} · Valid size: {fmtInt(model.validation_size)}
      </div>
      <div className="text-xs text-mute break-all">
        Artifact: {model.artifact_path || "N/A"} · Updated: {fmtDate(model.artifact_timestamp)}
      </div>
      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
        <MiniStat title="Macro F1" value={fmtPct(model.macro_f1)} />
        <MiniStat title={`Recall(${dangerClass})`} value={fmtPct(findRecall(model, dangerClass))} />
        <MiniStat title="Validation Size" value={fmtInt(model.validation_size)} />
        <MiniStat title="Accuracy (secondary)" value={fmtPct(model.accuracy)} />
      </div>
      {validationWarning && (
        <div className="rounded border border-warning/50 bg-warning/10 p-2 text-xs text-warning">
          {validationWarning}
        </div>
      )}
    </div>
  );
}

function PerClassTable({ title, model, dangerClass }: { title: string; model: OpsAiModelEvaluation; dangerClass: string }) {
  return (
    <div className="rounded border border-line/70 bg-panel2/50 p-3">
      <div className="mb-2 text-xs uppercase tracking-wide text-neon">{title}</div>
      <div className="overflow-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-mute">
            <tr>
              <th className="py-1">Class</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>F1</th>
              <th>Support</th>
            </tr>
          </thead>
          <tbody>
            {model.per_class.map((row) => (
              <tr key={row.label} className="border-t border-line/50">
                <td className={`py-1 ${row.label === dangerClass ? "text-warning font-semibold" : "text-text"}`}>{row.label}</td>
                <td>{fmtPct(row.precision)}</td>
                <td className={row.label === dangerClass ? toneClass(toneByMetric(row.recall, 0.6, 0.45)) : ""}>{fmtPct(row.recall)}</td>
                <td>{fmtPct(row.f1)}</td>
                <td>{fmtInt(row.support)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ConfusionMatrixPanel({ title, model }: { title: string; model: OpsAiModelEvaluation }) {
  const labels = model.confusion.labels;
  const matrix = model.confusion.matrix;
  return (
    <div className="rounded border border-line/70 bg-panel2/50 p-3 space-y-2">
      <div className="text-xs uppercase tracking-wide text-neon">{title}</div>
      {labels.length === 0 || matrix.length === 0 ? (
        <div className="text-xs text-mute">No confusion matrix available.</div>
      ) : (
        <div className="overflow-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-mute">
              <tr>
                <th className="py-1">Actual \ Pred</th>
                {labels.map((label) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.map((row, ridx) => (
                <tr key={`${labels[ridx] || ridx}`} className="border-t border-line/50">
                  <td className="py-1 text-mute">{labels[ridx] || `row${ridx}`}</td>
                  {row.map((value, cidx) => (
                    <td key={`${ridx}-${cidx}`} className={ridx === cidx ? "text-text font-semibold" : "text-mute"}>
                      {fmtInt(value)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="text-xs text-mute">{model.confusion.note || "-"}</div>
    </div>
  );
}

function findRecall(model: OpsAiModelEvaluation, label: string): number | null {
  const row = model.per_class.find((p) => p.label === label);
  return row?.recall ?? null;
}

function TabButton({
  active,
  onClick,
  label,
  id,
  controls,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  id: string;
  controls: string;
}) {
  return (
    <Button
      id={id}
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      variant={active ? "default" : "ghost"}
      className={active ? "border border-line" : ""}
      onClick={onClick}
    >
      {label}
    </Button>
  );
}

function Stat({ title, value, tone }: { title: string; value: string; tone?: "normal" | "warning" | "critical" }) {
  const cls = toneClass(tone);
  return (
    <div className="rounded border border-line/70 bg-panel2/60 p-2">
      <div className="text-[11px] uppercase tracking-wide text-mute">{title}</div>
      <div className={`mt-1 text-sm font-semibold break-all ${cls}`}>{value}</div>
    </div>
  );
}

function MiniStat({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded border border-line/50 bg-panel2/40 p-2">
      <div className="text-[10px] uppercase tracking-wide text-mute">{title}</div>
      <div className="mt-1 text-xs text-text break-all">{value}</div>
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

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "N/A";
  return Number(v).toFixed(digits);
}

function fmtInt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "N/A";
  return String(Math.round(v));
}

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "N/A";
  return `${(Number(v) * 100).toFixed(digits)}%`;
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

function fmtCpuPct(v: number | null | undefined): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0) return "N/A";
  if (n > 0 && n < 0.1) return "<0.1%";
  return `${n.toFixed(2)}%`;
}

function toneClass(tone?: "normal" | "warning" | "critical"): string {
  if (tone === "critical") return "text-danger";
  if (tone === "warning") return "text-warning";
  return "text-text";
}

function toneFromServer(tone: string | null | undefined): "normal" | "warning" | "critical" {
  if (tone === "critical" || tone === "warning" || tone === "normal") return tone;
  return "warning";
}

function toneByMetric(v: number | null | undefined, goodMin: number, poorMax: number): "normal" | "warning" | "critical" {
  const n = Number(v);
  if (!Number.isFinite(n)) return "warning";
  if (n < poorMax) return "critical";
  if (n < goodMin) return "warning";
  return "normal";
}

function toneByInverse(v: number | null | undefined, goodMax: number, poorMin: number): "normal" | "warning" | "critical" {
  const n = Number(v);
  if (!Number.isFinite(n)) return "warning";
  if (n >= poorMin) return "critical";
  if (n >= goodMax) return "warning";
  return "normal";
}

function toneByLevel(level: string): "normal" | "warning" | "critical" {
  if (level === "High") return "critical";
  if (level === "Medium") return "warning";
  if (level === "Insufficient data" || level === "Unknown") return "warning";
  return "normal";
}

function toneByHealth(level: string): "normal" | "warning" | "critical" {
  if (level === "Good") return "normal";
  if (level === "Watch") return "warning";
  return "critical";
}
