import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useDevices } from "@/routes/use-data";
import type { AIRuntimeConfig, AIRuntimeRecommendationDebug, AIRuntimeStatus } from "@/types";

const BOOLEAN_OPTIONS = [
  { label: "Enabled", value: "true" },
  { label: "Disabled", value: "false" },
];

export function AIRuntimePage() {
  const { devices } = useDevices();
  const [config, setConfig] = useState<AIRuntimeConfig | null>(null);
  const [status, setStatus] = useState<AIRuntimeStatus | null>(null);
  const [debugInfo, setDebugInfo] = useState<AIRuntimeRecommendationDebug | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);

  const rankedCandidates = useMemo(() => {
    const raw = debugInfo?.decision?.ranked_candidates;
    return Array.isArray(raw) ? raw : [];
  }, [debugInfo?.decision]);

  const topCandidate = useMemo(() => {
    const raw = debugInfo?.decision?.top_1_candidate;
    return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
  }, [debugInfo?.decision]);

  async function loadAll(deviceId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const [cfg, st] = await Promise.all([api.aiRuntimeConfig(), api.aiRuntimeStatus()]);
      setConfig(cfg);
      setStatus(st);
      if (typeof deviceId === "number") {
        try {
          const dbg = await api.aiRuntimeRecommendationDebug({ device_id: deviceId });
          setDebugInfo(dbg);
        } catch {
          setDebugInfo(null);
        }
      } else {
        setDebugInfo(null);
      }
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    if (selectedDeviceId == null) return;
    void loadAll(selectedDeviceId);
  }, [selectedDeviceId]);

  async function saveConfig() {
    if (!config) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await api.updateAiRuntimeConfig(config);
      setConfig(saved);
      const st = await api.aiRuntimeStatus();
      setStatus(st);
      setNotice("AI runtime config saved and model status refreshed.");
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading && !config) {
    return <div className="p-6 text-sm text-mute">Loading AI runtime...</div>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-neon/80">AI Runtime</div>
            <CardTitle className="text-2xl">Model Configuration and Decision Explainability</CardTitle>
          </div>
          <Button variant="ghost" onClick={() => void loadAll(selectedDeviceId)}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-2">
          {error && <div className="text-sm text-accent">{error}</div>}
          {notice && <div className="text-sm text-neon">{notice}</div>}
          <div className="text-xs text-mute">
            Configure runtime model switches, inspect model availability, and review candidate ranking explanation for the latest recommendation.
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model Overview</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2">
            <ModelStatusCard name="Problem Classifier" state={status?.problem_classifier} />
            <ModelStatusCard name="Success Predictor" state={status?.success_predictor} />
            <ModelStatusCard name="Preview Gap Predictor" state={status?.preview_gap_predictor} />
            <ModelStatusCard name="Candidate Ranker" state={status?.candidate_ranker} />
          </div>
        </CardContent>
      </Card>

      {config && (
        <Card>
          <CardHeader>
            <CardTitle>Decision Config</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <BoolField label="Problem Classifier" value={config.problem_classifier_enabled} onChange={(v) => setConfig({ ...config, problem_classifier_enabled: v })} />
              <BoolField label="Success Predictor" value={config.success_predictor_enabled} onChange={(v) => setConfig({ ...config, success_predictor_enabled: v })} />
              <BoolField
                label="Preview Gap Predictor"
                value={config.preview_gap_predictor_enabled}
                onChange={(v) => setConfig({ ...config, preview_gap_predictor_enabled: v })}
              />
              <BoolField label="Candidate Ranker" value={config.candidate_ranker_enabled} onChange={(v) => setConfig({ ...config, candidate_ranker_enabled: v })} />
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <VariantField
                label="Success Variant"
                value={config.success_model_variant}
                onChange={(v) => setConfig({ ...config, success_model_variant: v })}
              />
              <VariantField
                label="Preview Gap Variant"
                value={config.preview_gap_model_variant}
                onChange={(v) => setConfig({ ...config, preview_gap_model_variant: v })}
              />
              <NumberField label="Ranker Alpha" value={config.ranker_alpha} onChange={(v) => setConfig({ ...config, ranker_alpha: v })} />
              <NumberField label="Ranker Beta" value={config.ranker_beta} onChange={(v) => setConfig({ ...config, ranker_beta: v })} />
              <NumberField
                label="High Gap Threshold"
                value={config.high_gap_penalty_threshold}
                onChange={(v) => setConfig({ ...config, high_gap_penalty_threshold: v })}
              />
              <NumberField
                label="Candidate Count"
                value={config.ranker_candidate_count}
                onChange={(v) => setConfig({ ...config, ranker_candidate_count: Math.max(3, Math.round(v)) })}
              />
              <BoolField
                label="Use Classifier Bias"
                value={config.use_problem_classifier_for_candidate_bias}
                onChange={(v) => setConfig({ ...config, use_problem_classifier_for_candidate_bias: v })}
              />
            </div>
            <div>
              <Button onClick={saveConfig} disabled={saving}>
                {saving ? "Saving..." : "Save Runtime Config"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Current Decision Explanation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <div className="mb-1 text-xs text-mute">Device</div>
              <Select
                value={selectedDeviceId != null ? String(selectedDeviceId) : undefined}
                onValueChange={(value) => setSelectedDeviceId(value ? Number(value) : null)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select device" />
                </SelectTrigger>
                <SelectContent>
                  {devices.map((d) => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      {d.name} ({d.code})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {!debugInfo && <div className="text-sm text-mute">No runtime decision found yet for selected device.</div>}
          {debugInfo && (
            <div className="space-y-2 rounded-md border border-line/70 bg-panel2/50 p-3 text-sm">
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                <Info label="Source" value={debugInfo.source} />
                <Info label="Recommendation ID" value={String(debugInfo.recommendation_id ?? "-")} />
                <Info label="Predicted Problem" value={String(debugInfo.decision?.predicted_problem_type ?? "-")} />
                <Info label="Top-1 Candidate" value={String(debugInfo.decision?.top_1_candidate_id ?? "-")} />
                <Info label="Fallback Used" value={String(debugInfo.decision?.fallback_used ?? false)} />
                <Info label="Fallback Reason" value={String(debugInfo.decision?.fallback_reason ?? "-")} />
              </div>
              <div className="text-xs text-mute">
                Scoring: {String((debugInfo.decision?.scoring_formula as Record<string, unknown> | undefined)?.total_score ?? "-")}
              </div>
              {topCandidate && (
                <div className="text-xs text-mute">
                  success: {JSON.stringify((topCandidate.success_model ?? {}) as Record<string, unknown>)} | gap:{" "}
                  {JSON.stringify((topCandidate.preview_gap_model ?? {}) as Record<string, unknown>)}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Candidate Ranking Table</CardTitle>
        </CardHeader>
        <CardContent>
          {rankedCandidates.length === 0 && <div className="text-sm text-mute">No ranked candidates available.</div>}
          {rankedCandidates.length > 0 && (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="text-mute">
                  <tr className="border-b border-line/70">
                    <th className="px-2 py-2">Rank</th>
                    <th className="px-2 py-2">Candidate</th>
                    <th className="px-2 py-2">Params</th>
                    <th className="px-2 py-2">Delta</th>
                    <th className="px-2 py-2">Success</th>
                    <th className="px-2 py-2">Gap</th>
                    <th className="px-2 py-2">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {rankedCandidates.map((item, idx) => {
                    const row = item as Record<string, unknown>;
                    return (
                      <tr key={`${row.candidate_id ?? idx}`} className="border-b border-line/40">
                        <td className="px-2 py-2">{String(row.rank ?? idx + 1)}</td>
                        <td className="px-2 py-2">{String(row.candidate_id ?? "-")}</td>
                        <td className="px-2 py-2">{formatParams(row.recommended_params)}</td>
                        <td className="px-2 py-2">{formatParams(row.delta)}</td>
                        <td className="px-2 py-2">{formatProb(row.success_model)}</td>
                        <td className="px-2 py-2">{formatProb(row.preview_gap_model)}</td>
                        <td className="px-2 py-2">{formatScore(row.total_score)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ModelStatusCard({ name, state }: { name: string; state?: { enabled: boolean; loaded: boolean; error?: string | null } }) {
  return (
    <div className="rounded-md border border-line/70 bg-panel2/60 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-semibold">{name}</div>
        <Badge className={state?.enabled ? "border-neon/60 text-neon" : "border-line text-mute"}>{state?.enabled ? "enabled" : "disabled"}</Badge>
      </div>
      <div className="text-xs text-mute">status: {state?.loaded ? "loaded" : "unavailable"}</div>
      {state?.error && <div className="mt-1 text-xs text-accent">{state.error}</div>}
    </div>
  );
}

function BoolField({ label, value, onChange }: { label: string; value: boolean; onChange: (next: boolean) => void }) {
  return (
    <div>
      <div className="mb-1 text-xs text-mute">{label}</div>
      <Select value={value ? "true" : "false"} onValueChange={(v) => onChange(v === "true")}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {BOOLEAN_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function VariantField({ label, value, onChange }: { label: string; value: string; onChange: (next: string) => void }) {
  return (
    <div>
      <div className="mb-1 text-xs text-mute">{label}</div>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="baseline">baseline</SelectItem>
          <SelectItem value="tree">tree</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (next: number) => void }) {
  return (
    <div>
      <div className="mb-1 text-xs text-mute">{label}</div>
      <Input type="number" value={String(value)} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-mute">{label}</div>
      <div className="text-sm">{value}</div>
    </div>
  );
}

function normalizeError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err ?? "Unknown error");
}

function formatParams(value: unknown): string {
  if (!value || typeof value !== "object") return "-";
  const obj = value as Record<string, unknown>;
  return `kp=${formatScore(obj.kp)} ki=${formatScore(obj.ki)} kd=${formatScore(obj.kd)}`;
}

function formatProb(value: unknown): string {
  if (!value || typeof value !== "object") return "-";
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).filter((k) => k.startsWith("p_"));
  if (!keys.length) return "-";
  return keys.map((k) => `${k}=${formatScore(obj[k])}`).join(" ");
}

function formatScore(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(3);
}
