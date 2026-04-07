import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Link2, Search } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useDevices } from "@/routes/use-data";
import type { AIPostEffectComparison, AIRecommendationHistoryItem, AIRecommendationHistoryResponse } from "@/types";
type TimePreset = "30m" | "1h" | "3h" | "24h" | "7d" | "30d" | "custom";

export function AIPage() {
  const { devices } = useDevices();
  const [windowData, setWindowData] = useState<AIRecommendationHistoryResponse | null>(null);
  const [historyData, setHistoryData] = useState<AIRecommendationHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [devicePickerOpen, setDevicePickerOpen] = useState(false);
  const [devicePickerQuery, setDevicePickerQuery] = useState("");
  const [timePreset, setTimePreset] = useState<TimePreset>("30m");
  const [customStart, setCustomStart] = useState(() => toDatetimeLocalValue(new Date(Date.now() - 60 * 60 * 1000)));
  const [customEnd, setCustomEnd] = useState(() => toDatetimeLocalValue(new Date()));
  const [busy, setBusy] = useState(false);
  const devicePickerRef = useRef<HTMLDivElement>(null);

  const timeRange = useMemo(() => buildTimeRange(timePreset, customStart, customEnd), [timePreset, customStart, customEnd]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [windowNext, historyNext] = await Promise.all([
        api.aiRecommendationHistory({
          limit: 200,
          start_ms: timeRange.startMs,
          end_ms: timeRange.endMs,
        }),
        api.aiRecommendationHistory({
          limit: 500,
        }),
      ]);
      setWindowData(windowNext);
      setHistoryData(historyNext);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [timeRange.startMs, timeRange.endMs]);

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
    return selectedDeviceRecords.find((item) => item.history_state === "applied") ?? selectedDeviceRecords[0] ?? null;
  }, [selectedDeviceRecords]);

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

  async function handleEvaluate() {
    if (!currentRecord || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.evaluateAiRecommendationActual(currentRecord.device_id, currentRecord.recommendation_id, {
        observation_window_minutes: toObservationWindowMinutes(timeRange),
      });
      await load();
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setBusy(false);
    }
  }

  function selectDevice(deviceId: number) {
    setSelectedDeviceId(deviceId);
    setDevicePickerOpen(false);
    setDevicePickerQuery("");
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
                  ["Problem", formatLabel(currentRecord.problem_type)],
                  ["Expected Effect", currentRecord.expected_effect ? formatLabel(currentRecord.expected_effect) : "-"],
                  ["Risk", currentRecord.risk_level ?? "-"],
                  ["Outcome", formatLabel(currentRecord.effect_outcome)],
                  ["Applied Record Time", formatDateTime(currentRecord.generated_at)],
                  ["History State", currentRecord.history_state ?? "-"],
                ]}
              />
              <ParamBlock title="Current Params" params={currentRecord.current_params} />
              <ParamBlock title="Recommended / Delta" params={currentRecord.recommended_params} delta={currentRecord.delta} />
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
                    disabled={busy || currentRecord.history_state !== "applied"}
                  >
                    {busy ? "Evaluating..." : "Evaluate Actual Effect"}
                  </Button>
                  <Button size="sm" variant="ghost" asChild>
                    <Link to={`/devices/${currentRecord.device_id}`}>
                      <Link2 className="mr-1 h-4 w-4" />
                      Open Device
                    </Link>
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <MetricsBlock
                title="Actual Effect Summary"
                emptyText="Run actual effect evaluation to compare post-apply telemetry against the pre-apply baseline."
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
              <ComparisonBlock title="Before vs After" comparison={currentRecord.comparison_to_before} />
              <ComparisonBlock title="Preview vs Actual" comparison={currentRecord.comparison_to_preview} />
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
}: {
  title: string;
  params?: { kp: number; ki: number; kd: number } | null;
  delta?: { kp: number; ki: number; kd: number } | null;
}) {
  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">{title}</div>
      {!params ? (
        <div className="mt-2 text-xs text-mute">No parameter snapshot available.</div>
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
        </div>
      )}
    </div>
  );
}

function MetricsBlock({
  title,
  metrics,
  emptyText,
}: {
  title: string;
  metrics: [string, string][] | null;
  emptyText: string;
}) {
  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">{title}</div>
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

function ComparisonBlock({ title, comparison }: { title: string; comparison?: AIPostEffectComparison | null }) {
  const rows: [string, number | null | undefined, "ratio" | "temp" | "sec"][] = [
    ["In-band Ratio", comparison?.in_band_ratio_delta, "ratio"],
    ["Overshoot", comparison?.overshoot_c_delta, "temp"],
    ["Settling Time", comparison?.settling_sec_delta, "sec"],
    ["Mean Abs Error", comparison?.mean_abs_error_delta, "temp"],
    ["Saturation Ratio", comparison?.saturation_ratio_delta, "ratio"],
    ["Temp Swing", comparison?.temp_swing_delta, "temp"],
  ];
  return (
    <div className="rounded-xl border border-line/70 bg-panel px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-neon/80">{title}</div>
      {!comparison ? (
        <div className="mt-2 text-xs text-mute">No comparison available yet.</div>
      ) : (
        <div className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map(([label, value, kind]) => (
            <div key={label} className="rounded border border-line/60 bg-panel2 px-2 py-1 text-xs">
              <div className="text-mute">{label}</div>
              <div className={`mt-0.5 font-semibold ${deltaTone(value)}`}>{formatDelta(value, kind)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function normalizeError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Request failed";
}

function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
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

function deltaTone(value?: number | null): string {
  if (value == null || Math.abs(value) < 0.0001) return "text-mute";
  return value > 0 ? "text-accent" : "text-danger";
}

function formatDelta(value: number | null | undefined, kind: "ratio" | "temp" | "sec"): string {
  if (value == null || Number.isNaN(value)) return "N/A";
  const prefix = value > 0 ? "+" : "";
  if (kind === "ratio") return `${prefix}${(value * 100).toFixed(2)}%`;
  if (kind === "sec") return `${prefix}${value.toFixed(1)}s`;
  return `${prefix}${value.toFixed(3)}°C`;
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
