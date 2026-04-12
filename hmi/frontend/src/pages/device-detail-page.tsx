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
import type {
  AIRecommendation,
  AIGeneratedRecommendation,
  AIPreviewSimulation,
  ControlEvaluation,
  Device,
  MetricWindowStats,
} from "@/types";

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
const CHART_RENDER_MAX_POINTS = 300;
const PREVIEW_CHART_MAX_POINTS = 240;
const GENERATE_CLICK_DEBOUNCE_MS = 1200;

const EMPTY_CONTROL_EVAL: ControlEvaluation = {
  current_temp: 0,
  target_temp: 0,
  pwm_output: 0,
  error: 0,
  in_band: false,
  steady: false,
  steady_window_samples: 0,
  steady_in_band_samples: 0,
  observed_settling_sec: null,
  overshoot_pct: 0,
  saturation_ratio: 0,
  saturation_risk: "Low",
  tune_advice: "Tune",
  result: "Critical",
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

  const { device, metrics, parameters, alarms, recommendation, loading, reload, updateParameters, applyAiRecommendation } =
    useDeviceDetail(deviceId);

  const [editing, setEditing] = useState({ kp: "", ki: "", kd: "", target_temp: "", control_mode: "" });
  const [feedback, setFeedback] = useState({
    lastUpdate: "-",
    ackStatus: "Acked",
    appliedStatus: "Applied",
    effect: "No Change" as EffectState,
    reason: "-" as string,
  });

  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerItems, setPickerItems] = useState<Device[]>([]);
  const [targetConfig, setTargetConfig] = useState<TargetConfig>(DEFAULT_TARGET_CONFIG);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmIntent, setConfirmIntent] = useState<"full" | "targets">("full");
  const [aiConfirmOpen, setAiConfirmOpen] = useState(false);
  const [aiGenerateBusy, setAiGenerateBusy] = useState(false);
  const [aiApplyBusy, setAiApplyBusy] = useState(false);
  const [aiPreviewBusy, setAiPreviewBusy] = useState(false);
  const [aiGenerated, setAiGenerated] = useState<AIGeneratedRecommendation | null>(null);
  const [aiRecoveredFromStorage, setAiRecoveredFromStorage] = useState(false);
  const [aiApplyResult, setAiApplyResult] = useState({ ackStatus: "Idle", applyStatus: "Idle", detail: "-" });
  const [aiPreviewResult, setAiPreviewResult] = useState<AIPreviewSimulation | null>(null);
  const [aiPreviewError, setAiPreviewError] = useState<string | null>(null);
  const [targetEvalOpen, setTargetEvalOpen] = useState(false);
  const [historyRangePreset, setHistoryRangePreset] = useState<HistoryRangePreset>("6h");
  const [historyCustomStart, setHistoryCustomStart] = useState(() =>
    toDatetimeLocalValue(new Date(Date.now() - 6 * 60 * 60 * 1000))
  );
  const [historyCustomEnd, setHistoryCustomEnd] = useState(() => toDatetimeLocalValue(new Date()));
  const [historyRangeStats, setHistoryRangeStats] = useState<MetricWindowStats>({
    samples: 0,
    in_band_ratio: 0,
    total_stable_sec: 0,
    longest_stable_sec: 0,
    since_last_stable_sec: null,
    has_stable_window: false,
  });
  const [historyStatsLoading, setHistoryStatsLoading] = useState(true);
  const [controlEval, setControlEval] = useState<ControlEvaluation>(EMPTY_CONTROL_EVAL);
  const [controlEvalLoading, setControlEvalLoading] = useState(true);
  const aiGenerateClickRef = useRef(0);
  const chartTimeFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }),
    []
  );

  useEffect(() => {
    setAiGenerated(null);
    setAiRecoveredFromStorage(false);
    setAiApplyResult({ ackStatus: "Idle", applyStatus: "Idle", detail: "-" });
    setAiPreviewResult(null);
    setAiPreviewError(null);
  }, [deviceId]);

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
  }, [pickerOpen, pickerQuery, device?.id]);

  useEffect(() => {
    if (!deviceId) return;
    let cancelled = false;

    const loadControlEval = () => {
      const now = Date.now();
      return api
        .controlEval(deviceId, {
          start_ms: now - 6 * 60 * 60 * 1000,
          end_ms: now,
          band: targetConfig.band,
          steady_window: targetConfig.steadyWindow,
          pwm_threshold: targetConfig.pwmThreshold,
          saturation_warn: targetConfig.saturationWarn,
          saturation_high: targetConfig.saturationHigh,
          overshoot_limit: targetConfig.overshootLimit,
          limit: 20000,
        })
        .then((res) => {
          if (cancelled) return;
          setControlEval(res);
        })
        .catch(() => {
          if (cancelled) return;
          setControlEval(EMPTY_CONTROL_EVAL);
        })
        .finally(() => {
          if (cancelled) return;
          setControlEvalLoading(false);
        });
    };

    setControlEvalLoading(true);
    void loadControlEval();
    const timer = window.setInterval(() => {
      void loadControlEval();
    }, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    deviceId,
    targetConfig.band,
    targetConfig.steadyWindow,
    targetConfig.pwmThreshold,
    targetConfig.saturationWarn,
    targetConfig.saturationHigh,
    targetConfig.overshootLimit,
  ]);

  const evalSnapshot = useMemo(
    () => ({
      currentTemp: controlEval.current_temp || metrics[metrics.length - 1]?.current_temp || device?.current_temp || 0,
      targetTemp: controlEval.target_temp || metrics[metrics.length - 1]?.target_temp || device?.target_temp || 0,
    }),
    [controlEval.current_temp, controlEval.target_temp, metrics, device]
  );

  const derived = useMemo(
    () => ({
      error: controlEval.error,
      inBand: controlEval.in_band,
      steady: controlEval.steady,
      steadyWindowSamples: controlEval.steady_window_samples,
      steadyInBandSamples: controlEval.steady_in_band_samples,
      observedSettlingSec: controlEval.observed_settling_sec ?? null,
      overshootPct: controlEval.overshoot_pct,
      saturationRatio: controlEval.saturation_ratio,
      saturationRisk: controlEval.saturation_risk,
      tuneAdvice: controlEval.tune_advice,
      result: controlEval.result as TargetResult,
    }),
    [controlEval]
  );

  const metricsForChart = useMemo(() => {
    if (metrics.length <= CHART_RENDER_MAX_POINTS) return metrics;
    const step = Math.ceil(metrics.length / CHART_RENDER_MAX_POINTS);
    const sampled: typeof metrics = [];
    for (let i = 0; i < metrics.length; i += step) {
      sampled.push(metrics[i]);
    }
    const last = metrics[metrics.length - 1];
    if (sampled[sampled.length - 1] !== last) sampled.push(last);
    return sampled;
  }, [metrics]);

  const chartData = useMemo(
    () =>
      metricsForChart.map((m, idx) => ({
        idx,
        t: chartTimeFormatter.format(new Date(m.timestamp)),
        temp: m.current_temp,
        target: m.target_temp,
      })),
    [metricsForChart, chartTimeFormatter]
  );

  const targetTemp = evalSnapshot.targetTemp;
  const latestPwm = controlEval.pwm_output || metrics[metrics.length - 1]?.pwm_output || device?.pwm_output || 0;
  useEffect(() => {
    if (!deviceId) return;
    setHistoryStatsLoading(true);
    const now = Date.now();
    let startMs = 0;
    let endMs = now;
    if (historyRangePreset === "2h") startMs = now - 2 * 60 * 60 * 1000;
    if (historyRangePreset === "6h") startMs = now - 6 * 60 * 60 * 1000;
    if (historyRangePreset === "24h") startMs = now - 24 * 60 * 60 * 1000;
    if (historyRangePreset === "custom") {
      const parsedStart = new Date(historyCustomStart).getTime();
      const parsedEnd = new Date(historyCustomEnd).getTime();
      if (!Number.isFinite(parsedStart) || !Number.isFinite(parsedEnd) || parsedStart >= parsedEnd) {
        setHistoryRangeStats({
          samples: 0,
          in_band_ratio: 0,
          total_stable_sec: 0,
          longest_stable_sec: 0,
          since_last_stable_sec: null,
          has_stable_window: false,
        });
        setHistoryStatsLoading(false);
        return;
      }
      startMs = parsedStart;
      endMs = parsedEnd;
    }

    api
      .metricsStats(deviceId, {
        start_ms: Math.floor(startMs),
        end_ms: Math.floor(endMs),
        band: targetConfig.band,
        steady_window: targetConfig.steadyWindow,
        limit: 20000,
      })
      .then((stats) => setHistoryRangeStats(stats))
      .catch(() =>
        setHistoryRangeStats({
          samples: 0,
          in_band_ratio: 0,
          total_stable_sec: 0,
          longest_stable_sec: 0,
          since_last_stable_sec: null,
          has_stable_window: false,
        })
      )
      .finally(() => setHistoryStatsLoading(false));
  }, [deviceId, historyRangePreset, historyCustomStart, historyCustomEnd, targetConfig.band, targetConfig.steadyWindow]);
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
        current: `${derived.steadyInBandSamples}/${targetConfig.steadyWindow} samples in band`,
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

    const values = chartData.flatMap((d) => [d.temp, d.target, d.target - targetConfig.band, d.target + targetConfig.band]);
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

  const targetBandAreas = useMemo(() => {
    if (!chartData.length) return [] as Array<{ key: string; x1: number; x2: number; y1: number; y2: number }>;
    // Avoid generating too many tiny areas caused by float jitter.
    const epsilon = 1e-3;
    const areas: Array<{ key: string; x1: number; x2: number; y1: number; y2: number }> = [];
    let start = 0;
    let activeTarget = chartData[0].target;

    for (let i = 1; i < chartData.length; i += 1) {
      if (Math.abs(chartData[i].target - activeTarget) <= epsilon) continue;
      areas.push({
        key: `${start}-${i - 1}-${activeTarget}`,
        x1: start,
        x2: i - 1,
        y1: activeTarget - targetConfig.band,
        y2: activeTarget + targetConfig.band,
      });
      start = i;
      activeTarget = chartData[i].target;
    }

    areas.push({
      key: `${start}-${chartData.length - 1}-${activeTarget}`,
      x1: start,
      x2: chartData.length - 1,
      y1: activeTarget - targetConfig.band,
      y2: activeTarget + targetConfig.band,
    });
    return areas;
  }, [chartData, targetConfig.band]);

  const aiCurrentParams = aiGenerated?.current_params ?? {
    kp: parameters?.kp ?? 0,
    ki: parameters?.ki ?? 0,
    kd: parameters?.kd ?? 0,
  };
  const aiRecommendedParams = aiGenerated?.recommended_params ?? null;
  const aiDelta = aiGenerated?.delta ?? null;
  const aiNoChangeNeeded = Boolean(
    aiGenerated &&
      (aiGenerated.problem_type === "normal" ||
        (aiDelta && isZeroDelta(aiDelta.kp) && isZeroDelta(aiDelta.ki) && isZeroDelta(aiDelta.kd)))
  );
  const aiEvidenceRows = aiGenerated ? buildEvidenceRows(aiGenerated.evidence) : [];
  const showStoredEvidenceHint = Boolean(aiGenerated && aiRecoveredFromStorage && aiEvidenceRows.length === 0);
  const aiPreviewTrust = useMemo(() => {
    if (!aiGenerated || aiNoChangeNeeded) return null;
    return derivePreviewTrust(aiGenerated.ai_decision);
  }, [aiGenerated, aiNoChangeNeeded]);
  const previewCurveData = useMemo(() => {
    if (!aiPreviewResult) return [] as Array<{ idx: number; t: string; baseline: number; recommended: number; target: number }>;
    const base = aiPreviewResult.baseline_curve;
    const rec = aiPreviewResult.recommended_curve;
    const len = Math.min(base.length, rec.length);
    if (len === 0) return [];
    const step = Math.max(1, Math.ceil(len / PREVIEW_CHART_MAX_POINTS));
    const rows: Array<{ idx: number; t: string; baseline: number; recommended: number; target: number }> = [];
    for (let i = 0; i < len; i += step) {
      rows.push({
        idx: rows.length,
        t: formatPreviewSeconds(base[i].time_s),
        baseline: base[i].temp,
        recommended: rec[i].temp,
        target: base[i].target_temp,
      });
    }
    const lastIdx = len - 1;
    const maybeLast = rows[rows.length - 1];
    if (!maybeLast || maybeLast.baseline !== base[lastIdx].temp || maybeLast.recommended !== rec[lastIdx].temp) {
      rows.push({
        idx: rows.length,
        t: formatPreviewSeconds(base[lastIdx].time_s),
        baseline: base[lastIdx].temp,
        recommended: rec[lastIdx].temp,
        target: base[lastIdx].target_temp,
      });
    }
    return rows;
  }, [aiPreviewResult]);

  const previewYDomain = useMemo<[number, number]>(() => {
    if (previewCurveData.length === 0) return [35, 39];
    const values = previewCurveData.flatMap((row) => [row.baseline, row.recommended, row.target]);
    const target = previewCurveData[0]?.target;
    if (typeof target === "number") {
      values.push(target - targetConfig.band, target + targetConfig.band);
    }
    let min = Math.min(...values);
    let max = Math.max(...values);
    const span = max - min;
    const minSpan = 1.2;
    if (span < minSpan) {
      const pad = (minSpan - span) / 2;
      min -= pad;
      max += pad;
    }
    const margin = Math.max(0.08, (max - min) * 0.12);
    return [Number((min - margin).toFixed(2)), Number((max + margin).toFixed(2))];
  }, [previewCurveData, targetConfig.band]);
  const previewBand = useMemo(() => {
    const target = previewCurveData[0]?.target;
    if (typeof target !== "number") return null;
    return {
      y1: target - targetConfig.band,
      y2: target + targetConfig.band,
    };
  }, [previewCurveData, targetConfig.band]);
  const alarmSummary = useMemo(() => {
    const active = alarms.filter((a) => a.is_active);
    const critical = active.filter((a) => a.level.toLowerCase() === "critical").length;
    const warning = active.filter((a) => a.level.toLowerCase() === "warning").length;
    return {
      activeTotal: active.length,
      critical,
      warning,
      hasAlarm: active.length > 0,
    };
  }, [alarms]);

  // Intentionally do not auto-recover stored recommendation into the main panel.
  // Main AI recommendation details should appear only after explicit Generate action.

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
      reason: "-",
    });

    try {
      await updateParameters({
        target_temp: editing.target_temp ? Number(editing.target_temp) : undefined,
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
        reason: "-",
      });
    } catch (error) {
      const message = normalizeApiError(error);
      const lower = message.toLowerCase();
      const applyStatus = lower.includes("ack timeout")
        ? "Ack Timeout"
        : lower.includes("ack failed")
          ? "Ack Failed"
          : lower.includes("mqtt publish")
            ? "Publish Failed"
            : "Apply Failed";
      setFeedback({
        lastUpdate: new Date().toLocaleTimeString(),
        ackStatus: "Failed",
        appliedStatus: applyStatus,
        effect: "No Change",
        reason: message,
      });
    }
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
      reason: "-",
    }));
  }

  async function handleGenerateAiRecommendation() {
    if (aiGenerateBusy) return;
    const nowMs = Date.now();
    if (nowMs - aiGenerateClickRef.current < GENERATE_CLICK_DEBOUNCE_MS) return;
    aiGenerateClickRef.current = nowMs;

    setAiGenerateBusy(true);
    try {
      const generated = await api.generateAiRecommendation(deviceId, { window_minutes: 60 });
      const generatedNoChange =
        generated.problem_type === "normal" ||
        Boolean(
          generated.delta &&
            isZeroDelta(generated.delta.kp) &&
            isZeroDelta(generated.delta.ki) &&
            isZeroDelta(generated.delta.kd)
        );
      const existingActionable =
        aiGenerated &&
        aiGenerated.problem_type !== "normal" &&
        Boolean(
          aiGenerated.delta &&
            (!isZeroDelta(aiGenerated.delta.kp) ||
              !isZeroDelta(aiGenerated.delta.ki) ||
              !isZeroDelta(aiGenerated.delta.kd))
        );

      // Guard demo/operator flow:
      // if Generate returns a "no-change" refresh, keep existing actionable recommendation
      // so Apply stays available instead of being overwritten by a transient normal result.
      if (generatedNoChange && existingActionable) {
        setAiApplyResult({
          ackStatus: "Unchanged",
          applyStatus: "Ready",
          detail: "Latest generate result is no-change; kept current actionable recommendation.",
        });
        return;
      }

      setAiGenerated(generated);
      setAiRecoveredFromStorage(false);
      if (generated.reused_existing) {
        setAiApplyResult({
          ackStatus: "Reused",
          applyStatus: "Ready",
          detail: "Recommendation unchanged, latest result reused.",
        });
      } else {
        setAiApplyResult({ ackStatus: "Generated", applyStatus: "Pending", detail: "Recommendation generated. Awaiting confirmation." });
      }
    } catch (error) {
      const message = normalizeApiError(error);
      setAiApplyResult({ ackStatus: "Generate Failed", applyStatus: "Generate Failed", detail: message });
    } finally {
      setAiGenerateBusy(false);
    }
  }

  function openApplyAiConfirm() {
    if (!aiGenerated || !canWrite || aiApplyBusy || aiNoChangeNeeded) return;
    setAiConfirmOpen(true);
  }

  async function executeApplyAiRecommendation() {
    if (!canWrite || !aiGenerated) return;
    setAiApplyBusy(true);
    setAiApplyResult({ ackStatus: "Pending", applyStatus: "Applying", detail: "Dispatching AI recommendation to device..." });
    try {
      const appliedParams = await applyAiRecommendation();
      await reload({ silent: true });
      setEditing((prev) => ({
        ...prev,
        kp: String(appliedParams.kp),
        ki: String(appliedParams.ki),
        kd: String(appliedParams.kd),
        control_mode: appliedParams.control_mode ?? prev.control_mode,
      }));
      setAiGenerated((prev) => (prev ? { ...prev, history_state: "applied" } : prev));
      setAiApplyResult({ ackStatus: "Acked", applyStatus: "Applied", detail: "AI recommendation acknowledged by device." });
      setFeedback((prev) => ({
        ...prev,
        lastUpdate: new Date().toLocaleTimeString(),
        ackStatus: "Acked",
        appliedStatus: "Applied",
        reason: "-",
      }));
    } catch (error) {
      const message = normalizeApiError(error);
      const lower = message.toLowerCase();
      const applyStatus = lower.includes("ack timeout")
        ? "Ack Timeout"
        : lower.includes("ack failed")
          ? "Ack Failed"
          : lower.includes("mqtt publish")
            ? "Publish Failed"
            : "Apply Failed";
      setAiApplyResult({ ackStatus: "Failed", applyStatus, detail: message });
      setFeedback((prev) => ({
        ...prev,
        lastUpdate: new Date().toLocaleTimeString(),
        ackStatus: "Failed",
        appliedStatus: applyStatus,
        reason: message,
      }));
    } finally {
      setAiApplyBusy(false);
    }
  }

  async function handlePreviewImpact() {
    if (!aiGenerated || aiNoChangeNeeded) {
      setAiPreviewError(aiNoChangeNeeded ? "No change needed; preview is skipped." : "Generate recommendation first.");
      setAiPreviewResult(null);
      return;
    }
    setAiPreviewBusy(true);
    setAiPreviewError(null);
    try {
      const preview = await api.aiRecommendationPreview(deviceId, { horizon_sec: 1800, step_sec: 1 });
      setAiPreviewResult(preview);
    } catch (error) {
      const message = normalizeApiError(error);
      setAiPreviewError(message);
      setAiPreviewResult(null);
    } finally {
      setAiPreviewBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="py-2">
          <div className="grid gap-2 lg:grid-cols-[1.2fr_1fr_auto_auto_auto_auto] lg:items-center">
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

            <SignalBox label="Control" value={formatControlMode(parameters.control_mode)} tone="text-neon" />
            <SignalBox label="Comm" value={device.is_online ? "Online" : "Offline"} tone={device.is_online ? "text-accent" : "text-danger"} />
            <Button
              className={`h-9 px-3 text-xs ${alarmSummary.hasAlarm ? "border-danger/50 text-danger" : ""}`}
              variant="ghost"
              onClick={() => navigate(`/alarms?device=${encodeURIComponent(device.code)}`)}
            >
              Alarms {alarmSummary.activeTotal} · C{alarmSummary.critical} / W{alarmSummary.warning}
            </Button>
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
                <MetricCard title="Stable Time in Range" value={formatDuration(historyRangeStats.total_stable_sec)} loading={historyStatsLoading} />
                <MetricCard
                  title="Since Last Stable"
                  value={
                    historyRangeStats.since_last_stable_sec == null ? "N/A" : formatDuration(historyRangeStats.since_last_stable_sec)
                  }
                  loading={historyStatsLoading}
                />
                <MetricCard title="Longest Stable Run" value={formatDuration(historyRangeStats.longest_stable_sec)} loading={historyStatsLoading} />
                <MetricCard title="In-Band Ratio" value={`${(historyRangeStats.in_band_ratio * 100).toFixed(1)}%`} loading={historyStatsLoading} />
              </div>
              {controlEvalLoading && <div className="mt-2 text-xs text-mute">Updating real-time control evaluation...</div>}

              <div className="mt-2 text-xs text-mute">
                {historyStatsLoading ? (
                  <span className="inline-block h-4 w-[360px] animate-pulse rounded bg-panel2" />
                ) : (
                  <>
                    Samples: {historyRangeStats.samples} · Rule: stable requires at least {targetConfig.steadyWindow} consecutive samples within ±
                    {targetConfig.band.toFixed(2)}°C.
                  </>
                )}
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
                  {targetBandAreas.map((area) => (
                    <ReferenceArea
                      key={area.key}
                      x1={area.x1}
                      x2={area.x2}
                      y1={area.y1}
                      y2={area.y2}
                      fill="rgba(25,211,152,0.12)"
                      strokeOpacity={0}
                    />
                  ))}
                  <XAxis
                    dataKey="idx"
                    stroke="#7fa6b8"
                    tickFormatter={(v: number) => chartData[v]?.t ?? ""}
                    interval="preserveStartEnd"
                    minTickGap={44}
                    tickMargin={8}
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis stroke="#7fa6b8" width={56} domain={yDomain} allowDecimals tickCount={6} tick={{ fontSize: 12 }} />
                  <Tooltip
                    labelFormatter={(v) => `Time: ${chartData[Number(v)]?.t ?? ""}`}
                    contentStyle={{ background: "rgba(5, 24, 34, 0.95)", border: "1px solid rgba(41,240,255,0.35)", borderRadius: 8 }}
                    itemStyle={{ color: "#c7e4f1", fontSize: 12 }}
                    labelStyle={{ color: "#95c0d3", fontSize: 12 }}
                    cursor={{ stroke: "rgba(41,240,255,0.3)", strokeDasharray: "3 3" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="temp"
                    stroke="#29f0ff"
                    strokeWidth={2.8}
                    dot={false}
                    isAnimationActive
                    animationDuration={850}
                    animationEasing="ease-out"
                  />
                  <Line
                    type="monotone"
                    dataKey="target"
                    stroke="#2ad4a0"
                    strokeWidth={1.9}
                    dot={false}
                    isAnimationActive
                    animationDuration={850}
                    animationEasing="ease-out"
                  />
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
                  <div className="text-xs text-mute">Generate, review, confirm, then apply with ACK feedback</div>
                </div>
                <span className="rounded border border-neon/40 bg-neon/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-neon">
                  AI Core Module
                </span>
              </div>

              <div className="mt-3 grid gap-2 lg:grid-cols-3">
                <div className="rounded border border-line/70 bg-panel px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wide text-mute">Diagnosis</div>
                  <div className="mt-1 text-xs text-mute">
                    Primary Issue: <span className="text-text">{aiGenerated ? formatLabel(derivePrimaryProblemType(aiGenerated)) : "Not generated"}</span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Secondary Issues:{" "}
                    <span className="text-text">
                      {aiGenerated ? formatProblemList(deriveSecondaryProblemTypes(aiGenerated)) : "N/A"}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Triggered Rules:{" "}
                    <span className="text-text">
                      {aiGenerated ? formatRuleList(deriveTriggeredRuleKeys(aiGenerated)) : "N/A"}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Risk Level: <span className="text-text">{aiGenerated?.risk_level ?? "N/A"}</span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Confidence:{" "}
                    <span className="text-accent">
                      {typeof aiGenerated?.confidence === "number" ? `${Math.round(aiGenerated.confidence * 100)}%` : "N/A"}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Confirmation:{" "}
                    <span className={aiGenerated?.requires_confirmation ? "text-warn" : "text-accent"}>
                      {aiGenerated ? formatConfirmationRequirement(aiGenerated.requires_confirmation) : "N/A"}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-mute">
                    Expected Effect: <span className="text-text">{aiGenerated ? formatExpectedEffect(aiGenerated.expected_effect) : "N/A"}</span>
                  </div>
                  {aiNoChangeNeeded && (
                    <div className="mt-2 rounded border border-accent/40 bg-accent/10 px-2 py-1 text-xs text-accent">
                      System currently stable, no parameter adjustment recommended.
                    </div>
                  )}
                </div>

                <div className="rounded border border-line/70 bg-panel px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wide text-mute">Parameter Comparison</div>
                  <div className="mt-1 overflow-hidden">
                    <div className="grid grid-cols-[44px_repeat(3,minmax(0,1fr))] gap-x-2 gap-y-1 text-[11px]">
                      <span className="text-mute">Param</span>
                      <span className="truncate text-right text-mute">Current</span>
                      <span className="truncate text-right text-mute">Rec</span>
                      <span className="truncate text-right text-mute">Δ</span>

                      <span className="text-text">Kp</span>
                      <span className="whitespace-nowrap text-right text-text">{formatPidValue(aiCurrentParams.kp)}</span>
                      <span className="whitespace-nowrap text-right text-accent">{aiRecommendedParams ? formatPidValue(aiRecommendedParams.kp) : "-"}</span>
                      <span className="whitespace-nowrap text-right text-neon">{aiDelta ? withSign(aiDelta.kp) : "-"}</span>

                      <span className="text-text">Ki</span>
                      <span className="whitespace-nowrap text-right text-text">{formatPidValue(aiCurrentParams.ki)}</span>
                      <span className="whitespace-nowrap text-right text-accent">{aiRecommendedParams ? formatPidValue(aiRecommendedParams.ki) : "-"}</span>
                      <span className="whitespace-nowrap text-right text-neon">{aiDelta ? withSign(aiDelta.ki) : "-"}</span>

                      <span className="text-text">Kd</span>
                      <span className="whitespace-nowrap text-right text-text">{formatPidValue(aiCurrentParams.kd)}</span>
                      <span className="whitespace-nowrap text-right text-accent">{aiRecommendedParams ? formatPidValue(aiRecommendedParams.kd) : "-"}</span>
                      <span className="whitespace-nowrap text-right text-neon">{aiDelta ? withSign(aiDelta.kd) : "-"}</span>
                    </div>
                  </div>
                </div>

                <div className="rounded border border-line/70 bg-panel px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wide text-mute">Apply Result</div>
                  <div className="mt-1 text-xs text-mute">ACK: <span className="text-text">{aiApplyResult.ackStatus}</span></div>
                  <div className="mt-1 text-xs text-mute">Apply: <span className="text-text">{aiApplyResult.applyStatus}</span></div>
                  <div className="mt-1 text-xs text-mute">
                    Detail: <span className="text-text">{aiApplyResult.detail}</span>
                  </div>
                  <div className="mt-1 text-xs text-mute">Last Stored Suggestion: <span className="text-text">{recommendation?.reason ?? "-"}</span></div>
                </div>
              </div>

            <div className="mt-2 rounded border border-line/70 bg-panel px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-mute">Evidence / Metrics</div>
              {!aiGenerated && <div className="mt-1 text-xs text-mute">Generate recommendation to view evidence.</div>}
              {showStoredEvidenceHint && (
                <div className="mt-1 text-xs text-mute">Stored recommendation loaded. Generate again to refresh evidence.</div>
              )}
              {aiGenerated && aiEvidenceRows.length === 0 && !showStoredEvidenceHint && <div className="mt-1 text-xs text-mute">No evidence metrics available.</div>}
              {aiEvidenceRows.length > 0 && (
                <div className="mt-1 grid gap-x-3 gap-y-1 text-xs sm:grid-cols-2 lg:grid-cols-3">
                  {aiEvidenceRows.map((row) => (
                    <div key={row.key} className="flex items-center justify-between rounded border border-line/60 bg-panel2 px-2 py-1">
                      <span className="text-mute">{row.label}</span>
                      <span className="font-semibold text-text">{row.value}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" onClick={handleGenerateAiRecommendation} disabled={aiGenerateBusy}>
                {aiGenerateBusy ? "Generating..." : "Generate Recommendation"}
              </Button>
              <Button size="sm" variant="ghost" onClick={handlePreviewImpact} disabled={aiPreviewBusy || !aiGenerated || aiNoChangeNeeded}>
                {aiPreviewBusy ? "Simulating..." : "Preview Impact"}
              </Button>
              <Button size="sm" variant="accent" onClick={openApplyAiConfirm} disabled={!canWrite || !aiGenerated || aiApplyBusy || aiNoChangeNeeded}>
                {aiApplyBusy ? "Applying..." : aiNoChangeNeeded ? "No Change Needed" : "Apply Recommendation"}
              </Button>
              </div>

              <div className="mt-3 rounded border border-line/70 bg-panel px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[11px] uppercase tracking-wide text-mute">Preview Simulation (What-if)</div>
                  {aiPreviewTrust && !aiNoChangeNeeded && (
                    <span
                      className={`rounded border px-2 py-1 text-[11px] ${
                        aiPreviewTrust.trustLevel === "high"
                          ? "border-accent/50 bg-accent/10 text-accent"
                          : aiPreviewTrust.trustLevel === "medium"
                            ? "border-warn/50 bg-warn/10 text-warn"
                            : "border-danger/50 bg-danger/10 text-danger"
                      }`}
                      title={`Preview gap model: P(low)=${(aiPreviewTrust.pLow * 100).toFixed(1)}%, P(medium)=${(
                        aiPreviewTrust.pMedium * 100
                      ).toFixed(1)}%, P(high)=${(aiPreviewTrust.pHigh * 100).toFixed(1)}%`}
                    >
                      Preview Trust: {aiPreviewTrust.trustLabel}
                    </span>
                  )}
                </div>
                {!aiPreviewResult && !aiPreviewBusy && !aiPreviewError && (
                  <div className="mt-1 text-xs text-mute">
                    {aiGenerated
                      ? aiNoChangeNeeded
                        ? "No change needed; preview impact is skipped."
                        : "Run preview to compare baseline vs recommended parameter impact."
                      : "Generate recommendation first, then run preview impact."}
                    {aiPreviewTrust && !aiNoChangeNeeded ? ` Gap-model confidence: ${aiPreviewTrust.trustLabel}.` : ""}
                  </div>
                )}
                {aiPreviewBusy && <div className="mt-1 text-xs text-mute">Running simulation...</div>}
                {aiPreviewError && <div className="mt-1 text-xs text-danger">{aiPreviewError}</div>}
                {aiPreviewResult && (
                  <div className="mt-2 space-y-2">
                    <div className="grid gap-2 md:grid-cols-2">
                      <PreviewMetricGroup title="Baseline" metrics={aiPreviewResult.baseline_metrics} />
                      <PreviewMetricGroup title="Recommended" metrics={aiPreviewResult.recommended_metrics} />
                    </div>
                    <div className="rounded border border-line/70 bg-panel2 p-2 text-xs">
                      <div className="mb-1 font-semibold text-text">Improvement Delta</div>
                      <div className="mb-1 text-[11px] text-mute">Legend: `↑` higher, `↓` lower, `→` unchanged.</div>
                      <div className="grid gap-x-3 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                        <DeltaBadge label="In-band Ratio" value={aiPreviewResult.improvement.in_band_ratio_delta} kind="ratio" />
                        <DeltaBadge label="Overshoot" value={aiPreviewResult.improvement.overshoot_c_delta} kind="temp" />
                        <DeltaBadge
                          label="Settling Time"
                          value={aiPreviewResult.improvement.settling_sec_delta}
                          kind="sec"
                          unavailable={
                            aiPreviewResult.baseline_metrics.settling_sec == null ||
                            aiPreviewResult.recommended_metrics.settling_sec == null
                          }
                          unavailableText="N/A"
                        />
                        <DeltaBadge label="Temp Swing" value={aiPreviewResult.improvement.temp_swing_delta} kind="temp" />
                        <DeltaBadge label="Mean Abs Error" value={aiPreviewResult.improvement.mean_abs_error_delta} kind="temp" />
                        <DeltaBadge label="Saturation Ratio" value={aiPreviewResult.improvement.saturation_ratio_delta} kind="ratio" />
                      </div>
                    </div>
                    {previewCurveData.length > 1 && (
                      <div className="h-[220px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={previewCurveData} margin={{ top: 8, right: 14, left: 2, bottom: 0 }}>
                            <CartesianGrid stroke="rgba(41,240,255,0.1)" />
                            {previewBand && (
                              <ReferenceArea
                                y1={previewBand.y1}
                                y2={previewBand.y2}
                                fill="rgba(25,211,152,0.12)"
                                strokeOpacity={0}
                              />
                            )}
                            <XAxis
                              dataKey="idx"
                              stroke="#7fa6b8"
                              tickFormatter={(v: number) => previewCurveData[v]?.t ?? ""}
                              minTickGap={34}
                              tickMargin={8}
                              tick={{ fontSize: 12 }}
                            />
                            <YAxis stroke="#7fa6b8" width={54} domain={previewYDomain} allowDecimals tickCount={6} tick={{ fontSize: 12 }} />
                            <Tooltip
                              labelFormatter={(v) => `t=${previewCurveData[Number(v)]?.t ?? ""}`}
                              contentStyle={{ background: "rgba(5, 24, 34, 0.95)", border: "1px solid rgba(41,240,255,0.35)", borderRadius: 8 }}
                            />
                            <Line type="monotone" dataKey="baseline" stroke="#7fa6b8" strokeWidth={1.8} dot={false} isAnimationActive />
                            <Line type="monotone" dataKey="recommended" stroke="#29f0ff" strokeWidth={2.2} dot={false} isAnimationActive />
                            <Line type="monotone" dataKey="target" stroke="#2ad4a0" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                    <div className="text-[11px] text-mute">Target Band: ±{targetConfig.band.toFixed(1)}°C</div>
                  </div>
                )}
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
            <MetricRow label="Mode" value={formatControlMode(parameters.control_mode)} />

            <SectionTitle title="Update & Feedback" />
            <form className="space-y-2" onSubmit={saveParameters}>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  disabled={!canWrite}
                  placeholder={`Kp ${formatPidValue(parameters.kp)}`}
                  value={editing.kp}
                  onChange={(e) => setEditing((s) => ({ ...s, kp: e.target.value }))}
                />
                <Input
                  disabled={!canWrite}
                  placeholder={`Ki ${formatPidValue(parameters.ki)}`}
                  value={editing.ki}
                  onChange={(e) => setEditing((s) => ({ ...s, ki: e.target.value }))}
                />
                <Input
                  disabled={!canWrite}
                  placeholder={`Kd ${formatPidValue(parameters.kd)}`}
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
                value={editing.control_mode || normalizeControlMode(parameters.control_mode)}
                onValueChange={(v) => setEditing((s) => ({ ...s, control_mode: v }))}
                disabled={!canWrite}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Control Mode" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="pid_control">PID Control</SelectItem>
                  <SelectItem value="pi_control">PI Control</SelectItem>
                  <SelectItem value="p_control">P Control</SelectItem>
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
              <FeedbackRow label="Reason" value={feedback.reason} />
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

      <ConfirmDialog
        open={aiConfirmOpen}
        title="Confirm AI Recommendation Apply"
        description={
          aiGenerated ? (
            <span>
              Apply recommendation now? problem_type=<b>{aiGenerated.problem_type}</b>, risk_level=<b>{aiGenerated.risk_level}</b>, confidence=
              <b>{Math.round(aiGenerated.confidence * 100)}%</b>.
            </span>
          ) : (
            "No recommendation generated."
          )
        }
        confirmLabel="Apply Recommendation"
        busy={aiApplyBusy}
        onCancel={() => !aiApplyBusy && setAiConfirmOpen(false)}
        onConfirm={async () => {
          try {
            await executeApplyAiRecommendation();
            setAiConfirmOpen(false);
          } finally {
            // noop
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
  }, [query, open]);

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
              placeholder="Search name/code/line/location..."
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
                <div className="truncate text-xs text-mute">{item.code} · {item.line} · {item.location}</div>
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

function MetricCard({ title, value, loading = false }: { title: string; value: string; loading?: boolean }) {
  return (
    <div className="rounded border border-line/70 bg-panel2 p-2 text-center">
      <div className="text-xs text-mute">{title}</div>
      {loading ? <div className="mx-auto mt-1 h-6 w-20 animate-pulse rounded bg-neon/15" /> : <div className="text-base font-semibold text-neon">{value}</div>}
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

function normalizeApiError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  try {
    const parsed = JSON.parse(raw) as { detail?: string };
    if (parsed && typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
  } catch {
    // keep raw message
  }
  return raw;
}

function withSign(value: number): string {
  const rounded = Number(value.toFixed(3));
  if (rounded === 0) return "0";
  const abs = Math.abs(rounded).toString();
  return rounded > 0 ? `+${abs}` : `-${abs}`;
}

function formatPidValue(value: number): string {
  return Number(value.toFixed(3)).toString();
}

function isZeroDelta(value: number): boolean {
  return Math.abs(value) < 1e-9;
}

function formatConfirmationRequirement(required: boolean): string {
  return required ? "Required" : "Not Required";
}

function formatExpectedEffect(value: string): string {
  const map: Record<string, string> = {
    keep_stable: "Keep Stable",
    speed_up_response: "Speed Up Response",
    reduce_steady_state_error: "Reduce Steady-state Error",
    reduce_overshoot: "Reduce Overshoot",
    reduce_oscillation: "Reduce Oscillation",
    limited_gain_expected: "Limited Gain Expected",
  };
  return map[value] ?? value;
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (ch: string) => ch.toUpperCase());
}

function derivePrimaryProblemType(data: AIGeneratedRecommendation): string {
  return (data.primary_problem_type || data.problem_type || "unknown").trim();
}

function deriveSecondaryProblemTypes(data: AIGeneratedRecommendation): string[] {
  const items = Array.isArray(data.secondary_problem_types) ? data.secondary_problem_types : [];
  return items.filter((item) => item && item !== derivePrimaryProblemType(data));
}

function deriveProblemFlags(data: AIGeneratedRecommendation): Record<string, boolean> {
  if (data.problem_flags && typeof data.problem_flags === "object") {
    return data.problem_flags;
  }
  const evidence = data.evidence ?? {};
  const mapping: Array<[string, string]> = [
    ["saturation_limited", "rule_saturation_limited"],
    ["severe_saturation", "rule_severe_saturation"],
    ["oscillation", "rule_oscillation"],
    ["overshoot_high", "rule_overshoot_high"],
    ["steady_state_error", "rule_steady_state_error"],
    ["slow_response", "rule_slow_response"],
  ];
  const out: Record<string, boolean> = {};
  for (const [key, evidenceKey] of mapping) {
    if (evidenceKey in evidence) out[key] = Boolean(evidence[evidenceKey]);
  }
  return out;
}

function deriveTriggeredRuleKeys(data: AIGeneratedRecommendation): string[] {
  return Object.entries(deriveProblemFlags(data))
    .filter(([, enabled]) => Boolean(enabled))
    .map(([rule]) => rule);
}

function formatProblemList(items: string[]): string {
  if (!items.length) return "None";
  return items.map((item) => formatLabel(item)).join(", ");
}

function formatRuleList(items: string[]): string {
  if (!items.length) return "None";
  return items.map((item) => formatLabel(item)).join(", ");
}

function formatMetricNumber(value: number): string {
  if (!Number.isFinite(value)) return "-";
  if (Number.isInteger(value)) return String(value);
  const fixed = value.toFixed(4);
  const [intPart, decPart = ""] = fixed.split(".");
  const trimmed = decPart.replace(/0+$/, "");
  if (!trimmed) return intPart;
  if (trimmed.length < 2) return `${intPart}.${decPart.slice(0, 2)}`;
  return `${intPart}.${trimmed}`;
}

function formatPercentValue(value: number): string {
  return `${formatMetricNumber(value)}%`;
}

function buildEvidenceRows(evidence: Record<string, string | number | boolean | null>): Array<{ key: string; label: string; value: string }> {
  const fields: Array<{ key: string; label: string; kind: "percent" | "ratio_percent" | "number" }> = [
    { key: "overshoot_pct", label: "Overshoot %", kind: "percent" },
    { key: "mean_abs_error", label: "Mean Abs Error", kind: "number" },
    { key: "error_std", label: "Error Std", kind: "number" },
    { key: "zero_crossings", label: "Zero Crossings", kind: "number" },
    { key: "in_band_ratio", label: "In-band Ratio", kind: "ratio_percent" },
    { key: "settling_sec", label: "Settling Time (s)", kind: "number" },
    { key: "saturation_ratio", label: "Saturation Ratio", kind: "ratio_percent" },
    { key: "pwm_mean", label: "PWM Mean", kind: "number" },
    { key: "pwm_max", label: "PWM Max", kind: "number" },
    { key: "temp_swing", label: "Temp Swing", kind: "number" },
  ];

  return fields.flatMap(({ key, label, kind }) => {
    const raw = evidence[key];
    if (raw === null || raw === undefined || typeof raw !== "number" || !Number.isFinite(raw)) return [];
    const value = kind === "percent" ? formatPercentValue(raw) : kind === "ratio_percent" ? formatPercentValue(raw * 100) : formatMetricNumber(raw);
    return [{ key, label, value }];
  });
}

function formatPreviewSeconds(value: number): string {
  const sec = Math.max(0, Math.round(value));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function PreviewMetricGroup({
  title,
  metrics,
}: {
  title: string;
  metrics: {
    in_band_ratio: number;
    overshoot_c: number;
    settling_sec?: number | null;
    temp_swing: number;
    mean_abs_error: number;
    saturation_ratio: number;
  };
}) {
  return (
    <div className="rounded border border-line/70 bg-panel2 p-2 text-xs">
      <div className="mb-1 font-semibold text-text">{title}</div>
      <div className="grid grid-cols-2 gap-1">
        <span className="text-mute">In-band</span>
        <span className="text-text">{(metrics.in_band_ratio * 100).toFixed(1)}%</span>
        <span className="text-mute">Overshoot</span>
        <span className="text-text">{metrics.overshoot_c.toFixed(3)}°C</span>
        <span className="text-mute">Settling</span>
        <span className="text-text">{metrics.settling_sec == null ? "N/A" : `${metrics.settling_sec.toFixed(0)}s`}</span>
        <span className="text-mute">Temp Swing</span>
        <span className="text-text">{metrics.temp_swing.toFixed(3)}°C</span>
        <span className="text-mute">Mean |Error|</span>
        <span className="text-text">{metrics.mean_abs_error.toFixed(3)}°C</span>
        <span className="text-mute">Saturation</span>
        <span className="text-text">{(metrics.saturation_ratio * 100).toFixed(1)}%</span>
      </div>
    </div>
  );
}

function DeltaBadge({
  label,
  value,
  kind,
  unavailable = false,
  unavailableText = "N/A",
}: {
  label: string;
  value: number;
  kind: "ratio" | "temp" | "sec";
  unavailable?: boolean;
  unavailableText?: string;
}) {
  if (unavailable) {
    return (
      <div className="flex items-center justify-between rounded border border-line/70 px-2 py-1 text-mute">
        <span className="text-mute">{label}</span>
        <span className="font-semibold">{unavailableText}</span>
      </div>
    );
  }

  const tone = value > 0 ? "text-accent border-accent/40" : value < 0 ? "text-danger border-danger/40" : "text-mute border-line/70";
  const abs = Math.abs(value);
  const rendered = (() => {
    if (kind === "ratio") {
      const arrow = value > 0 ? "↑" : value < 0 ? "↓" : "→";
      return `${arrow}${(abs * 100).toFixed(2)}%`;
    }
    if (kind === "temp") {
      const arrow = value > 0 ? "↑" : value < 0 ? "↓" : "→";
      return `${arrow}${abs.toFixed(3)}°C`;
    }
    const arrow = value > 0 ? "↑" : value < 0 ? "↓" : "→";
    return `${arrow}${abs.toFixed(1)}s`;
  })();
  return (
    <div className={`flex items-center justify-between rounded border px-2 py-1 ${tone}`}>
      <span className="text-mute">{label}</span>
      <span className="font-semibold">{rendered}</span>
    </div>
  );
}

function parseStoredRecommendationMeta(suggestion?: string | null): {
  history_state?: string;
  last_generate_reused?: boolean;
  reused_count?: number;
  last_accessed_at?: string;
  actual_effect_evaluated?: boolean;
  post_effect_summary?: {
    observed_window_start: string;
    observed_window_end: string;
    point_count: number;
    in_band_ratio_after: number;
    overshoot_c_after: number;
    settling_sec_after?: number | null;
    mean_abs_error_after: number;
    saturation_ratio_after: number;
    temp_swing_after: number;
  };
  post_effect_window_minutes?: number;
  post_effect_evaluated_at?: string;
  post_effect_comparison_before?: {
    in_band_ratio_delta?: number | null;
    overshoot_c_delta?: number | null;
    settling_sec_delta?: number | null;
    mean_abs_error_delta?: number | null;
    saturation_ratio_delta?: number | null;
    temp_swing_delta?: number | null;
  };
  post_effect_comparison_preview?: {
    in_band_ratio_delta?: number | null;
    overshoot_c_delta?: number | null;
    settling_sec_delta?: number | null;
    mean_abs_error_delta?: number | null;
    saturation_ratio_delta?: number | null;
    temp_swing_delta?: number | null;
  } | null;
  ai_decision?: Record<string, unknown> | null;
} {
  if (!suggestion || !suggestion.trim()) return {};
  try {
    const body = JSON.parse(suggestion) as unknown;
    if (!body || typeof body !== "object" || Array.isArray(body)) return {};
    const row = body as Record<string, unknown>;
    if (row.f !== "ai_rec" || !row.p || typeof row.p !== "object" || Array.isArray(row.p)) return {};
    const payload = row.p as Record<string, unknown>;
    const meta = payload.m;
    if (!meta || typeof meta !== "object" || Array.isArray(meta)) return {};
    const m = meta as Record<string, unknown>;

    const toNumber = (value: unknown): number | undefined => {
      const n = Number(value);
      return Number.isFinite(n) ? n : undefined;
    };

    const postSummaryRaw = m.pe;
    let postSummary:
      | {
          observed_window_start: string;
          observed_window_end: string;
          point_count: number;
          in_band_ratio_after: number;
          overshoot_c_after: number;
          settling_sec_after?: number | null;
          mean_abs_error_after: number;
          saturation_ratio_after: number;
          temp_swing_after: number;
        }
      | undefined;
    if (postSummaryRaw && typeof postSummaryRaw === "object" && !Array.isArray(postSummaryRaw)) {
      const pe = postSummaryRaw as Record<string, unknown>;
      if ("in_band_ratio_after" in pe || "point_count" in pe) {
        postSummary = pe as {
          observed_window_start: string;
          observed_window_end: string;
          point_count: number;
          in_band_ratio_after: number;
          overshoot_c_after: number;
          settling_sec_after?: number | null;
          mean_abs_error_after: number;
          saturation_ratio_after: number;
          temp_swing_after: number;
        };
      } else if ("ib" in pe) {
        postSummary = {
          observed_window_start: typeof m.pea === "string" ? m.pea : new Date().toISOString(),
          observed_window_end: typeof m.pea === "string" ? m.pea : new Date().toISOString(),
          point_count: toNumber(pe.pc) ?? 0,
          in_band_ratio_after: toNumber(pe.ib) ?? 0,
          overshoot_c_after: toNumber(pe.ov) ?? 0,
          settling_sec_after: toNumber(pe.st) ?? null,
          mean_abs_error_after: toNumber(pe.ma) ?? 0,
          saturation_ratio_after: toNumber(pe.sr) ?? 0,
          temp_swing_after: toNumber(pe.sw) ?? 0,
        };
      }
    }

    const cmpBeforeRaw = m.pecb;
    const cmpPreviewRaw = m.pecp;
    return {
      history_state: typeof m.hs === "string" ? m.hs : undefined,
      last_generate_reused: typeof m.lgr === "boolean" ? m.lgr : undefined,
      reused_count: toNumber(m.rc),
      last_accessed_at: typeof m.la === "string" ? m.la : undefined,
      actual_effect_evaluated: typeof m.aee === "boolean" ? m.aee : undefined,
      post_effect_summary: postSummary,
      post_effect_window_minutes: toNumber(m.pew),
      post_effect_evaluated_at: typeof m.pea === "string" ? m.pea : undefined,
      post_effect_comparison_before:
        cmpBeforeRaw && typeof cmpBeforeRaw === "object" && !Array.isArray(cmpBeforeRaw)
          ? (cmpBeforeRaw as {
              in_band_ratio_delta?: number | null;
              overshoot_c_delta?: number | null;
              settling_sec_delta?: number | null;
              mean_abs_error_delta?: number | null;
              saturation_ratio_delta?: number | null;
              temp_swing_delta?: number | null;
            })
          : undefined,
      post_effect_comparison_preview:
        cmpPreviewRaw && typeof cmpPreviewRaw === "object" && !Array.isArray(cmpPreviewRaw)
          ? (cmpPreviewRaw as {
              in_band_ratio_delta?: number | null;
              overshoot_c_delta?: number | null;
              settling_sec_delta?: number | null;
              mean_abs_error_delta?: number | null;
              saturation_ratio_delta?: number | null;
              temp_swing_delta?: number | null;
            })
          : null,
      ai_decision:
        m.ard && typeof m.ard === "object" && !Array.isArray(m.ard)
          ? (m.ard as Record<string, unknown>)
          : null,
    };
  } catch {
    return {};
  }
}

function parseReasonFields(reason: string): { problem_type?: string; expected_effect?: string } {
  if (!reason || !reason.trim()) return {};
  const text = reason.trim();
  const effectMatch = text.match(/effect=([a-z_]+)/i);
  const prefix = text.split(";")[0]?.trim() ?? "";
  const problem = prefix && !prefix.includes("=") ? prefix : undefined;
  return {
    problem_type: problem,
    expected_effect: effectMatch?.[1],
  };
}

function parseRiskFields(risk: string): { risk_level?: string; requires_confirmation?: boolean } {
  if (!risk || !risk.trim()) return {};
  const text = risk.trim();
  const levelMatch = text.match(/^(Low|Medium|High)\b/i);
  const confirmMatch = text.match(/requires_confirmation\s*=\s*(true|false)/i);
  return {
    risk_level: levelMatch ? normalizeRiskLevel(levelMatch[1]) : undefined,
    requires_confirmation: confirmMatch ? confirmMatch[1].toLowerCase() === "true" : undefined,
  };
}

function parseStoredAiRecommendation(
  recommendation: AIRecommendation,
  current_params: { kp: number; ki: number; kd: number }
): Partial<AIGeneratedRecommendation> & {
  primary_problem_type?: string;
  secondary_problem_types?: string[];
  problem_flags?: Record<string, boolean>;
  recommended_params?: { kp: number; ki: number; kd: number };
  delta?: { kp: number; ki: number; kd: number };
} {
  const reasonFields = parseReasonFields(recommendation.reason);
  const riskFields = parseRiskFields(recommendation.risk);
  const parsed: Partial<AIGeneratedRecommendation> & {
    primary_problem_type?: string;
    secondary_problem_types?: string[];
    problem_flags?: Record<string, boolean>;
    recommended_params?: { kp: number; ki: number; kd: number };
    delta?: { kp: number; ki: number; kd: number };
  } = {
    problem_type: reasonFields.problem_type,
    primary_problem_type: reasonFields.problem_type,
    expected_effect: reasonFields.expected_effect,
    risk_level: riskFields.risk_level,
    requires_confirmation: riskFields.requires_confirmation,
  };
  const meta = parseStoredRecommendationMeta(recommendation.suggestion);
  if (meta.history_state) parsed.history_state = meta.history_state;
  if (typeof meta.last_generate_reused === "boolean") parsed.last_generate_reused = meta.last_generate_reused;
  if (typeof meta.reused_count === "number") parsed.reused_count = meta.reused_count;
  if (meta.last_accessed_at) parsed.last_accessed_at = meta.last_accessed_at;
  if (meta.ai_decision && typeof meta.ai_decision === "object") parsed.ai_decision = meta.ai_decision;

  const suggestion = recommendation.suggestion?.trim() ?? "";
  if (!suggestion) return parsed;

  const extractFromObject = (obj: Record<string, unknown>) => {
    if (!parsed.problem_type && typeof obj.problem_type === "string") parsed.problem_type = obj.problem_type;
    if (!parsed.primary_problem_type && typeof obj.primary_problem_type === "string") parsed.primary_problem_type = obj.primary_problem_type;
    if (!parsed.secondary_problem_types && Array.isArray(obj.secondary_problem_types)) {
      parsed.secondary_problem_types = obj.secondary_problem_types.filter((item): item is string => typeof item === "string");
    }
    if (!parsed.problem_flags && obj.problem_flags && typeof obj.problem_flags === "object" && !Array.isArray(obj.problem_flags)) {
      parsed.problem_flags = Object.fromEntries(
        Object.entries(obj.problem_flags as Record<string, unknown>).map(([key, value]) => [key, Boolean(value)])
      );
    }
    if (!parsed.expected_effect && typeof obj.expected_effect === "string") parsed.expected_effect = obj.expected_effect;
    if (!parsed.risk_level && typeof obj.risk_level === "string") parsed.risk_level = normalizeRiskLevel(obj.risk_level);
    if (parsed.requires_confirmation === undefined && typeof obj.requires_confirmation === "boolean") {
      parsed.requires_confirmation = obj.requires_confirmation;
    }
    if (!parsed.evidence && obj.evidence && typeof obj.evidence === "object") {
      parsed.evidence = obj.evidence as Record<string, string | number | boolean | null>;
    }
    const recommended = pickPidTuple(obj.recommended_params);
    if (!parsed.recommended_params && recommended) parsed.recommended_params = recommended;
    const delta = pickPidTuple(obj.delta);
    if (!parsed.delta && delta) parsed.delta = delta;
  };

  try {
    const bodyUnknown = JSON.parse(suggestion) as unknown;
    if (bodyUnknown && typeof bodyUnknown === "object" && !Array.isArray(bodyUnknown)) {
      const body = bodyUnknown as Record<string, unknown>;

      // ai_rec v1 compact format.
      if (body.f === "ai_rec" && body.p && typeof body.p === "object" && !Array.isArray(body.p)) {
        const p = body.p as Record<string, unknown>;
        if (typeof p.t === "string") parsed.problem_type = p.t;
        if (typeof p.pt === "string") parsed.primary_problem_type = p.pt;
        if (Array.isArray(p.st)) {
          parsed.secondary_problem_types = p.st.filter((item): item is string => typeof item === "string");
        }
        if (p.pf && typeof p.pf === "object" && !Array.isArray(p.pf)) {
          parsed.problem_flags = Object.fromEntries(
            Object.entries(p.pf as Record<string, unknown>).map(([key, value]) => [key, Boolean(value)])
          );
        }
        if (typeof p.e === "string") parsed.expected_effect = p.e;
        if (typeof p.r === "string") parsed.risk_level = normalizeRiskLevel(p.r);
        if (typeof p.rc === "boolean") parsed.requires_confirmation = p.rc;
        if (!parsed.evidence && p.evidence && typeof p.evidence === "object") {
          parsed.evidence = p.evidence as Record<string, string | number | boolean | null>;
        }
        const recommended = pickPidTuple(p.rp);
        if (recommended) parsed.recommended_params = recommended;
        const delta = pickPidTuple(p.d);
        if (delta) parsed.delta = delta;
        return parsed;
      }

      // Older payload format.
      if (body.payload && typeof body.payload === "object" && !Array.isArray(body.payload)) {
        extractFromObject(body.payload as Record<string, unknown>);
        return parsed;
      }

      // Flat JSON fallback.
      extractFromObject(body);
      return parsed;
    }
  } catch {
    // Keep parsing as legacy text.
  }

  // Legacy text fallback, e.g. "Kp:+0.2 Ki:+0.05 Kd:0".
  const legacyDelta = parseLegacyPidDeltaText(suggestion);
  if (legacyDelta) {
    parsed.delta = legacyDelta;
    parsed.recommended_params = {
      kp: round4(current_params.kp + legacyDelta.kp),
      ki: round4(current_params.ki + legacyDelta.ki),
      kd: round4(current_params.kd + legacyDelta.kd),
    };
  }

  return parsed;
}

function buildRecoveredAiGenerated(
  recommendation: AIRecommendation,
  current_params: { kp: number; ki: number; kd: number }
): AIGeneratedRecommendation | null {
  const parsed = parseStoredAiRecommendation(recommendation, current_params);

  const recommended = parsed.recommended_params
    ? normalizePidTuple(parsed.recommended_params)
    : parsed.delta
      ? normalizePidTuple({
          kp: current_params.kp + parsed.delta.kp,
          ki: current_params.ki + parsed.delta.ki,
          kd: current_params.kd + parsed.delta.kd,
        })
      : null;
  if (!recommended) return null;

  const delta = parsed.delta
    ? normalizePidTuple(parsed.delta)
    : normalizePidTuple({
        kp: recommended.kp - current_params.kp,
        ki: recommended.ki - current_params.ki,
        kd: recommended.kd - current_params.kd,
      });

  const problem_type = parsed.problem_type || (isZeroDelta(delta.kp) && isZeroDelta(delta.ki) && isZeroDelta(delta.kd) ? "normal" : "unknown");
  const primary_problem_type = parsed.primary_problem_type || problem_type;
  const expected_effect = parsed.expected_effect || (problem_type === "normal" ? "keep_stable" : "limited_gain_expected");
  const requires_confirmation =
    typeof parsed.requires_confirmation === "boolean" ? parsed.requires_confirmation : problem_type !== "normal";

  return {
    problem_type: primary_problem_type,
    primary_problem_type,
    secondary_problem_types: parsed.secondary_problem_types ?? [],
    problem_flags: parsed.problem_flags ?? {},
    confidence: Number.isFinite(recommendation.confidence) ? recommendation.confidence : 0,
    risk_level: parsed.risk_level || "N/A",
    requires_confirmation,
    current_params: normalizePidTuple(current_params),
    recommended_params: recommended,
    delta,
    expected_effect,
    evidence: (parsed.evidence as Record<string, string | number | boolean | null> | undefined) ?? {},
    generated_at: recommendation.last_run_at,
    ai_decision: parsed.ai_decision ?? null,
  };
}

function derivePreviewTrust(
  aiDecision: Record<string, unknown> | null | undefined
): { trustLevel: "high" | "medium" | "low"; trustLabel: string; pLow: number; pMedium: number; pHigh: number } | null {
  if (!aiDecision || typeof aiDecision !== "object") return null;
  const top = aiDecision.top_1_candidate;
  if (!top || typeof top !== "object") return null;
  const gap = (top as Record<string, unknown>).preview_gap_model;
  if (!gap || typeof gap !== "object") return null;

  const pLow = Number((gap as Record<string, unknown>).p_low);
  const pMedium = Number((gap as Record<string, unknown>).p_medium);
  const pHigh = Number((gap as Record<string, unknown>).p_high);
  if (!Number.isFinite(pLow) || !Number.isFinite(pMedium) || !Number.isFinite(pHigh)) return null;

  const maxKey = [
    { k: "low", v: pLow },
    { k: "medium", v: pMedium },
    { k: "high", v: pHigh },
  ].sort((a, b) => b.v - a.v)[0]?.k;
  if (!maxKey) return null;

  if (maxKey === "low") {
    return { trustLevel: "high", trustLabel: "Can Trust (High)", pLow, pMedium, pHigh };
  }
  if (maxKey === "medium") {
    return { trustLevel: "medium", trustLabel: "Partially Trust (Medium)", pLow, pMedium, pHigh };
  }
  return { trustLevel: "low", trustLabel: "Use Caution (Low)", pLow, pMedium, pHigh };
}

function normalizeRiskLevel(value: unknown): string {
  const text = String(value ?? "").trim().toLowerCase();
  if (text === "low") return "Low";
  if (text === "medium") return "Medium";
  if (text === "high") return "High";
  return String(value ?? "");
}

function parseLegacyPidDeltaText(text: string): { kp: number; ki: number; kd: number } | null {
  const pattern = /(Kp|Ki|Kd)\s*:\s*([+-]?\d+(?:\.\d+)?)/g;
  const found: Partial<{ kp: number; ki: number; kd: number }> = {};
  for (const match of text.matchAll(pattern)) {
    const key = match[1].toLowerCase() as "kp" | "ki" | "kd";
    const value = Number(match[2]);
    if (Number.isFinite(value)) {
      found[key] = value;
    }
  }
  if (found.kp === undefined && found.ki === undefined && found.kd === undefined) return null;
  return {
    kp: round4(found.kp ?? 0),
    ki: round4(found.ki ?? 0),
    kd: round4(found.kd ?? 0),
  };
}

function pickPidTuple(input: unknown): { kp: number; ki: number; kd: number } | null {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  const row = input as Record<string, unknown>;
  const kp = Number(row.kp);
  const ki = Number(row.ki);
  const kd = Number(row.kd);
  if (!Number.isFinite(kp) || !Number.isFinite(ki) || !Number.isFinite(kd)) return null;
  return { kp: round4(kp), ki: round4(ki), kd: round4(kd) };
}

function normalizePidTuple(input: { kp: number; ki: number; kd: number }): { kp: number; ki: number; kd: number } {
  return {
    kp: round4(input.kp),
    ki: round4(input.ki),
    kd: round4(input.kd),
  };
}

function round4(value: number): number {
  return Number(value.toFixed(4));
}

function normalizeControlMode(mode: string): string {
  const next = mode.trim().toLowerCase();
  if (next === "pid" || next === "pid_control") return "pid_control";
  if (next === "pi" || next === "pi_control") return "pi_control";
  if (next === "p" || next === "p_control") return "p_control";
  return "pid_control";
}

function formatControlMode(mode: string): string {
  const normalized = normalizeControlMode(mode);
  if (normalized === "pid_control") return "PID";
  if (normalized === "pi_control") return "PI";
  if (normalized === "p_control") return "P";
  return mode;
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
