import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { CheckCircle2, ChevronDown, Gauge, Search, SlidersHorizontal, Target, Waves } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useDeviceDetail } from "@/routes/use-data";
import type { Device } from "@/types";

type TargetConfig = {
  band: number;
  pwmThreshold: number;
  saturationWarn: number;
  saturationHigh: number;
  overshootLimit: number;
  steadyWindow: number;
};

const DEFAULT_TARGET_CONFIG: TargetConfig = {
  band: 0.5,
  pwmThreshold: 85,
  saturationWarn: 0.3,
  saturationHigh: 0.6,
  overshootLimit: 3,
  steadyWindow: 12,
};

type EffectState = "Pending" | "Improved" | "No Change" | "Worse";
type TargetResult = "On Target" | "Critical" | "Not Met";
type EvalStatus = "Pass" | "Warn" | "Fail";
type HistoryRangePreset = "2h" | "6h" | "24h" | "custom";

export function DeviceDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const canWrite = hasRole("admin", "operator");
  const deviceId = Number(id);

  const { device, metrics, parameters, recommendation, loading, reload, updateParameters } = useDeviceDetail(deviceId);

  const [editing, setEditing] = useState({ kp: "", ki: "", kd: "", target_temp: "", control_mode: "" });
  const [feedback, setFeedback] = useState({
    lastUpdate: "-",
    ackStatus: "Acked",
    appliedStatus: "Applied",
    effect: "No Change" as EffectState,
  });

  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerItems, setPickerItems] = useState<Device[]>([]);
  const [targetConfig, setTargetConfig] = useState<TargetConfig>(DEFAULT_TARGET_CONFIG);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmIntent, setConfirmIntent] = useState<"full" | "targets">("full");
  const [targetEvalOpen, setTargetEvalOpen] = useState(false);
  const [historyRangePreset, setHistoryRangePreset] = useState<HistoryRangePreset>("6h");
  const [historyCustomStart, setHistoryCustomStart] = useState(() =>
    toDatetimeLocalValue(new Date(Date.now() - 6 * 60 * 60 * 1000))
  );
  const [historyCustomEnd, setHistoryCustomEnd] = useState(() => toDatetimeLocalValue(new Date()));

  useEffect(() => {
    if (!parameters) return;
    setTargetConfig({
      band: parameters.target_band,
      overshootLimit: parameters.overshoot_limit_pct,
      saturationWarn: parameters.saturation_warn_ratio,
      saturationHigh: parameters.saturation_high_ratio,
      pwmThreshold: parameters.pwm_saturation_threshold,
      steadyWindow: parameters.steady_window_samples,
    });
  }, [parameters]);

  useEffect(() => {
    if (!pickerOpen) return;
    const q = pickerQuery.trim();
    if (q.length < 1) {
      setPickerItems(device ? [device] : []);
      return;
    }
    const timer = setTimeout(() => {
      setPickerLoading(true);
      api.devicesManage({ q, page: 1, page_size: 20 })
        .then((res) => setPickerItems(res.items))
        .finally(() => setPickerLoading(false));
    }, 240);
    return () => clearTimeout(timer);
  }, [pickerOpen, pickerQuery, device]);

  const evalSnapshot = useMemo(() => {
    const latest = metrics.length ? metrics[metrics.length - 1] : null;
    return {
      currentTemp: latest?.current_temp ?? device?.current_temp ?? 0,
      targetTemp: latest?.target_temp ?? device?.target_temp ?? 0,
    };
  }, [metrics, device]);

  const derived = useMemo(() => {
    if (!metrics.length || !device) {
      return {
        error: 0,
        inBand: false,
        steady: false,
        steadyWindowSamples: 0,
        observedSettlingSec: null as number | null,
        overshootPct: 0,
        saturationRatio: 0,
        saturationRisk: "Low",
        tuneAdvice: "Keep",
        result: "Critical" as TargetResult,
        steadyStartIdx: -1,
      };
    }

    const error = evalSnapshot.currentTemp - evalSnapshot.targetTemp;
    const inBand = Math.abs(error) <= targetConfig.band;
    const steadyWindow = metrics.slice(-targetConfig.steadyWindow);

    const overshootPct = metrics
      .map((m) => Math.max(0, ((m.current_temp - m.target_temp) / Math.max(m.target_temp, 0.001)) * 100))
      .reduce((a, b) => Math.max(a, b), 0);

    const saturationRatio = steadyWindow.filter((m) => m.pwm_output >= targetConfig.pwmThreshold).length / Math.max(steadyWindow.length, 1);
    const saturationRisk =
      saturationRatio >= targetConfig.saturationHigh ? "High" : saturationRatio >= targetConfig.saturationWarn ? "Medium" : "Low";

    const steady = steadyWindow.length > 0 && steadyWindow.every((m) => Math.abs(m.error) <= targetConfig.band);
    const steadyStartIdx = steady ? Math.max(0, metrics.length - steadyWindow.length) : -1;
    let settleIdx = -1;
    for (let i = 0; i < metrics.length; i += 1) {
      const tailInBand = metrics.slice(i).every((m) => Math.abs(m.error) <= targetConfig.band);
      if (tailInBand) {
        settleIdx = i;
        break;
      }
    }
    const observedSettlingSec =
      settleIdx > 0
        ? Math.max(0, (new Date(metrics[settleIdx].timestamp).getTime() - new Date(metrics[0].timestamp).getTime()) / 1000)
        : null;
    const tuneAdvice = inBand && steady && saturationRisk === "Low" ? "Keep" : "Tune";

    let result: TargetResult = "Not Met";
    if (inBand && steady && saturationRisk === "Low") result = "On Target";
    else if (inBand || saturationRisk !== "High") result = "Critical";

    return {
      error,
      inBand,
      steady,
      steadyWindowSamples: steadyWindow.length,
      observedSettlingSec,
      overshootPct,
      saturationRatio,
      saturationRisk,
      tuneAdvice,
      result,
      steadyStartIdx,
    };
  }, [device, metrics, targetConfig, evalSnapshot]);

  const chartData = useMemo(
    () =>
      metrics.map((m, idx) => ({
        idx,
        t: new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        temp: m.current_temp,
        target: m.target_temp,
      })),
    [metrics]
  );

  const targetTemp = evalSnapshot.targetTemp;
  const latestPwm = metrics[metrics.length - 1]?.pwm_output ?? device?.pwm_output ?? 0;
  const historyRangeMetrics = useMemo(() => {
    if (!metrics.length) return [];

    const now = Date.now();
    let startMs = 0;
    let endMs = now;
    if (historyRangePreset === "2h") startMs = now - 2 * 60 * 60 * 1000;
    if (historyRangePreset === "6h") startMs = now - 6 * 60 * 60 * 1000;
    if (historyRangePreset === "24h") startMs = now - 24 * 60 * 60 * 1000;
    if (historyRangePreset === "custom") {
      const parsedStart = new Date(historyCustomStart).getTime();
      const parsedEnd = new Date(historyCustomEnd).getTime();
      if (!Number.isFinite(parsedStart) || !Number.isFinite(parsedEnd) || parsedStart >= parsedEnd) return [];
      startMs = parsedStart;
      endMs = parsedEnd;
    }

    return metrics.filter((m) => {
      const ts = new Date(m.timestamp).getTime();
      return ts >= startMs && ts <= endMs;
    });
  }, [historyRangePreset, historyCustomEnd, historyCustomStart, metrics]);

  const historyRangeStats = useMemo(() => {
    const points = historyRangeMetrics;
    if (points.length < 2) {
      return {
        samples: points.length,
        inBandRatio: 0,
        totalStableSec: 0,
        longestStableSec: 0,
        sinceLastStableSec: null as number | null,
        hasStableWindow: false,
      };
    }

    const stepSec = Math.max(
      1,
      Math.round(
        points
          .slice(1)
          .map((p, idx) => (new Date(p.timestamp).getTime() - new Date(points[idx].timestamp).getTime()) / 1000)
          .reduce((sum, x) => sum + Math.max(0, x), 0) / Math.max(1, points.length - 1)
      )
    );

    let inBandCount = 0;
    let totalStableSec = 0;
    let longestStableSec = 0;
    let lastStableEndMs: number | null = null;
    let runStart = -1;

    for (let i = 0; i < points.length; i += 1) {
      const inBand = Math.abs(points[i].error) <= targetConfig.band;
      if (inBand) {
        inBandCount += 1;
        if (runStart < 0) runStart = i;
      } else if (runStart >= 0) {
        const runLen = i - runStart;
        if (runLen >= targetConfig.steadyWindow) {
          const startMs = new Date(points[runStart].timestamp).getTime();
          const endMs = new Date(points[i - 1].timestamp).getTime();
          const sec = Math.max(stepSec, Math.round((endMs - startMs) / 1000) + stepSec);
          totalStableSec += sec;
          if (sec > longestStableSec) longestStableSec = sec;
          lastStableEndMs = endMs;
        }
        runStart = -1;
      }
    }

    if (runStart >= 0) {
      const runLen = points.length - runStart;
      if (runLen >= targetConfig.steadyWindow) {
        const startMs = new Date(points[runStart].timestamp).getTime();
        const endMs = new Date(points[points.length - 1].timestamp).getTime();
        const sec = Math.max(stepSec, Math.round((endMs - startMs) / 1000) + stepSec);
        totalStableSec += sec;
        if (sec > longestStableSec) longestStableSec = sec;
        lastStableEndMs = endMs;
      }
    }

    return {
      samples: points.length,
      inBandRatio: inBandCount / points.length,
      totalStableSec,
      longestStableSec,
      sinceLastStableSec: lastStableEndMs ? Math.max(0, Math.round((Date.now() - lastStableEndMs) / 1000)) : null,
      hasStableWindow: totalStableSec > 0,
    };
  }, [historyRangeMetrics, targetConfig.band, targetConfig.steadyWindow]);
  const targetEvalRows = useMemo(
    () => [
      {
        key: "temperature_band",
        title: "Temperature Band",
        field: "target_band",
        target: `±${targetConfig.band.toFixed(2)}°C`,
        current: `${Math.abs(derived.error).toFixed(2)}°C error`,
        rule: `|error| <= ${targetConfig.band.toFixed(2)}°C`,
        why: derived.inBand ? "Current error is within allowed band." : "Current error exceeds allowed band.",
        status: (derived.inBand ? "Pass" : Math.abs(derived.error) <= targetConfig.band * 1.5 ? "Warn" : "Fail") as EvalStatus,
      },
      {
        key: "steady_state",
        title: "Steady State",
        field: "steady_window_samples",
        target: `${targetConfig.steadyWindow} samples in band`,
        current: `${derived.steadyWindowSamples}/${targetConfig.steadyWindow} samples in band`,
        rule: `All last ${targetConfig.steadyWindow} samples must stay in band`,
        why: derived.steady ? "Recent samples are stable in target band." : "Recent samples still fluctuate outside band.",
        status: (derived.steady ? "Pass" : derived.inBand ? "Warn" : "Fail") as EvalStatus,
      },
      {
        key: "overshoot_limit",
        title: "Overshoot",
        field: "overshoot_limit_pct",
        target: `<= ${targetConfig.overshootLimit.toFixed(1)}%`,
        current: `${derived.overshootPct.toFixed(2)}%`,
        rule: `Max overshoot <= ${targetConfig.overshootLimit.toFixed(1)}%`,
        why: derived.overshootPct <= targetConfig.overshootLimit ? "Overshoot is under configured limit." : "Overshoot is above configured limit.",
        status:
          (derived.overshootPct <= targetConfig.overshootLimit
            ? "Pass"
            : derived.overshootPct <= targetConfig.overshootLimit * 1.3
              ? "Warn"
              : "Fail") as EvalStatus,
      },
      {
        key: "saturation_ratio",
        title: "Saturation Risk",
        field: "pwm_saturation_threshold + saturation ratios",
        target: `Warn>=${targetConfig.saturationWarn.toFixed(2)}, High>=${targetConfig.saturationHigh.toFixed(2)}`,
        current: `${derived.saturationRatio.toFixed(2)} (Latest PWM Snapshot ${latestPwm.toFixed(1)}%)`,
        rule: `ratio=(samples PWM>=${targetConfig.pwmThreshold.toFixed(0)}%) / window`,
        why:
          derived.saturationRisk === "Low"
            ? "PWM saturation usage is low."
            : derived.saturationRisk === "Medium"
              ? "Saturation trend is rising; monitor closely."
              : "Saturation risk is high and may limit control authority.",
        status: (derived.saturationRisk === "Low" ? "Pass" : derived.saturationRisk === "Medium" ? "Warn" : "Fail") as EvalStatus,
      },
    ],
    [derived, latestPwm, targetConfig]
  );
  const yDomain = useMemo<[number, number]>(() => {
    if (!chartData.length) return [targetTemp - 1, targetTemp + 1];

    const values = chartData.map((d) => d.temp);
    values.push(targetTemp - targetConfig.band, targetTemp + targetConfig.band);
    let min = Math.min(...values);
    let max = Math.max(...values);

    const span = max - min;
    const minSpan = Math.max(1.6, targetConfig.band * 4);
    if (span < minSpan) {
      const pad = (minSpan - span) / 2;
      min -= pad;
      max += pad;
    }
    const margin = Math.max(0.18, (max - min) * 0.12);
    return [Number((min - margin).toFixed(2)), Number((max + margin).toFixed(2))];
  }, [chartData, targetTemp, targetConfig.band]);

  if (loading) return <p className="text-sm text-mute">Loading device detail...</p>;
  if (!device || !parameters) return <p className="text-sm text-danger">Device not found or no permission.</p>;

  async function saveParameters(e: FormEvent) {
    e.preventDefault();
    if (!canWrite || confirmBusy) return;
    setConfirmIntent("full");
    setConfirmOpen(true);
  }

  async function executeSaveParameters() {
    if (!canWrite) return;
    const snapshot = device;
    if (!snapshot) return;

    const prevErr = Math.abs(snapshot.current_temp - snapshot.target_temp);
    setFeedback({
      lastUpdate: new Date().toLocaleTimeString(),
      ackStatus: "Acked",
      appliedStatus: "Pending",
      effect: "Pending",
    });

    if (editing.target_temp) {
      await api.updateDevice(deviceId, { target_temp: Number(editing.target_temp) });
    }

    await updateParameters({
      kp: editing.kp ? Number(editing.kp) : undefined,
      ki: editing.ki ? Number(editing.ki) : undefined,
      kd: editing.kd ? Number(editing.kd) : undefined,
      control_mode: editing.control_mode || undefined,
      target_band: targetConfig.band,
      overshoot_limit_pct: targetConfig.overshootLimit,
      saturation_warn_ratio: targetConfig.saturationWarn,
      saturation_high_ratio: targetConfig.saturationHigh,
      pwm_saturation_threshold: targetConfig.pwmThreshold,
      steady_window_samples: targetConfig.steadyWindow,
    });
    setEditing({ kp: "", ki: "", kd: "", target_temp: "", control_mode: "" });
    await reload();
    const after = await api.device(deviceId);
    const nextErr = Math.abs(after.current_temp - after.target_temp);
    const effect: EffectState = nextErr < prevErr ? "Improved" : nextErr > prevErr ? "Worse" : "No Change";
    setFeedback({
      lastUpdate: new Date().toLocaleTimeString(),
      ackStatus: "Acked",
      appliedStatus: "Applied",
      effect,
    });
  }

  async function executeSaveTargetsOnly() {
    if (!canWrite) return;
    await updateParameters({
      target_band: targetConfig.band,
      overshoot_limit_pct: targetConfig.overshootLimit,
      saturation_warn_ratio: targetConfig.saturationWarn,
      saturation_high_ratio: targetConfig.saturationHigh,
      pwm_saturation_threshold: targetConfig.pwmThreshold,
      steady_window_samples: targetConfig.steadyWindow,
    });
    await reload();
    setFeedback((prev) => ({
      ...prev,
      lastUpdate: new Date().toLocaleTimeString(),
      ackStatus: "Acked",
      appliedStatus: "Applied",
    }));
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="py-2">
          <div className="grid gap-2 lg:grid-cols-[1.2fr_1fr_auto_auto_auto] lg:items-center">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-neon">{device.name}</div>
              <div className="truncate text-xs text-mute">{device.code} · {device.line} · {device.location}</div>
            </div>

            <DeviceSearchSelect
              open={pickerOpen}
              setOpen={setPickerOpen}
              query={pickerQuery}
              setQuery={setPickerQuery}
              loading={pickerLoading}
              current={device}
              items={pickerItems}
              onSelect={(next) => {
                setPickerOpen(false);
                setPickerQuery("");
                navigate(`/devices/${next.id}`);
              }}
            />

            <SignalBox label="Control" value={parameters.control_mode} tone="text-neon" />
            <SignalBox label="Comm" value={device.is_online ? "Online" : "Offline"} tone={device.is_online ? "text-accent" : "text-danger"} />
            <Button className="h-9 px-3 text-xs" variant="ghost" onClick={() => navigate(`/history?deviceId=${device.id}`)}>
              View History
            </Button>
          </div>
        </CardContent>
      </Card>

      <ControlStatusBar
        result={derived.result}
        error={derived.error}
        inBand={derived.inBand}
        steady={derived.steady}
        saturationRisk={derived.saturationRisk}
        tuneAdvice={derived.tuneAdvice}
        targetBand={targetConfig.band}
      />

      <div className="grid gap-3 xl:grid-cols-[2.4fr_1fr] xl:items-start">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle>Control Performance Trend (Live)</CardTitle>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-mute">
              <InlineRefTag label={`Band ±${targetConfig.band.toFixed(1)}°C`} />
              <InlineRefTag label={`Overshoot ≤ ${targetConfig.overshootLimit.toFixed(1)}%`} />
              <InlineRefTag
                label={`Settling (Recent): ${derived.observedSettlingSec ? `${Math.round(derived.observedSettlingSec)}s` : "N/A"}`}
                weak
              />
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="mb-3 rounded border border-line/70 bg-panel2 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold text-text">Control Target History Window</div>
                <div className="text-xs text-mute">Evaluate stability over selected range</div>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2">
                {(["2h", "6h", "24h", "custom"] as HistoryRangePreset[]).map((preset) => (
                  <Button
                    key={preset}
                    size="sm"
                    variant={historyRangePreset === preset ? "accent" : "ghost"}
                    className="h-8 px-3 text-xs"
                    onClick={() => setHistoryRangePreset(preset)}
                  >
                    {preset === "custom" ? "Custom" : `Last ${preset}`}
                  </Button>
                ))}
              </div>

              {historyRangePreset === "custom" && (
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <Input type="datetime-local" value={historyCustomStart} onChange={(e) => setHistoryCustomStart(e.target.value)} />
                  <Input type="datetime-local" value={historyCustomEnd} onChange={(e) => setHistoryCustomEnd(e.target.value)} />
                </div>
              )}

              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                <MetricCard title="Stable Time in Range" value={formatDuration(historyRangeStats.totalStableSec)} />
                <MetricCard
                  title="Since Last Stable"
                  value={historyRangeStats.sinceLastStableSec == null ? "N/A" : formatDuration(historyRangeStats.sinceLastStableSec)}
                />
                <MetricCard title="Longest Stable Run" value={formatDuration(historyRangeStats.longestStableSec)} />
                <MetricCard title="In-Band Ratio" value={`${(historyRangeStats.inBandRatio * 100).toFixed(1)}%`} />
              </div>

              <div className="mt-2 text-xs text-mute">
                Samples: {historyRangeStats.samples} · Rule: stable requires at least {targetConfig.steadyWindow} consecutive samples within ±
                {targetConfig.band.toFixed(2)}°C.
              </div>
            </div>

            <div className="relative h-[390px] w-full">
              <div className="pointer-events-none absolute right-3 top-3 z-10">
                <div
                  className={`max-w-[170px] rounded-md border px-2 py-1 text-[10px] leading-tight shadow-panel ${
                    derived.inBand ? "border-accent/50 bg-accent/10 text-accent" : "border-warn/50 bg-warn/10 text-warn"
                  }`}
                >
                  <div className="font-semibold leading-tight">{derived.inBand ? "IN BAND" : "OUT OF BAND"}</div>
                  <div>Error {derived.error >= 0 ? "+" : ""}{derived.error.toFixed(2)}°C</div>
                  <div className="text-[10px] text-mute">{derived.inBand ? "Tracking stable" : "Needs tuning"}</div>
                </div>
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 18, left: 2, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(41,240,255,0.13)" />
                  <ReferenceArea
                    y1={targetTemp - targetConfig.band}
                    y2={targetTemp + targetConfig.band}
                    fill="rgba(25,211,152,0.12)"
                    strokeOpacity={0}
                  />
                  <XAxis
                    dataKey="idx"
                    stroke="#7fa6b8"
                    tickFormatter={(v: number) => chartData[v]?.t ?? ""}
                    minTickGap={28}
                  />
                  <YAxis stroke="#7fa6b8" width={56} domain={yDomain} allowDecimals tickCount={6} />
                  <Tooltip
                    labelFormatter={(v) => `Time: ${chartData[Number(v)]?.t ?? ""}`}
                    contentStyle={{ background: "rgba(5, 24, 34, 0.95)", border: "1px solid rgba(41,240,255,0.35)", borderRadius: 8 }}
                    itemStyle={{ color: "#c7e4f1", fontSize: 12 }}
                    labelStyle={{ color: "#95c0d3", fontSize: 12 }}
                    cursor={{ stroke: "rgba(41,240,255,0.3)", strokeDasharray: "3 3" }}
                  />
                  <Line type="monotone" dataKey="temp" stroke="#29f0ff" strokeWidth={2.8} dot={false} />
                  <Line type="monotone" dataKey="target" stroke="#2ad4a0" strokeWidth={1.9} dot={false} />
                  <ReferenceDot
                    x={chartData.length - 1}
                    y={evalSnapshot.currentTemp}
                    r={6}
                    fill={derived.inBand ? "#19d398" : "#ffd166"}
                    stroke="#042a36"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-mute">
              <ChartLegend label="Actual Temp" sampleClass="bg-[#29f0ff]" />
              <ChartLegend label="Target Line" sampleClass="bg-[#2ad4a0]" />
              <ChartLegend label={`Target Band ±${targetConfig.band.toFixed(1)}°C`} sampleClass="bg-accent/35" />
            </div>

            <div className="mt-3 rounded border border-neon/40 bg-gradient-to-br from-panel2 to-panel p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold uppercase tracking-wide text-neon">AI Recommended Configuration</div>
                  <div className="text-xs text-mute">High-priority panel for suggestion, confidence, and execution workflow</div>
                </div>
                <span className="rounded border border-neon/40 bg-neon/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-neon">
                  AI Core Module
                </span>
              </div>

              <div className="mt-3 grid gap-2 lg:grid-cols-3">
                <div className="rounded border border-line/70 bg-panel px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wide text-mute">Insight</div>
                  <div className="mt-1 text-xs text-mute">
                    Reason: <span className="text-text">{recommendation?.reason ?? "Pending live recommendation data"}</span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Risk: <span className="text-text">{recommendation?.risk ?? "Not evaluated yet"}</span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Confidence:{" "}
                    <span className="text-accent">
                      {typeof recommendation?.confidence === "number" ? `${Math.round(recommendation.confidence * 100)}%` : "N/A"}
                    </span>
                  </div>
                </div>

                <div className="rounded border border-line/70 bg-panel px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wide text-mute">Proposed Parameter Set</div>
                  <div className="mt-1 text-xs text-mute">
                    Suggestion: <span className="text-accent">{recommendation?.suggestion ?? "Reserved for AI generated Kp/Ki/Kd/Target set"}</span>
                  </div>
                  <div className="mt-1 text-xs text-mute">Preset Slot: <span className="text-text">AI_SET_A</span></div>
                  <div className="mt-1 text-xs text-mute">Scope: <span className="text-text">Current device only</span></div>
                </div>

                <div className="rounded border border-line/70 bg-panel px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wide text-mute">Execution Pipeline</div>
                  <div className="mt-1 flex flex-wrap gap-1 text-[10px]">
                    <span className="rounded border border-line/70 px-1.5 py-0.5 text-mute">Preview</span>
                    <span className="rounded border border-line/70 px-1.5 py-0.5 text-mute">Confirm</span>
                    <span className="rounded border border-line/70 px-1.5 py-0.5 text-mute">Apply</span>
                    <span className="rounded border border-line/70 px-1.5 py-0.5 text-mute">Observe</span>
                  </div>
                  <div className="mt-2 text-xs text-mute">Reserved for one-click AI apply with closed-loop feedback.</div>
                </div>
              </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" disabled>
                Preview Impact
                </Button>
                <Button size="sm" variant="accent" disabled>
                  Apply AI Set
                </Button>
              </div>
            </div>

          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Parameter Closed Loop</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <SectionTitle title="Current Snapshot" />
            <MetricRow label="Current Temp" value={`${evalSnapshot.currentTemp.toFixed(2)}°C`} />
            <MetricRow label="Target Temp" value={`${evalSnapshot.targetTemp.toFixed(2)}°C`} tone="target" />
            <MetricRow label="Error" value={`${derived.error.toFixed(2)}°C`} />
            <MetricRow label="PWM" value={`${latestPwm.toFixed(1)}%`} />

            <SectionTitle title="Current Parameters" />
            <div className="grid grid-cols-3 gap-2">
              <MetricCard title="Kp" value={parameters.kp.toFixed(2)} />
              <MetricCard title="Ki" value={parameters.ki.toFixed(2)} />
              <MetricCard title="Kd" value={parameters.kd.toFixed(2)} />
            </div>
            <MetricRow label="Mode" value={parameters.control_mode} />

            <SectionTitle title="Update & Feedback" />
            <form className="space-y-2" onSubmit={saveParameters}>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  disabled={!canWrite}
                  placeholder={`Kp ${parameters.kp}`}
                  value={editing.kp}
                  onChange={(e) => setEditing((s) => ({ ...s, kp: e.target.value }))}
                />
                <Input
                  disabled={!canWrite}
                  placeholder={`Ki ${parameters.ki}`}
                  value={editing.ki}
                  onChange={(e) => setEditing((s) => ({ ...s, ki: e.target.value }))}
                />
                <Input
                  disabled={!canWrite}
                  placeholder={`Kd ${parameters.kd}`}
                  value={editing.kd}
                  onChange={(e) => setEditing((s) => ({ ...s, kd: e.target.value }))}
                />
                <Input
                  disabled={!canWrite}
                  type="number"
                  step="0.1"
                  placeholder={`Target Temp ${device.target_temp.toFixed(1)}°C`}
                  value={editing.target_temp}
                  onChange={(e) => setEditing((s) => ({ ...s, target_temp: e.target.value }))}
                />
              </div>
              <Select
                value={editing.control_mode || parameters.control_mode}
                onValueChange={(v) => setEditing((s) => ({ ...s, control_mode: v }))}
                disabled={!canWrite}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Control Mode" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PID">PID</SelectItem>
                  <SelectItem value="PI">PI</SelectItem>
                  <SelectItem value="P">P</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="accent" className="w-full" type="submit" disabled={!canWrite}>
                {canWrite ? "Send Parameter Update" : "Read-only Role"}
              </Button>
            </form>

            <div className="grid gap-2">
              <FeedbackRow label="Last Update" value={feedback.lastUpdate} />
              <FeedbackRow label="Ack Status" value={feedback.ackStatus} />
              <FeedbackRow label="Apply Status" value={feedback.appliedStatus} />
              <FeedbackRow label="Effect" value={feedback.effect} tone={feedbackTone(feedback.effect)} />
            </div>

            <SectionTitle title="Target Settings" />
            <div className="grid grid-cols-2 gap-2">
              <SmallNumberInput
                label="Band"
                value={targetConfig.band}
                step="0.1"
                onChange={(next) => setTargetConfig((s) => ({ ...s, band: next }))}
              />
              <SmallNumberInput
                label="Overshoot %"
                value={targetConfig.overshootLimit}
                step="0.1"
                onChange={(next) => setTargetConfig((s) => ({ ...s, overshootLimit: next }))}
              />
              <SmallNumberInput
                label="Sat Warn"
                value={targetConfig.saturationWarn}
                step="0.05"
                onChange={(next) => setTargetConfig((s) => ({ ...s, saturationWarn: next }))}
              />
              <SmallNumberInput
                label="Sat High"
                value={targetConfig.saturationHigh}
                step="0.05"
                onChange={(next) => setTargetConfig((s) => ({ ...s, saturationHigh: next }))}
              />
              <SmallNumberInput
                label="PWM Threshold %"
                value={targetConfig.pwmThreshold}
                step="1"
                onChange={(next) => setTargetConfig((s) => ({ ...s, pwmThreshold: Math.max(1, Math.round(next)) }))}
              />
              <SmallNumberInput
                label="Steady Window Samples"
                value={targetConfig.steadyWindow}
                step="1"
                onChange={(next) => setTargetConfig((s) => ({ ...s, steadyWindow: Math.max(1, Math.round(next)) }))}
              />
            </div>
            <Button
              variant="ghost"
              size="sm"
              disabled={!canWrite || confirmBusy}
              onClick={() => {
                setConfirmIntent("targets");
                setConfirmOpen(true);
              }}
            >
              Save Target Settings
            </Button>

            <div className="rounded border border-line/70 bg-panel2">
              <button
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-left"
                onClick={() => setTargetEvalOpen((s) => !s)}
              >
                <div className="text-xs font-semibold uppercase tracking-wide text-mute">Target Evaluation Details</div>
                <ChevronDown className={`h-4 w-4 text-mute transition-transform ${targetEvalOpen ? "rotate-180" : ""}`} />
              </button>
              {targetEvalOpen && (
                <div className="space-y-2 border-t border-line/70 p-2">
                  {targetEvalRows.map((row) => (
                    <TargetRuleCard
                      key={row.key}
                      title={row.title}
                      field={row.field}
                      target={row.target}
                      current={row.current}
                      rule={row.rule}
                      why={row.why}
                      status={row.status}
                    />
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title={confirmIntent === "targets" ? "Confirm Target Settings Save" : "Confirm Parameter Update"}
        description={
          confirmIntent === "targets"
            ? "Save control target thresholds to database?"
            : "Save current PID and control target settings to device parameters?"
        }
        confirmLabel={confirmIntent === "targets" ? "Save Targets" : "Apply Update"}
        busy={confirmBusy}
        onCancel={() => !confirmBusy && setConfirmOpen(false)}
        onConfirm={async () => {
          setConfirmBusy(true);
          try {
            if (confirmIntent === "targets") await executeSaveTargetsOnly();
            else await executeSaveParameters();
            setConfirmOpen(false);
          } finally {
            setConfirmBusy(false);
          }
        }}
      />
    </div>
  );
}

function DeviceSearchSelect({
  open,
  setOpen,
  query,
  setQuery,
  loading,
  current,
  items,
  onSelect,
}: {
  open: boolean;
  setOpen: (v: boolean) => void;
  query: string;
  setQuery: (v: string) => void;
  loading: boolean;
  current: Device;
  items: Device[];
  onSelect: (d: Device) => void;
}) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const canNavigate = query.trim().length > 0 && items.length > 0;

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapperRef.current) return;
      const target = e.target as Node | null;
      if (target && !wrapperRef.current.contains(target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open, setOpen]);

  useEffect(() => {
    setHighlightedIndex(0);
  }, [query, items, open]);

  function onInputKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || !canNavigate) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev + 1) % items.length);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev - 1 + items.length) % items.length);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const next = items[highlightedIndex];
      if (next) onSelect(next);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  }

  return (
    <div ref={wrapperRef} className="relative min-w-[290px]">
      <button
        type="button"
        className="flex h-9 w-full items-center justify-between rounded-md border border-line bg-panel2 px-3 text-sm text-text"
        onClick={() => setOpen(!open)}
      >
        <span className="truncate">{current.name}</span>
        <ChevronDown className="h-4 w-4 text-mute" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-full rounded-md border border-line bg-panel p-2 shadow-panel">
          <div className="mb-2 flex items-center gap-2">
            <Search className="h-4 w-4 text-mute" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onInputKeyDown}
              placeholder="Search device name/code..."
              className="h-8"
            />
          </div>
          <div className="max-h-52 space-y-1 overflow-auto">
            {loading && <p className="px-2 py-1 text-xs text-mute">Searching...</p>}
            {!loading && query.trim().length === 0 && <p className="px-2 py-1 text-xs text-mute">Type keywords to search devices</p>}
            {!loading && query.trim().length > 0 && items.length === 0 && <p className="px-2 py-1 text-xs text-mute">No match</p>}
            {items.map((item, idx) => (
              <button
                key={item.id}
                type="button"
                className={`w-full rounded px-2 py-2 text-left text-sm ${
                  idx === highlightedIndex
                    ? "bg-neon/15 text-neon"
                    : item.id === current.id
                      ? "bg-neon/10 text-neon"
                      : "text-text hover:bg-white/5"
                }`}
                onMouseEnter={() => setHighlightedIndex(idx)}
                onClick={() => onSelect(item)}
              >
                <div className="truncate">{item.name}</div>
                <div className="truncate text-xs text-mute">{item.code} · {item.line}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ControlStatusBar({
  result,
  error,
  inBand,
  steady,
  saturationRisk,
  tuneAdvice,
  targetBand,
}: {
  result: TargetResult;
  error: number;
  inBand: boolean;
  steady: boolean;
  saturationRisk: string;
  tuneAdvice: string;
  targetBand: number;
}) {
  const resultTone =
    result === "On Target"
      ? "border-accent/60 bg-accent/12 text-accent"
      : result === "Critical"
        ? "border-warn/60 bg-warn/12 text-warn"
        : "border-danger/60 bg-danger/12 text-danger";
  return (
    <Card>
      <CardContent className="py-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className={`rounded border px-3 py-1 text-sm font-semibold ${resultTone}`}>{result}</div>
          <StatePill icon={Target} label="Error" value={`${error.toFixed(2)}°C`} tone={Math.abs(error) <= targetBand ? "ok" : "warn"} />
          <StatePill icon={Waves} label="Band" value={inBand ? "In Band" : "Out Band"} tone={inBand ? "ok" : "warn"} />
          <StatePill icon={CheckCircle2} label="Steady" value={steady ? "Stable" : "Unstable"} tone={steady ? "ok" : "warn"} />
          <StatePill icon={Gauge} label="Sat Risk" value={saturationRisk} tone={saturationRisk === "High" ? "danger" : saturationRisk === "Medium" ? "warn" : "ok"} />
          <StatePill icon={SlidersHorizontal} label="Advice" value={tuneAdvice} tone={tuneAdvice === "Keep" ? "ok" : "info"} />
        </div>
      </CardContent>
    </Card>
  );
}

function StatePill({
  icon: Icon,
  label,
  value,
  tone = "info",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone?: "ok" | "warn" | "danger" | "info";
}) {
  const cls = {
    ok: "border-accent/50 text-accent",
    warn: "border-warn/50 text-warn",
    danger: "border-danger/50 text-danger",
    info: "border-neon/50 text-neon",
  }[tone];
  return (
    <div className={`inline-flex items-center gap-2 rounded border bg-panel2 px-2.5 py-1 text-xs ${cls}`}>
      <Icon className="h-3.5 w-3.5" />
      <span className="text-mute">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function SignalBox({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded border border-line bg-panel2 px-2 py-1.5 text-xs">
      <div className="text-[10px] text-mute">{label}</div>
      <div className={tone}>{value}</div>
    </div>
  );
}

function ChartLegend({ label, sampleClass }: { label: string; sampleClass: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-2.5 w-5 rounded-sm ${sampleClass}`} />
      <span>{label}</span>
    </span>
  );
}

function SectionTitle({ title }: { title: string }) {
  return <div className="text-xs font-semibold uppercase tracking-wide text-mute">{title}</div>;
}

function MetricRow({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "target" }) {
  const isTarget = tone === "target";
  return (
    <div className={`flex items-center justify-between rounded px-2 py-1 ${isTarget ? "border border-accent/50 bg-accent/10" : "border border-line/70 bg-panel2"}`}>
      <span className={isTarget ? "text-accent" : "text-mute"}>{label}</span>
      <span className={isTarget ? "font-semibold text-accent" : "text-text"}>{value}</span>
    </div>
  );
}

function MetricCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded border border-line/70 bg-panel2 p-2 text-center">
      <div className="text-xs text-mute">{title}</div>
      <div className="text-base font-semibold text-neon">{value}</div>
    </div>
  );
}

function FeedbackRow({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "ok" | "warn" | "danger" }) {
  const cls = {
    default: "text-text border-line/70",
    ok: "text-accent border-accent/40",
    warn: "text-warn border-warn/40",
    danger: "text-danger border-danger/40",
  }[tone];
  return (
    <div className={`flex items-center justify-between rounded border bg-panel2 px-2 py-1 ${cls}`}>
      <span className="text-mute">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function feedbackTone(effect: EffectState): "default" | "ok" | "warn" | "danger" {
  if (effect === "Improved") return "ok";
  if (effect === "Worse") return "danger";
  if (effect === "Pending") return "warn";
  return "default";
}

function InlineRefTag({ label, weak = false }: { label: string; weak?: boolean }) {
  return (
    <span className={`rounded border px-2 py-0.5 ${weak ? "border-line/70 text-mute" : "border-neon/40 text-neon"}`}>
      {label}
    </span>
  );
}

function SmallNumberInput({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="space-y-1">
      <div className="text-[10px] text-mute">{label}</div>
      <Input
        className="h-8"
        type="number"
        step={step}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Number(e.target.value || 0))}
      />
    </label>
  );
}

function toDatetimeLocalValue(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${d}T${hh}:${mm}`;
}

function formatDuration(totalSec: number): string {
  if (!Number.isFinite(totalSec) || totalSec <= 0) return "0m";
  const sec = Math.max(0, Math.round(totalSec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${Math.max(1, m)}m`;
}

function TargetRuleCard({
  title,
  field,
  target,
  current,
  rule,
  why,
  status,
}: {
  title: string;
  field: string;
  target: string;
  current: string;
  rule: string;
  why: string;
  status: EvalStatus;
}) {
  const toneClass =
    status === "Pass"
      ? "border-accent/45 bg-accent/8 text-accent"
      : status === "Warn"
        ? "border-warn/45 bg-warn/8 text-warn"
        : "border-danger/45 bg-danger/8 text-danger";
  return (
    <div className={`rounded border p-2 text-xs ${toneClass}`}>
      <div className="mb-1 flex items-center justify-between">
        <div className="font-semibold">{title}</div>
        <span className="rounded border px-1.5 py-0.5 text-[10px]">{status}</span>
      </div>
      <div className="space-y-0.5 text-mute">
        <div>Field: {field}</div>
        <div>Target: {target}</div>
        <div>Current: {current}</div>
        <div>Rule: {rule}</div>
        <div>Why: {why}</div>
      </div>
    </div>
  );
}
