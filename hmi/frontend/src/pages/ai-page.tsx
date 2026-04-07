import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Link2, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useDevices } from "@/routes/use-data";
import type {
  AIPostEffectComparison,
  AITelemetryComparison,
  AIRecommendationHistoryItem,
  AIRecommendationHistoryResponse,
} from "@/types";
type TimePreset = "30m" | "1h" | "3h" | "24h" | "7d" | "30d" | "custom";
type RecommendationState = "generated" | "previewed" | "applied" | "dismissed" | "expired";
type EvaluationStatus = "Pending" | "Completed" | "Not Available" | "Insufficient Data";
type MetricKey = "in_band_ratio" | "overshoot_c" | "settling_sec" | "mean_abs_error" | "saturation_ratio" | "temp_swing";

export function AIPage() {
  const { devices } = useDevices();
  const [historyData, setHistoryData] = useState<AIRecommendationHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evaluationNotice, setEvaluationNotice] = useState<string | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [devicePickerOpen, setDevicePickerOpen] = useState(false);
  const [devicePickerQuery, setDevicePickerQuery] = useState("");
  const [timePreset, setTimePreset] = useState<TimePreset>("30m");
  const [customStart, setCustomStart] = useState(() => toDatetimeLocalValue(new Date(Date.now() - 60 * 60 * 1000)));
  const [customEnd, setCustomEnd] = useState(() => toDatetimeLocalValue(new Date()));
  const [busy, setBusy] = useState(false);
  const [insufficientDataByRecommendation, setInsufficientDataByRecommendation] = useState<Record<number, true>>({});
  const [telemetryComparison, setTelemetryComparison] = useState<AITelemetryComparison | null>(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const devicePickerRef = useRef<HTMLDivElement>(null);

  const timeRange = useMemo(() => buildTimeRange(timePreset, customStart, customEnd), [timePreset, customStart, customEnd]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const historyNext = await api.aiRecommendationHistory({ limit: 500 });
      setHistoryData(historyNext);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const latestAppliedGlobally = useMemo(() => {
    const source = historyData?.items ?? [];
    return source.find((item) => item.history_state === "applied") ?? source[0] ?? null;
  }, [historyData?.items]);

  useEffect(() => {
    if (selectedDeviceId != null) return;
    if (!latestAppliedGlobally) return;
    setSelectedDeviceId(latestAppliedGlobally.device_id);
  }, [latestAppliedGlobally, selectedDeviceId]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!devicePickerOpen) return;
      if (!devicePickerRef.current) return;
      const target = event.target;
      if (target instanceof Node && !devicePickerRef.current.contains(target)) {
        setDevicePickerOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [devicePickerOpen]);

  const selectedDeviceRecords = useMemo(() => {
    if (selectedDeviceId == null) return [] as AIRecommendationHistoryItem[];
    return (historyData?.items ?? []).filter((item) => item.device_id === selectedDeviceId);
  }, [historyData?.items, selectedDeviceId]);

  const currentRecord = useMemo(() => {
    if (selectedDeviceRecords.length === 0) return null;
    return selectedDeviceRecords.find((item) => normalizeHistoryState(item) === "applied") ?? selectedDeviceRecords[0] ?? null;
  }, [selectedDeviceRecords]);

  const recommendationState = useMemo<RecommendationState>(
    () => normalizeHistoryState(currentRecord),
    [currentRecord]
  );

  const evaluationStatus = useMemo(
    () =>
      deriveEvaluationStatus(
        recommendationState,
        currentRecord,
        Boolean(currentRecord && insufficientDataByRecommendation[currentRecord.recommendation_id])
      ),
    [currentRecord, insufficientDataByRecommendation, recommendationState]
  );

  const appliedOutsideWindow = useMemo(() => {
    if (!currentRecord?.applied_at) return false;
    if (typeof timeRange.startMs !== "number") return false;
    const appliedMs = new Date(currentRecord.applied_at).getTime();
    if (Number.isNaN(appliedMs)) return false;
    return appliedMs < timeRange.startMs;
  }, [currentRecord?.applied_at, timeRange.startMs]);

  const selectedDevice = useMemo(() => {
    if (selectedDeviceId == null) return null;
    return devices.find((device) => device.id === selectedDeviceId) ?? null;
  }, [devices, selectedDeviceId]);

  const searchableDevices = useMemo(() => {
    const q = devicePickerQuery.trim().toLowerCase();
    if (!q) return devices;
    return devices.filter((device) =>
      [device.name, device.code, device.line, device.location].join(" ").toLowerCase().includes(q)
    );
  }, [devices, devicePickerQuery]);

  useEffect(() => {
    let active = true;
    async function loadTelemetryComparison() {
      if (!currentRecord) {
        setTelemetryComparison(null);
        setTelemetryError(null);
        setTelemetryLoading(false);
        return;
      }
      setTelemetryLoading(true);
      setTelemetryError(null);
      try {
        const observationMinutes = toObservationWindowMinutes(timeRange);
        const data = await api.aiRecommendationTelemetryComparison(currentRecord.device_id, currentRecord.recommendation_id, {
          start_ms: timeRange.startMs,
          end_ms: timeRange.endMs,
          observation_window_minutes: observationMinutes,
          baseline_window_minutes: observationMinutes,
        });
        if (!active) return;
        setTelemetryComparison(data);
      } catch (err) {
        if (!active) return;
        setTelemetryComparison(null);
        setTelemetryError(normalizeError(err));
      } finally {
        if (!active) return;
        setTelemetryLoading(false);
      }
    }
    void loadTelemetryComparison();
    return () => {
      active = false;
    };
  }, [currentRecord?.device_id, currentRecord?.recommendation_id, timeRange.endMs, timeRange.startMs]);

  async function handleEvaluate() {
    if (!currentRecord || busy) return;
    const recommendationId = currentRecord.recommendation_id;
    setBusy(true);
    setError(null);
    setEvaluationNotice(null);
    try {
      await api.evaluateAiRecommendationActual(currentRecord.device_id, currentRecord.recommendation_id, {
        observation_window_minutes: toObservationWindowMinutes(timeRange),
      });
      setInsufficientDataByRecommendation((previous) => {
        const next = { ...previous };
        delete next[recommendationId];
        return next;
      });
      setEvaluationNotice("Actual effect evaluation completed for the current recommendation.");
      await load();
    } catch (err) {
      const message = normalizeError(err);
      if (isInsufficientTelemetryError(message)) {
        setInsufficientDataByRecommendation((previous) => ({ ...previous, [recommendationId]: true }));
        setEvaluationNotice("Not enough post-apply telemetry data yet.");
      } else {
        setError(message);
      }
    } finally {
      setBusy(false);
    }
  }

  function selectDevice(deviceId: number) {
    setSelectedDeviceId(deviceId);
    setDevicePickerOpen(false);
    setDevicePickerQuery("");
    setEvaluationNotice(null);
  }

  return (
    <div className="space-y-4">
      <Card className="border-neon/35 bg-[linear-gradient(180deg,rgba(8,39,55,0.55),rgba(4,18,30,0.92))]">
        <CardHeader className="pb-3">
          <div className="space-y-1">
            <div className="text-[11px] uppercase tracking-[0.18em] text-neon/80">AI Review Console</div>
            <CardTitle className="text-[28px] leading-none">AI Optimization Review</CardTitle>
            <div className="mt-1 text-sm text-mute">
              Switch devices if needed. This page always shows the selected device's latest applied AI recommendation, even if it was applied long ago.
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 rounded-xl border border-line/70 bg-panel2/60 p-2 xl:grid-cols-[260px_minmax(0,1fr)_auto]">
            <DeviceSearchSelect
              containerRef={devicePickerRef}
              open={devicePickerOpen}
              setOpen={setDevicePickerOpen}
              query={devicePickerQuery}
              setQuery={setDevicePickerQuery}
              current={selectedDevice}
              items={searchableDevices}
              onSelect={selectDevice}
            />
            <RangePicker
              timePreset={timePreset}
              onPresetChange={setTimePreset}
              customStart={customStart}
              customEnd={customEnd}
              onCustomStartChange={setCustomStart}
              onCustomEndChange={setCustomEnd}
            />
            <div className="flex justify-start xl:justify-end">
              <Button variant="ghost" className="w-full xl:w-auto" onClick={load}>Refresh</Button>
            </div>
          </div>
          <div className="text-xs text-mute/90">
            The selected time window is used to review post-apply telemetry for the latest applied recommendation.
          </div>
          {appliedOutsideWindow && (
            <div className="text-xs text-accent">
              The selected time window may not fully cover the initial post-apply observation period.
            </div>
          )}

          {selectedDevice && (
            <div className="rounded-xl border border-neon/35 bg-neon/10 px-4 py-3">
              <div className="text-[11px] uppercase tracking-wide text-neon">Selected Device</div>
              <div className="mt-1 text-lg font-semibold text-text">{selectedDevice.name}</div>
              <div className="text-sm text-mute">
                {selectedDevice.code} · {selectedDevice.line} · {selectedDevice.location}
              </div>
            </div>
          )}

          {loading && <div className="text-sm text-mute">Loading AI comparison...</div>}
          {evaluationNotice && !loading && (
            <div className="rounded-md border border-accent/35 bg-accent/10 px-3 py-2 text-sm text-accent">
              {evaluationNotice}
            </div>
          )}
          {error && !loading && <div className="text-sm text-danger">{error}</div>}
          {!loading && !error && !currentRecord && (
            <div className="rounded-xl border border-line/70 bg-panel2 px-4 py-4">
              <div className="text-[11px] uppercase tracking-wide text-mute">No Applied AI Record</div>
              <div className="mt-1 text-sm text-text">
                {selectedDevice
                  ? `${selectedDevice.name} has no applied AI recommendation yet.`
                  : "No applied AI recommendation found yet."}
              </div>
              <div className="mt-1 text-xs text-mute">
                Apply a recommendation from device detail first, or switch to another device with an applied AI record.
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {currentRecord && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Latest Applied Recommendation</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 xl:grid-cols-[1fr_1fr_1fr]">
              <InfoBlock
                title="Recommendation"
                rows={[
                  ["Recommendation ID", String(currentRecord.recommendation_id)],
                  ["Problem", formatLabel(currentRecord.problem_type)],
                  ["Expected Effect", currentRecord.expected_effect ? formatLabel(currentRecord.expected_effect) : "-"],
                  ["Risk", currentRecord.risk_level ?? "-"],
                  ["Applied At", formatDateTime(currentRecord.applied_at ?? currentRecord.generated_at)],
                  ["Evaluated At", currentRecord.evaluated_at ? formatDateTime(currentRecord.evaluated_at) : "Not evaluated"],
                  ["History State", formatHistoryState(recommendationState)],
                  ["Evaluation Status", evaluationStatus],
                ]}
              />
              <ParamBlock
                title="Baseline Params"
                params={currentRecord.current_params}
                controlMode={readOptionalControlMode(currentRecord)}
                emptyText="No baseline parameter snapshot was captured for this applied recommendation."
              />
              <ParamBlock
                title="Recommended / Delta"
                params={currentRecord.recommended_params}
                delta={currentRecord.delta}
                emptyText="Recommended parameter snapshot is not available for this recommendation record."
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle>Actual Effect Comparison</CardTitle>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void handleEvaluate()}
                    disabled={busy || recommendationState !== "applied"}
                    title={recommendationState !== "applied" ? "This recommendation is not in applied state yet." : undefined}
                  >
                    {busy ? "Evaluating..." : evaluationStatus === "Completed" ? "Re-evaluate Actual Effect" : "Evaluate Actual Effect"}
                  </Button>
                  <Button size="sm" variant="ghost" asChild>
                    <Link to={`/devices/${currentRecord.device_id}`}>
                      <Link2 className="mr-1 h-4 w-4" />
                      Open Device
                    </Link>
                  </Button>
                </div>
              </div>
              <div className="text-xs text-mute">
                {recommendationState !== "applied"
                  ? "Actual effect evaluation is available after this recommendation reaches applied state."
                  : evaluationStatus === "Completed"
                    ? "This recommendation has already been evaluated. You can re-run evaluation for a fresh telemetry window."
                    : evaluationStatus === "Insufficient Data"
                      ? "Not enough post-apply telemetry data yet. Wait for more runtime data, then re-evaluate."
                      : "Run evaluation to validate whether real post-apply behavior improved against baseline."}
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <TelemetryComparisonBlock
                comparison={telemetryComparison}
                loading={telemetryLoading}
                error={telemetryError}
              />
              <MetricsBlock
                title="Actual Effect Summary"
                status={evaluationStatus}
                emptyText="Run actual effect evaluation to compare post-apply telemetry with the pre-apply baseline for this recommendation."
                metrics={
                  currentRecord.post_effect_summary
                    ? [
                        ["In-band Ratio", formatPercent(currentRecord.post_effect_summary.in_band_ratio_after)],
                        ["Overshoot", `${currentRecord.post_effect_summary.overshoot_c_after.toFixed(3)}°C`],
                        ["Settling Time", formatSeconds(currentRecord.post_effect_summary.settling_sec_after)],
                        ["Mean |Error|", `${currentRecord.post_effect_summary.mean_abs_error_after.toFixed(3)}°C`],
                        ["Saturation Ratio", formatPercent(currentRecord.post_effect_summary.saturation_ratio_after)],
                        ["Temp Swing", `${currentRecord.post_effect_summary.temp_swing_after.toFixed(3)}°C`],
                      ]
                    : null
                }
              />
              <ComparisonBlock
                title="Before vs After"
                comparison={currentRecord.comparison_to_before}
                actualSummary={currentRecord.post_effect_summary}
                emptyText="No before-vs-after comparison is available yet. Run actual effect evaluation to generate this review."
                mode="before-after"
                subtitle="Compared against the pre-apply baseline captured for this recommendation."
              />
              <ComparisonBlock
                title="Preview vs Actual"
                comparison={currentRecord.comparison_to_preview}
                actualSummary={currentRecord.post_effect_summary}
                emptyText={previewEmptyText(currentRecord)}
                mode="preview-actual"
                subtitle="Compared against the preview simulation generated before apply."
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function RangePicker({
  timePreset,
  onPresetChange,
  customStart,
  customEnd,
  onCustomStartChange,
  onCustomEndChange,
}: {
  timePreset: TimePreset;
  onPresetChange: (value: TimePreset) => void;
  customStart: string;
  customEnd: string;
  onCustomStartChange: (value: string) => void;
  onCustomEndChange: (value: string) => void;
}) {
  const options: Array<{ value: TimePreset; label: string }> = [
    { value: "30m", label: "Last 30 Minutes" },
    { value: "1h", label: "Last 1 Hour" },
    { value: "3h", label: "Last 3 Hours" },
    { value: "24h", label: "Last 24 Hours" },
    { value: "7d", label: "Last 7 Days" },
    { value: "30d", label: "Last 30 Days" },
    { value: "custom", label: "Custom Range" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-panel px-3 py-2">
      <span className="shrink-0 whitespace-nowrap text-xs uppercase tracking-wide text-mute">Window</span>
      <Select value={timePreset} onValueChange={(value) => onPresetChange(value as TimePreset)}>
        <SelectTrigger className="h-8 w-[220px] border-line bg-panel2 text-sm">
          <SelectValue placeholder="Select time range" />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <label className="flex items-center gap-1 text-xs text-mute">
        Start
        <input
          type="datetime-local"
          className="h-8 rounded-md border border-line bg-panel2 px-2 text-xs text-text outline-none focus:border-neon/60"
          value={customStart}
          onChange={(event) => onCustomStartChange(event.target.value)}
        />
      </label>
      <label className="flex items-center gap-1 text-xs text-mute">
        End
        <input
          type="datetime-local"
          className="h-8 rounded-md border border-line bg-panel2 px-2 text-xs text-text outline-none focus:border-neon/60"
          value={customEnd}
          onChange={(event) => onCustomEndChange(event.target.value)}
        />
      </label>
    </div>
  );
}

function DeviceSearchSelect({
  containerRef,
  open,
  setOpen,
  query,
  setQuery,
  current,
  items,
  onSelect,
}: {
  containerRef?: React.RefObject<HTMLDivElement>;
  open: boolean;
  setOpen: (value: boolean) => void;
  query: string;
  setQuery: (value: string) => void;
  current: { id: number; name: string; code: string; line: string; location: string } | null;
  items: { id: number; name: string; code: string; line: string; location: string }[];
  onSelect: (deviceId: number) => void;
}) {
  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        className="flex h-10 w-full items-center justify-between rounded-md border border-line bg-panel px-3 text-left text-sm text-text transition-colors hover:border-neon/40"
        onClick={() => setOpen(!open)}
      >
        <span className="truncate">{current ? `${current.name} · ${current.code}` : "Select device"}</span>
        <ChevronDown className={`h-4 w-4 text-mute transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-20 mt-2 w-full rounded-xl border border-line bg-panel p-3 shadow-panel">
          <div className="flex items-center gap-2 rounded-md border border-neon/50 bg-panel2 px-3 py-2">
            <Search className="h-4 w-4 text-mute" />
            <input
              className="w-full bg-transparent text-sm text-text outline-none placeholder:text-mute"
              placeholder="Search device"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
          </div>
          <div className="mt-2 max-h-64 space-y-2 overflow-y-auto">
            {items.map((device) => (
              <button
                key={device.id}
                type="button"
                className="w-full rounded-md border border-line/70 bg-panel2 px-3 py-2 text-left transition-colors hover:border-neon/40 hover:bg-neon/5"
                onClick={() => onSelect(device.id)}
              >
                <div className="text-sm font-semibold text-neon">{device.name}</div>
                <div className="text-xs text-mute">{device.code} · {device.line} · {device.location}</div>
              </button>
            ))}
            {items.length === 0 && <div className="text-xs text-mute">No matching devices.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function InfoBlock({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">{title}</div>
      <div className="mt-2 space-y-1 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 rounded-md border border-line/50 bg-panel2/70 px-2 py-1.5">
            <span className="text-mute">{label}</span>
            <span className="text-right text-text">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ParamBlock({
  title,
  params,
  delta,
  controlMode,
  emptyText,
}: {
  title: string;
  params?: { kp: number; ki: number; kd: number } | null;
  delta?: { kp: number; ki: number; kd: number } | null;
  controlMode?: string | null;
  emptyText: string;
}) {
  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">{title}</div>
      {!params ? (
        <div className="mt-2 min-h-[98px] rounded-md border border-line/60 bg-panel2/70 px-3 py-2">
          <div className="inline-flex rounded border border-line/60 bg-panel px-2 py-0.5 text-[10px] uppercase tracking-wide text-mute">
            Snapshot Missing
          </div>
          <div className="mt-2 text-xs text-text">{emptyText}</div>
          <div className="mt-1 text-[11px] text-mute">Snapshot capture was not available for this record.</div>
        </div>
      ) : (
        <div className="mt-2 grid grid-cols-[48px_repeat(2,minmax(0,1fr))] gap-x-2 gap-y-1 text-xs">
          <span className="text-mute">Param</span>
          <span className="text-right text-mute">Value</span>
          <span className="text-right text-mute">{delta ? "Delta" : ""}</span>
          <span className="text-text">Kp</span>
          <span className="text-right text-text">{params.kp.toFixed(4)}</span>
          <span className="text-right text-neon">{delta ? withSign(delta.kp) : ""}</span>
          <span className="text-text">Ki</span>
          <span className="text-right text-text">{params.ki.toFixed(4)}</span>
          <span className="text-right text-neon">{delta ? withSign(delta.ki) : ""}</span>
          <span className="text-text">Kd</span>
          <span className="text-right text-text">{params.kd.toFixed(4)}</span>
          <span className="text-right text-neon">{delta ? withSign(delta.kd) : ""}</span>
          {controlMode && (
            <>
              <span className="text-text">Mode</span>
              <span className="text-right text-text">{controlMode}</span>
              <span className="text-right text-mute">{""}</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function MetricsBlock({
  title,
  status,
  metrics,
  emptyText,
}: {
  title: string;
  status: EvaluationStatus;
  metrics: [string, string][] | null;
  emptyText: string;
}) {
  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">{title}</div>
        <StatusBadge status={status} />
      </div>
      {!metrics ? (
        <div className="mt-2 text-xs text-mute">{emptyText}</div>
      ) : (
        <div className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
          {metrics.map(([label, value]) => (
            <div key={label} className="rounded border border-line/60 bg-panel2 px-2 py-1 text-xs">
              <div className="text-mute">{label}</div>
              <div className="mt-0.5 font-semibold text-text">{value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ComparisonBlock({
  title,
  comparison,
  actualSummary,
  emptyText,
  mode,
  subtitle,
}: {
  title: string;
  comparison?: AIPostEffectComparison | null;
  actualSummary?: AIRecommendationHistoryItem["post_effect_summary"] | null;
  emptyText: string;
  mode: "before-after" | "preview-actual";
  subtitle: string;
}) {
  const rows = buildComparisonRows(comparison, actualSummary);
  const overall = rows ? summarizeComparisonOverall(mode, rows) : null;
  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">{title}</div>
      <div className="mt-0.5 text-[11px] text-mute">{subtitle}</div>
      {!rows ? (
        <div className="mt-2 text-xs text-mute">{emptyText}</div>
      ) : (
        <div className="mt-2 space-y-2">
          <div className="rounded border border-line/60 bg-panel2 px-2 py-1 text-xs">
            <div className="text-text">{overall?.headline}</div>
            {overall?.reason && <div className="mt-0.5 text-mute">{overall.reason}</div>}
          </div>
          <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((row) => (
              <div key={row.key} className="rounded border border-line/60 bg-panel2 px-2 py-1 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-mute">{row.label}</span>
                  <MetricStatusBadge status={row.result} />
                </div>
                <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
                  <span className="text-mute">{mode === "before-after" ? "Before" : "Preview"}</span>
                  <span className="text-right text-text">{formatMetricValue(row.before, row.key)}</span>
                  <span className="text-mute">{mode === "before-after" ? "After" : "Actual"}</span>
                  <span className="text-right text-text">{formatMetricValue(row.after, row.key)}</span>
                  <span className="text-mute">{mode === "before-after" ? "Delta" : "Gap"}</span>
                  <span className={`text-right font-semibold ${comparisonValueTone(row.result)}`}>
                    {formatMetricDelta(row.deltaRaw, row.key)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

type TelemetryChartRow = {
  xMin: number;
  baseline?: number;
  preview?: number;
  actual?: number;
  target?: number;
};

function TelemetryComparisonBlock({
  comparison,
  loading,
  error,
}: {
  comparison: AITelemetryComparison | null;
  loading: boolean;
  error: string | null;
}) {
  const minCurvePoints = 3;
  const chartRows = useMemo(() => buildTelemetryChartRows(comparison), [comparison]);
  const xMin = chartRows.length > 0 ? chartRows[0].xMin : -30;
  const xMax = chartRows.length > 0 ? chartRows[chartRows.length - 1].xMin : 30;
  const hasBaseline = Boolean(comparison && comparison.baseline_curve.length >= minCurvePoints);
  const hasPreview = Boolean(comparison && comparison.preview_curve.length >= minCurvePoints);
  const hasActual = Boolean(comparison && comparison.actual_curve.length >= minCurvePoints);
  const mode: "full" | "partial" = hasBaseline && hasPreview && hasActual ? "full" : "partial";
  const missingCurves = comparison?.missing_curves ?? [];
  const hasAnyCurve = chartRows.some((row) => row.baseline != null || row.preview != null || row.actual != null);
  const actualUnavailable = Boolean(comparison && comparison.actual_curve.length === 0) || missingCurves.includes("actual");
  const actualLimited = Boolean(comparison && comparison.actual_curve.length > 0 && comparison.actual_curve.length < minCurvePoints);
  const actualIncomplete = Boolean(!actualUnavailable && (actualLimited || comparison?.partial_post_apply_window));
  const previewUnavailable = Boolean(comparison && comparison.preview_curve.length === 0) || missingCurves.includes("preview");
  const baselineUnavailable = Boolean(comparison && comparison.baseline_curve.length === 0) || missingCurves.includes("baseline");

  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">Telemetry Comparison</div>
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
            mode === "full" ? "border-accent/40 bg-accent/10 text-accent" : "border-line/70 bg-panel2 text-mute"
          }`}
        >
          {mode === "full" ? "Full Comparison" : "Partial Comparison"}
        </span>
      </div>
      <div className="mt-0.5 text-[11px] text-mute/90">
        Baseline is aligned to the pre-apply period ending at the recommendation apply time. Preview and actual curves are aligned from the apply moment onward.
      </div>
      {comparison?.partial_post_apply_window && (
        <div className="mt-2 text-xs text-accent">Selected window does not fully cover the post-apply observation period.</div>
      )}
      {actualUnavailable && <div className="mt-1 text-xs text-mute">Actual telemetry unavailable in selected post-apply window.</div>}
      {!actualUnavailable && actualLimited && <div className="mt-1 text-xs text-mute">Actual telemetry is limited in selected post-apply window.</div>}
      {!actualUnavailable && !actualLimited && mode === "partial" && (
        <div className="mt-1 text-xs text-mute">Some comparison curves are unavailable for this recommendation.</div>
      )}
      {comparison?.preview_source === "reconstructed" && (
        <div className="mt-1 text-[10px] text-mute/70">Preview source: reconstructed from recommendation context.</div>
      )}
      {loading ? (
        <div className="mt-3 text-xs text-mute">Loading telemetry comparison curves...</div>
      ) : error ? (
        <div className="mt-3 text-xs text-danger">{error}</div>
      ) : !comparison || !hasAnyCurve ? (
        <div className="mt-3 text-xs text-mute">No telemetry comparison curves are available for this recommendation yet.</div>
      ) : (
        <>
          <div className="relative mt-3 h-[280px] rounded border border-line/60 bg-panel2/70 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartRows} margin={{ top: 6, right: 18, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(41,240,255,0.12)" />
                <XAxis
                  dataKey="xMin"
                  type="number"
                  stroke="#7fa6b8"
                  domain={[xMin, xMax]}
                  tickFormatter={(value) => formatRelativeMinuteLabel(value)}
                  tick={{ fontSize: 11 }}
                  minTickGap={30}
                />
                <YAxis
                  stroke="#7fa6b8"
                  width={56}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(value) => `${Number(value).toFixed(1)}°C`}
                />
                <Tooltip
                  contentStyle={{ background: "rgba(5, 24, 34, 0.95)", border: "1px solid rgba(41,240,255,0.35)", borderRadius: 8 }}
                  itemStyle={{ color: "#c7e4f1", fontSize: 12 }}
                  labelStyle={{ color: "#95c0d3", fontSize: 12 }}
                  formatter={(value, name) => [`${Number(value).toFixed(3)}°C`, seriesLabel(name)]}
                  labelFormatter={(value) => `t=${formatRelativeMinuteLabel(Number(value))}`}
                  cursor={{ stroke: "rgba(41,240,255,0.3)", strokeDasharray: "3 3" }}
                />
                <ReferenceLine
                  x={0}
                  stroke="rgba(42,212,160,0.62)"
                  strokeDasharray="4 3"
                  label={{ value: "Applied", position: "insideTopRight", fill: "rgba(42,212,160,0.82)", fontSize: 10 }}
                />
                <Line type="monotone" dataKey="baseline" connectNulls={false} stroke="#f9c74f" strokeWidth={2.1} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="preview" connectNulls={false} stroke="#ff8a5b" strokeWidth={2.1} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="actual" connectNulls={false} stroke="#29f0ff" strokeWidth={2.8} strokeOpacity={0.98} dot={false} isAnimationActive={false} />
                <Line
                  type="monotone"
                  dataKey="target"
                  connectNulls
                  stroke="#84b3a4"
                  strokeOpacity={0.3}
                  strokeWidth={1}
                  strokeDasharray="3 3"
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
            {(actualUnavailable || previewUnavailable || baselineUnavailable || actualIncomplete) && (
              <div className="pointer-events-none absolute right-3 top-3 flex flex-col items-end gap-1">
                {actualUnavailable && (
                  <span className="rounded border border-line/60 bg-panel/80 px-2 py-0.5 text-[10px] text-mute">Actual unavailable</span>
                )}
                {!actualUnavailable && actualIncomplete && (
                  <span className="rounded border border-line/60 bg-panel/80 px-2 py-0.5 text-[10px] text-mute">Actual incomplete</span>
                )}
                {previewUnavailable && (
                  <span className="rounded border border-line/60 bg-panel/80 px-2 py-0.5 text-[10px] text-mute">Preview unavailable</span>
                )}
                {baselineUnavailable && (
                  <span className="rounded border border-line/60 bg-panel/80 px-2 py-0.5 text-[10px] text-mute">Baseline unavailable</span>
                )}
              </div>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-mute">
            <ChartLegend label="Baseline" sampleClass="bg-[#f9c74f]" muted={!hasBaseline} />
            <ChartLegend label="Preview" sampleClass="bg-[#ff8a5b]" muted={!hasPreview} />
            <ChartLegend label="Actual" sampleClass="bg-[#29f0ff]" muted={!hasActual} />
            <ChartLegend label="Target" sampleClass="bg-[#2ad4a0]" />
            <span className="text-mute/80">t=0: AI recommendation applied</span>
          </div>
        </>
      )}
    </div>
  );
}

function ChartLegend({ label, sampleClass, muted = false }: { label: string; sampleClass: string; muted?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${muted ? "opacity-45" : ""}`}>
      <span className={`inline-block h-2 w-5 rounded ${sampleClass} ${muted ? "grayscale" : ""}`} />
      <span>{label}{muted ? " (unavailable)" : ""}</span>
    </span>
  );
}

function StatusBadge({ status }: { status: EvaluationStatus }) {
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide ${evaluationStatusTone(status)}`}>
      {status}
    </span>
  );
}

function MetricStatusBadge({ status }: { status: "Improved" | "Worse" | "Unchanged" }) {
  const tone =
    status === "Improved"
      ? "border-accent/50 bg-accent/10 text-accent"
      : status === "Worse"
        ? "border-danger/50 bg-danger/10 text-danger"
        : "border-line/70 bg-panel text-mute";
  return <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${tone}`}>{status}</span>;
}

function normalizeError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Request failed";
}

function isInsufficientTelemetryError(message: string): boolean {
  return message.toLowerCase().includes("not enough post-apply telemetry data");
}

function deriveEvaluationStatus(
  state: RecommendationState,
  record: AIRecommendationHistoryItem | null,
  hasInsufficientDataFlag: boolean
): EvaluationStatus {
  if (!record || state !== "applied") return "Not Available";
  if (record.actual_effect_evaluated) return "Completed";
  if (record.insufficient_data) return "Insufficient Data";
  if (hasInsufficientDataFlag) return "Insufficient Data";
  return "Pending";
}

function evaluationStatusTone(status: EvaluationStatus): string {
  if (status === "Completed") return "border-accent/50 bg-accent/10 text-accent";
  if (status === "Pending") return "border-neon/40 bg-neon/10 text-neon";
  if (status === "Insufficient Data") return "border-danger/40 bg-danger/10 text-danger";
  return "border-line/70 bg-panel2 text-mute";
}

function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function normalizeHistoryState(record: AIRecommendationHistoryItem | null): RecommendationState {
  const raw = String(record?.history_state ?? "").trim().toLowerCase();
  if (raw === "generated" || raw === "previewed" || raw === "applied" || raw === "dismissed" || raw === "expired") {
    return raw;
  }
  if (record?.applied_at || record?.actual_effect_evaluated) return "applied";
  return "generated";
}

function formatHistoryState(value: RecommendationState): string {
  return value;
}

function readOptionalControlMode(record: AIRecommendationHistoryItem | null): string | null {
  if (!record) return null;
  const data = record as unknown as { current_control_mode?: unknown; control_mode?: unknown };
  if (typeof data.current_control_mode === "string" && data.current_control_mode.trim()) return data.current_control_mode;
  if (typeof data.control_mode === "string" && data.control_mode.trim()) return data.control_mode;
  return null;
}

function previewEmptyText(record: AIRecommendationHistoryItem): string {
  if (!record.actual_effect_evaluated) {
    return "Preview-vs-actual comparison requires completed actual post-apply evaluation.";
  }
  return "Preview-vs-actual comparison is unavailable because preview data is missing for this recommendation record.";
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (ch: string) => ch.toUpperCase());
}

function formatPercent(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "N/A";
  return `${(value * 100).toFixed(1)}%`;
}

function formatSeconds(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "N/A";
  return `${value.toFixed(0)}s`;
}

function withSign(value: number): string {
  const fixed = value.toFixed(4);
  return value > 0 ? `+${fixed}` : fixed;
}

type MetricDirection = "higher-better" | "lower-better";

type ComparisonMetricRow = {
  key: MetricKey;
  label: string;
  before: number | null;
  after: number | null;
  deltaRaw: number | null;
  result: "Improved" | "Worse" | "Unchanged";
};

const METRIC_META: Record<MetricKey, { label: string; direction: MetricDirection }> = {
  in_band_ratio: { label: "In-band Ratio", direction: "higher-better" },
  overshoot_c: { label: "Overshoot", direction: "lower-better" },
  settling_sec: { label: "Settling Time", direction: "lower-better" },
  mean_abs_error: { label: "Mean Abs Error", direction: "lower-better" },
  saturation_ratio: { label: "Saturation Ratio", direction: "lower-better" },
  temp_swing: { label: "Temp Swing", direction: "lower-better" },
};

function metricDirection(metricKey: MetricKey): MetricDirection {
  return METRIC_META[metricKey].direction;
}

function comparisonValueTone(result: "Improved" | "Worse" | "Unchanged"): string {
  if (result === "Improved") return "text-accent";
  if (result === "Worse") return "text-danger";
  return "text-mute";
}

function metricStatusByDirection(
  metricKey: MetricKey,
  deltaRaw: number | null
): "Improved" | "Worse" | "Unchanged" {
  if (deltaRaw == null || Number.isNaN(deltaRaw) || Math.abs(deltaRaw) < 0.0001) return "Unchanged";
  const direction = metricDirection(metricKey);
  if (direction === "higher-better") return deltaRaw > 0 ? "Improved" : "Worse";
  return deltaRaw < 0 ? "Improved" : "Worse";
}

function mixedDeltaFromComparison(comparison: AIPostEffectComparison, metricKey: MetricKey): number | null {
  if (metricKey === "in_band_ratio") return comparison.in_band_ratio_delta ?? null;
  if (metricKey === "overshoot_c") return comparison.overshoot_c_delta ?? null;
  if (metricKey === "settling_sec") return comparison.settling_sec_delta ?? null;
  if (metricKey === "mean_abs_error") return comparison.mean_abs_error_delta ?? null;
  if (metricKey === "saturation_ratio") return comparison.saturation_ratio_delta ?? null;
  return comparison.temp_swing_delta ?? null;
}

function afterValueFromSummary(
  summary: AIRecommendationHistoryItem["post_effect_summary"] | null | undefined,
  metricKey: MetricKey
): number | null {
  if (!summary) return null;
  if (metricKey === "in_band_ratio") return summary.in_band_ratio_after ?? null;
  if (metricKey === "overshoot_c") return summary.overshoot_c_after ?? null;
  if (metricKey === "settling_sec") return summary.settling_sec_after ?? null;
  if (metricKey === "mean_abs_error") return summary.mean_abs_error_after ?? null;
  if (metricKey === "saturation_ratio") return summary.saturation_ratio_after ?? null;
  return summary.temp_swing_after ?? null;
}

function rebuildReferenceFromMixedDelta(metricKey: MetricKey, after: number, mixedDelta: number): number {
  // Current backend compare semantics:
  // - in_band_ratio_delta = actual - reference
  // - other deltas = reference - actual
  if (metricKey === "in_band_ratio") return after - mixedDelta;
  return after + mixedDelta;
}

function buildComparisonRows(
  comparison?: AIPostEffectComparison | null,
  actualSummary?: AIRecommendationHistoryItem["post_effect_summary"] | null
): ComparisonMetricRow[] | null {
  if (!comparison || !actualSummary) return null;
  const keys: MetricKey[] = ["in_band_ratio", "overshoot_c", "settling_sec", "mean_abs_error", "saturation_ratio", "temp_swing"];
  const rows: ComparisonMetricRow[] = [];
  for (const key of keys) {
    const after = afterValueFromSummary(actualSummary, key);
    const mixedDelta = mixedDeltaFromComparison(comparison, key);
    if (after == null || mixedDelta == null || Number.isNaN(after) || Number.isNaN(mixedDelta)) {
      rows.push({ key, label: METRIC_META[key].label, before: null, after: null, deltaRaw: null, result: "Unchanged" });
      continue;
    }
    const reference = rebuildReferenceFromMixedDelta(key, after, mixedDelta);
    const deltaRaw = after - reference;
    rows.push({
      key,
      label: METRIC_META[key].label,
      before: reference,
      after,
      deltaRaw,
      result: metricStatusByDirection(key, deltaRaw),
    });
  }
  return rows;
}

function formatMetricValue(value: number | null, metricKey: MetricKey): string {
  if (value == null || Number.isNaN(value)) return "N/A";
  if (metricKey === "in_band_ratio" || metricKey === "saturation_ratio") return `${(value * 100).toFixed(1)}%`;
  if (metricKey === "settling_sec") return `${value.toFixed(1)}s`;
  return `${value.toFixed(3)}°C`;
}

function formatMetricDelta(value: number | null, metricKey: MetricKey): string {
  if (value == null || Number.isNaN(value)) return "N/A";
  const prefix = value > 0 ? "+" : "";
  if (metricKey === "in_band_ratio" || metricKey === "saturation_ratio") return `${prefix}${(value * 100).toFixed(2)}%`;
  if (metricKey === "settling_sec") return `${prefix}${value.toFixed(1)}s`;
  return `${prefix}${value.toFixed(3)}°C`;
}

function summarizeComparisonOverall(
  mode: "before-after" | "preview-actual",
  rows: ComparisonMetricRow[]
): { headline: string; reason: string } {
  const available = rows.filter((row) => row.deltaRaw != null) as Array<ComparisonMetricRow & { deltaRaw: number }>;
  if (available.length === 0) return { headline: "No comparable metrics available.", reason: "" };

  const improved = available.filter((row) => row.result === "Improved");
  const worse = available.filter((row) => row.result === "Worse");
  const score = available.reduce((sum, row) => sum + signedMetricImpact(row.key, row.deltaRaw), 0);

  if (mode === "preview-actual") {
    const gapScore = available.reduce((sum, row) => sum + Math.abs(normalizedMetricDelta(row.key, row.deltaRaw)), 0) / available.length;
    const gapLevel = gapScore <= 0.35 ? "Low" : gapScore <= 0.9 ? "Medium" : "High";
    const reason =
      worse.length === 0
        ? "Actual behavior aligned with preview on most metrics."
        : `Largest gap: ${topMetricNames(worse.map((row) => ({ key: row.key, magnitude: Math.abs(normalizedMetricDelta(row.key, row.deltaRaw)) })))}.`;
    return { headline: `Prediction Gap: ${gapLevel}.`, reason };
  }

  if (score > 0.2) {
    const reason =
      worse.length === 0
        ? "Improvements were consistent across all available metrics."
        : `Dominant negatives: ${topMetricNames(worse.map((row) => ({ key: row.key, magnitude: Math.abs(normalizedMetricDelta(row.key, row.deltaRaw)) })))}.`;
    return { headline: "Overall Result: Improved real-device behavior after apply.", reason };
  }
  if (score < -0.2) {
    const reason =
      improved.length === 0
        ? `Main degradation came from ${topMetricNames(worse.map((row) => ({ key: row.key, magnitude: Math.abs(normalizedMetricDelta(row.key, row.deltaRaw)) })))}.`
        : `Main improvement came from ${topMetricNames(improved.map((row) => ({ key: row.key, magnitude: Math.abs(normalizedMetricDelta(row.key, row.deltaRaw)) })))} but was outweighed by ${topMetricNames(worse.map((row) => ({ key: row.key, magnitude: Math.abs(normalizedMetricDelta(row.key, row.deltaRaw)) })))}.`;
    return { headline: "Overall Result: Worse real-device behavior after apply.", reason };
  }
  return {
    headline: "Overall Result: No significant before-vs-after change detected.",
    reason: "Improvements and degradations were mixed and near-balanced.",
  };
}

function normalizedMetricDelta(metricKey: MetricKey, deltaRaw: number): number {
  if (metricKey === "in_band_ratio" || metricKey === "saturation_ratio") return deltaRaw * 100;
  if (metricKey === "settling_sec") return deltaRaw / 20;
  return deltaRaw;
}

function signedMetricImpact(metricKey: MetricKey, deltaRaw: number): number {
  const direction = metricDirection(metricKey);
  const normalized = normalizedMetricDelta(metricKey, deltaRaw);
  return direction === "higher-better" ? normalized : -normalized;
}

function topMetricNames(entries: Array<{ key: MetricKey; magnitude: number }>): string {
  if (entries.length === 0) return "none";
  const top = [...entries].sort((a, b) => b.magnitude - a.magnitude).slice(0, 3);
  return top.map((entry) => METRIC_META[entry.key].label.toLowerCase()).join(", ");
}

function buildTelemetryChartRows(comparison: AITelemetryComparison | null): TelemetryChartRow[] {
  if (!comparison) return [];
  const map = new Map<string, TelemetryChartRow>();

  function ensureRow(xMin: number): TelemetryChartRow {
    const key = xMin.toFixed(4);
    const existing = map.get(key);
    if (existing) return existing;
    const created: TelemetryChartRow = { xMin };
    map.set(key, created);
    return created;
  }

  for (const point of comparison.baseline_curve ?? []) {
    const row = ensureRow(Number(point.relative_time_min.toFixed(4)));
    row.baseline = point.temp;
  }
  for (const point of comparison.preview_curve ?? []) {
    const row = ensureRow(Number(point.relative_time_min.toFixed(4)));
    row.preview = point.temp;
  }
  for (const point of comparison.actual_curve ?? []) {
    const row = ensureRow(Number(point.relative_time_min.toFixed(4)));
    row.actual = point.temp;
  }

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  for (const row of map.values()) {
    minX = Math.min(minX, row.xMin);
    maxX = Math.max(maxX, row.xMin);
  }
  if (!Number.isFinite(minX) || !Number.isFinite(maxX)) {
    minX = -Math.max(1, comparison.baseline_window_minutes);
    maxX = Math.max(1, comparison.observation_window_minutes);
    ensureRow(minX);
    ensureRow(maxX);
  }
  if (comparison.target_temp != null) {
    ensureRow(minX).target = comparison.target_temp;
    ensureRow(maxX).target = comparison.target_temp;
    for (const row of map.values()) row.target = comparison.target_temp;
  }

  return [...map.values()].sort((a, b) => a.xMin - b.xMin);
}

function formatRelativeMinuteLabel(value: number): string {
  const rounded = Math.round(value);
  if (rounded > 0) return `+${rounded}m`;
  if (rounded < 0) return `${rounded}m`;
  return "0m";
}

function seriesLabel(key: string | number): string {
  if (key === "baseline") return "Baseline";
  if (key === "preview") return "Preview";
  if (key === "actual") return "Actual";
  if (key === "target") return "Target";
  return String(key);
}

function buildTimeRange(timePreset: TimePreset, customStart: string, customEnd: string): { startMs?: number; endMs?: number } {
  const now = Date.now();
  if (timePreset === "30m") return { startMs: now - 30 * 60 * 1000, endMs: now };
  if (timePreset === "1h") return { startMs: now - 60 * 60 * 1000, endMs: now };
  if (timePreset === "3h") return { startMs: now - 3 * 60 * 60 * 1000, endMs: now };
  if (timePreset === "24h") return { startMs: now - 24 * 60 * 60 * 1000, endMs: now };
  if (timePreset === "7d") return { startMs: now - 7 * 24 * 60 * 60 * 1000, endMs: now };
  if (timePreset === "30d") return { startMs: now - 30 * 24 * 60 * 60 * 1000, endMs: now };
  const parsedStart = parseDatetimeLocalToMs(customStart);
  const parsedEnd = parseDatetimeLocalToMs(customEnd);
  if (parsedStart == null || parsedEnd == null || parsedStart > parsedEnd) {
    return { startMs: undefined, endMs: undefined };
  }
  return { startMs: parsedStart, endMs: parsedEnd };
}

function toObservationWindowMinutes(timeRange: { startMs?: number; endMs?: number }): number {
  if (typeof timeRange.startMs !== "number" || typeof timeRange.endMs !== "number") return 180;
  const minutes = Math.round((timeRange.endMs - timeRange.startMs) / (60 * 1000));
  if (!Number.isFinite(minutes) || minutes <= 0) return 1;
  return Math.max(1, Math.min(180, minutes));
}

function parseDatetimeLocalToMs(value: string): number | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.getTime();
}

function toDatetimeLocalValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}
