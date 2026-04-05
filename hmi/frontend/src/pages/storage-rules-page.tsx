import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { ChevronDown, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useStorageRules } from "@/routes/use-data";
import type { Device, StorageRuleItem } from "@/types";

type FormState = {
  scope_type: "global" | "device";
  scope_value: string;
  raw_mode: "full" | "relaxed" | "strict" | "disabled";
  summary_enabled: "true" | "false";
  summary_min_samples: string;
  heartbeat_interval_ms: string;
  target_temp_deadband: string;
  sim_temp_deadband: string;
  sensor_temp_deadband: string;
  error_deadband: string;
  integral_error_deadband: string;
  control_output_deadband: string;
  pwm_duty_deadband: string;
  pwm_norm_deadband: string;
  parameter_deadband: string;
  enabled: "true" | "false";
};

const DEFAULT_FORM: FormState = {
  scope_type: "global",
  scope_value: "*",
  raw_mode: "full",
  summary_enabled: "true",
  summary_min_samples: "12",
  heartbeat_interval_ms: "30000",
  target_temp_deadband: "0.05",
  sim_temp_deadband: "0.05",
  sensor_temp_deadband: "0.05",
  error_deadband: "0.02",
  integral_error_deadband: "1.0",
  control_output_deadband: "1.0",
  pwm_duty_deadband: "1.0",
  pwm_norm_deadband: "0.01",
  parameter_deadband: "0.01",
  enabled: "true",
};

const RAW_MODE_HELP: Record<FormState["raw_mode"], string> = {
  full: "Write all raw points.",
  relaxed: "Write first + heartbeat + meaningful changes (balanced for production).",
  strict: "Sparse raw writes and rely more on summary (for stable lines and lower storage load).",
  disabled: "No raw persistence.",
};

const RAW_MODE_PRESETS: Record<
  FormState["raw_mode"],
  Pick<
    FormState,
    | "heartbeat_interval_ms"
    | "summary_min_samples"
    | "target_temp_deadband"
    | "sim_temp_deadband"
    | "sensor_temp_deadband"
    | "error_deadband"
    | "integral_error_deadband"
    | "control_output_deadband"
    | "pwm_duty_deadband"
    | "pwm_norm_deadband"
    | "parameter_deadband"
  >
> = {
  full: {
    heartbeat_interval_ms: "30000",
    summary_min_samples: "12",
    target_temp_deadband: "0.05",
    sim_temp_deadband: "0.05",
    sensor_temp_deadband: "0.05",
    error_deadband: "0.02",
    integral_error_deadband: "1.0",
    control_output_deadband: "1.0",
    pwm_duty_deadband: "1.0",
    pwm_norm_deadband: "0.01",
    parameter_deadband: "0.01",
  },
  relaxed: {
    heartbeat_interval_ms: "30000",
    summary_min_samples: "12",
    target_temp_deadband: "0.08",
    sim_temp_deadband: "0.08",
    sensor_temp_deadband: "0.08",
    error_deadband: "0.03",
    integral_error_deadband: "1.5",
    control_output_deadband: "1.5",
    pwm_duty_deadband: "2.0",
    pwm_norm_deadband: "0.02",
    parameter_deadband: "0.02",
  },
  strict: {
    heartbeat_interval_ms: "45000",
    summary_min_samples: "12",
    target_temp_deadband: "0.12",
    sim_temp_deadband: "0.12",
    sensor_temp_deadband: "0.12",
    error_deadband: "0.05",
    integral_error_deadband: "2.5",
    control_output_deadband: "2.5",
    pwm_duty_deadband: "3.0",
    pwm_norm_deadband: "0.03",
    parameter_deadband: "0.03",
  },
  disabled: {
    heartbeat_interval_ms: "0",
    summary_min_samples: "12",
    target_temp_deadband: "0.12",
    sim_temp_deadband: "0.12",
    sensor_temp_deadband: "0.12",
    error_deadband: "0.05",
    integral_error_deadband: "2.5",
    control_output_deadband: "2.5",
    pwm_duty_deadband: "3.0",
    pwm_norm_deadband: "0.03",
    parameter_deadband: "0.03",
  },
};

export function StorageRulesPage() {
  const { items, loading, reload, createRule, updateRule, deleteRule } = useStorageRules();
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDeviceCodes, setSelectedDeviceCodes] = useState<string[]>([]);
  const [scopePickerOpen, setScopePickerOpen] = useState(false);
  const [scopePickerQuery, setScopePickerQuery] = useState("");
  const [scopePickerLoading, setScopePickerLoading] = useState(false);
  const [scopePickerItems, setScopePickerItems] = useState<Device[]>([]);
  const [editing, setEditing] = useState<StorageRuleItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const rawThresholdsVisible = form.raw_mode === "relaxed" || form.raw_mode === "strict";

  const sorted = useMemo(
    () => [...items].sort((a, b) => `${a.scope_type}:${a.scope_value}`.localeCompare(`${b.scope_type}:${b.scope_value}`)),
    [items]
  );
  const scopeError = useMemo(() => {
    if (form.scope_type === "global") return null;
    if (selectedDeviceCodes.length === 0) return "Device scope requires at least one device target.";
    return null;
  }, [form.scope_type, selectedDeviceCodes.length]);

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFormError(null);
  };

  const setRawMode = (mode: FormState["raw_mode"]) => {
    const preset = RAW_MODE_PRESETS[mode];
    setForm((prev) => ({
      ...prev,
      raw_mode: mode,
      ...preset,
    }));
    setFormError(null);
  };

  useEffect(() => {
    api.devices().then(setDevices).catch(() => setDevices([]));
  }, []);

  useEffect(() => {
    if (form.scope_type !== "device") {
      setScopePickerOpen(false);
      setScopePickerQuery("");
      return;
    }
    if (!scopePickerOpen) return;
    const q = scopePickerQuery.trim();
    if (q.length < 1) {
      setScopePickerItems(devices);
      return;
    }
    const timer = window.setTimeout(() => {
      setScopePickerLoading(true);
      api.devicesManage({ q, page: 1, page_size: 30 })
        .then((res) => setScopePickerItems(res.items))
        .catch(() => setScopePickerItems([]))
        .finally(() => setScopePickerLoading(false));
    }, 220);
    return () => window.clearTimeout(timer);
  }, [devices, form.scope_type, scopePickerOpen, scopePickerQuery]);

  useEffect(() => {
    if (form.scope_type === "global" && form.scope_value !== "*") {
      setForm((prev) => ({ ...prev, scope_value: "*" }));
      setSelectedDeviceCodes([]);
      return;
    }
    if (form.scope_type === "device") {
      const nextScopeValue = selectedDeviceCodes[0] ?? "";
      if (form.scope_value !== nextScopeValue) {
        setForm((prev) => ({ ...prev, scope_value: nextScopeValue }));
      }
    }
  }, [form.scope_type, form.scope_value, selectedDeviceCodes]);

  const openEdit = (item: StorageRuleItem) => {
    setEditing(item);
    setSelectedDeviceCodes(item.scope_type === "device" && item.scope_value ? [item.scope_value] : []);
    setForm({
      scope_type: item.scope_type === "device" ? "device" : "global",
      scope_value: item.scope_value,
      raw_mode: (item.raw_mode as FormState["raw_mode"]) ?? "full",
      summary_enabled: item.summary_enabled ? "true" : "false",
      summary_min_samples: String(item.summary_min_samples),
      heartbeat_interval_ms: String(item.heartbeat_interval_ms),
      target_temp_deadband: String(item.target_temp_deadband),
      sim_temp_deadband: String(item.sim_temp_deadband),
      sensor_temp_deadband: String(item.sensor_temp_deadband),
      error_deadband: String(item.error_deadband),
      integral_error_deadband: String(item.integral_error_deadband),
      control_output_deadband: String(item.control_output_deadband),
      pwm_duty_deadband: String(item.pwm_duty_deadband),
      pwm_norm_deadband: String(item.pwm_norm_deadband),
      parameter_deadband: String(item.parameter_deadband),
      enabled: item.enabled ? "true" : "false",
    });
  };

  const resetForm = () => {
    setEditing(null);
    setForm(DEFAULT_FORM);
    setSelectedDeviceCodes([]);
    setScopePickerOpen(false);
    setScopePickerQuery("");
    setScopePickerItems(devices);
  };

  const buildPayload = (scopeValueOverride?: string) => ({
    scope_type: form.scope_type,
    scope_value: (scopeValueOverride ?? form.scope_value).trim(),
    raw_mode: form.raw_mode,
    summary_enabled: form.summary_enabled === "true",
    summary_min_samples: Math.max(1, Number(form.summary_min_samples || "1")),
    heartbeat_interval_ms: Math.max(0, Number(form.heartbeat_interval_ms || "0")),
    target_temp_deadband: Math.max(0, Number(form.target_temp_deadband || "0")),
    sim_temp_deadband: Math.max(0, Number(form.sim_temp_deadband || "0")),
    sensor_temp_deadband: Math.max(0, Number(form.sensor_temp_deadband || "0")),
    error_deadband: Math.max(0, Number(form.error_deadband || "0")),
    integral_error_deadband: Math.max(0, Number(form.integral_error_deadband || "0")),
    control_output_deadband: Math.max(0, Number(form.control_output_deadband || "0")),
    pwm_duty_deadband: Math.max(0, Number(form.pwm_duty_deadband || "0")),
    pwm_norm_deadband: Math.max(0, Number(form.pwm_norm_deadband || "0")),
    parameter_deadband: Math.max(0, Number(form.parameter_deadband || "0")),
    enabled: form.enabled === "true",
  });

  const onSubmit = async () => {
    if (scopeError) {
      setFormError(scopeError);
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        const payload = buildPayload(form.scope_type === "device" ? selectedDeviceCodes[0] : form.scope_value);
        await updateRule(editing.id, payload);
      } else {
        if (form.scope_type === "device") {
          let created = 0;
          const failed: string[] = [];
          for (const deviceCode of selectedDeviceCodes) {
            try {
              await createRule(buildPayload(deviceCode));
              created += 1;
            } catch (e) {
              failed.push(`${deviceCode}: ${extractApiErrorMessage(e)}`);
            }
          }
          if (failed.length > 0) {
            const prefix = created > 0 ? `${created} rule(s) created. ` : "";
            setFormError(`${prefix}Some device rules failed: ${failed.slice(0, 3).join(" | ")}${failed.length > 3 ? " ..." : ""}`);
            reload();
            return;
          }
        } else {
          await createRule(buildPayload());
        }
      }
      resetForm();
      reload();
    } catch (e) {
      setFormError(extractApiErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  const selectedScopeDevices = useMemo(
    () => devices.filter((d) => selectedDeviceCodes.includes(d.code)),
    [devices, selectedDeviceCodes]
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Storage Rules</CardTitle>
          <Button variant="ghost" onClick={reload}>Refresh</Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-mute">
                <tr>
                  <th className="py-2 align-middle">Scope</th>
                  <th className="py-2 align-middle">Raw</th>
                  <th className="py-2 align-middle">Summary</th>
                  <th className="py-2 align-middle">Heartbeat</th>
                  <th className="py-2 align-middle">Enabled</th>
                  <th className="py-2 align-middle">Updated</th>
                  <th className="py-2 align-middle">Action</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((item) => (
                  <tr key={item.id} className="border-t border-line/60">
                    <td className="py-3 align-middle">{item.scope_type}:{item.scope_value}</td>
                    <td className="py-3 align-middle">
                      <Badge className={rawModeBadgeClass(item.raw_mode)}>{item.raw_mode}</Badge>
                    </td>
                    <td className="py-3 align-middle">
                      <div className="font-medium">{item.summary_enabled ? "Summary On" : "Summary Off"}</div>
                      <div className="text-xs text-mute">{item.summary_enabled ? `min samples: ${item.summary_min_samples}` : "aggregation disabled"}</div>
                    </td>
                    <td className="py-3 align-middle">
                      <div className="font-medium">{formatDuration(item.heartbeat_interval_ms)}</div>
                      <div className="text-xs text-mute">{item.heartbeat_interval_ms} ms</div>
                    </td>
                    <td className="py-3 align-middle">
                      <Badge className={item.enabled ? "border-accent/50 text-accent" : "border-line/60 text-mute"}>
                        {item.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </td>
                    <td className="py-3 align-middle">{new Date(item.updated_at).toLocaleString()} · {item.updated_by}</td>
                    <td className="py-3 align-middle">
                      <Button size="sm" variant="ghost" onClick={() => openEdit(item)}>Edit</Button>
                      <Button size="sm" variant="ghost" className="text-danger" onClick={() => setDeletingId(item.id)}>Delete</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {loading && <p className="text-sm text-mute">Loading storage rules...</p>}
          {!loading && items.length === 0 && <p className="text-sm text-mute">No storage rules.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div className="space-y-1">
            <CardTitle>{editing ? "Edit Storage Rule" : "Create Storage Rule"}</CardTitle>
            {editing ? (
              <p className="text-xs text-mute">
                Editing: <span className="text-text">{editing.scope_type}:{editing.scope_value}</span>
              </p>
            ) : (
              <p className="text-xs text-mute">Create a new rule. Scope + mode values are required.</p>
            )}
          </div>
          {editing ? <Button variant="ghost" onClick={resetForm}>Cancel Edit</Button> : null}
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-line/60 p-3 space-y-3">
            <h3 className="text-sm font-semibold text-text">Scope</h3>
            <div className="grid gap-3 md:grid-cols-4">
              <Field
                label="Scope Type"
                hint="Rule level"
                help="global = all devices, device = one specific device."
              >
                <Select value={form.scope_type} onValueChange={(v: "global" | "device") => setField("scope_type", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="global">global</SelectItem>
                    <SelectItem value="device">device</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field
                label="Scope Value"
                hint="Rule target"
                help={
                  form.scope_type === "global"
                    ? "Global scope always uses '*' automatically."
                    : editing
                      ? "Edit mode updates one existing device rule."
                      : "Select one or more devices from the searchable dropdown."
                }
              >
                {form.scope_type === "global" ? (
                  <Input value="*" disabled />
                ) : (
                  <DeviceScopeSearchSelect
                    open={scopePickerOpen}
                    setOpen={setScopePickerOpen}
                    query={scopePickerQuery}
                    setQuery={setScopePickerQuery}
                    loading={scopePickerLoading}
                    selectedCodes={selectedDeviceCodes}
                    items={scopePickerItems}
                    onToggle={(d) =>
                      setSelectedDeviceCodes((prev) => {
                        if (editing) return [d.code];
                        return prev.includes(d.code) ? prev.filter((x) => x !== d.code) : [...prev, d.code];
                      })
                    }
                  />
                )}
                {scopeError ? <span className="block text-[11px] leading-5 text-danger">{scopeError}</span> : null}
                {form.scope_type === "device" && selectedScopeDevices.length > 0 ? (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {selectedScopeDevices.map((d) => (
                      <button
                        key={d.id}
                        type="button"
                        className="rounded border border-neon/40 bg-neon/10 px-2 py-1 text-[11px] text-neon"
                        onClick={() => setSelectedDeviceCodes((prev) => prev.filter((x) => x !== d.code))}
                      >
                        {d.code} · {d.name}
                      </button>
                    ))}
                  </div>
                ) : null}
              </Field>
              <SelectFieldLabeled
                label="Enabled"
                hint="Master switch"
                help="Enabled applies this rule. Disabled keeps it stored but inactive."
                value={form.enabled}
                onChange={setField}
                fieldKey="enabled"
                options={[
                  { value: "true", label: "Enabled" },
                  { value: "false", label: "Disabled" },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-line/60 p-3 space-y-3">
            <h3 className="text-sm font-semibold text-text">Raw Storage</h3>
            <div className="grid gap-3 md:grid-cols-3">
              <Field
                label="Raw Mode"
                hint="Raw write strategy"
                help={
                  form.raw_mode === "full"
                    ? "Write every raw point. Threshold and heartbeat controls are not applied in this mode."
                    : form.raw_mode === "disabled"
                      ? "Raw persistence is disabled. Threshold and heartbeat controls are not applied."
                      : `${RAW_MODE_HELP[form.raw_mode]} Mode switch auto-applies heartbeat and threshold presets.`
                }
              >
                <Select value={form.raw_mode} onValueChange={(v: FormState["raw_mode"]) => setRawMode(v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full">full</SelectItem>
                    <SelectItem value="relaxed">relaxed</SelectItem>
                    <SelectItem value="strict">strict</SelectItem>
                    <SelectItem value="disabled">disabled</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </div>

            {!rawThresholdsVisible ? (
              <div className="rounded-md border border-line/60 bg-panel2/40 px-3 py-2 text-xs text-mute">
                {form.raw_mode === "full"
                  ? "Full mode writes each incoming raw point. Heartbeat and thresholds are hidden because they are not used for filtering."
                  : "Raw persistence is disabled. Heartbeat and threshold fields are hidden because they are not used."}
              </div>
            ) : (
              <>
                <div className="grid gap-3 md:grid-cols-3">
              <NumberField
                label="Heartbeat Interval ms"
                hint="Keepalive write interval"
                help={`Force at least one write every N ms even on tiny changes. Default: ${DEFAULT_FORM.heartbeat_interval_ms} ms (${formatDuration(Number(DEFAULT_FORM.heartbeat_interval_ms))}).`}
                value={form.heartbeat_interval_ms}
                onChange={(v) => setField("heartbeat_interval_ms", v)}
              />
              <Field label="Heartbeat Preview" hint="Human-readable" help="Display-only helper. Value is still saved in milliseconds.">
                <div className="h-10 rounded-md border border-line/60 bg-panel2 px-3 py-2 text-sm text-text">
                  {formatDuration(Number(form.heartbeat_interval_ms || 0))}
                </div>
              </Field>
                </div>
                <div className="space-y-2 rounded-md border border-line/60 bg-panel2/30 p-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-mute">Advanced Thresholds</h4>
              <div className="grid gap-3 md:grid-cols-3">
              <NumberField
                label="target_temp_deadband"
                hint="Target temperature threshold"
                help="Write when target temperature changes more than this value."
                value={form.target_temp_deadband}
                onChange={(v) => setField("target_temp_deadband", v)}
              />
              <NumberField
                label="sim_temp_deadband"
                hint="Simulated temperature threshold"
                help="Write when simulated temperature changes more than this value."
                value={form.sim_temp_deadband}
                onChange={(v) => setField("sim_temp_deadband", v)}
              />
              <NumberField
                label="sensor_temp_deadband"
                hint="Sensor temperature threshold"
                help="Write when sensor temperature changes more than this value."
                value={form.sensor_temp_deadband}
                onChange={(v) => setField("sensor_temp_deadband", v)}
              />
              <NumberField
                label="error_deadband"
                hint="Error threshold"
                help="Write when control error changes more than this value."
                value={form.error_deadband}
                onChange={(v) => setField("error_deadband", v)}
              />
              <NumberField
                label="integral_error_deadband"
                hint="Integral error threshold"
                help="Write when integral error changes more than this value."
                value={form.integral_error_deadband}
                onChange={(v) => setField("integral_error_deadband", v)}
              />
              <NumberField
                label="control_output_deadband"
                hint="Control output threshold"
                help="Write when control output changes more than this value."
                value={form.control_output_deadband}
                onChange={(v) => setField("control_output_deadband", v)}
              />
              <NumberField
                label="pwm_duty_deadband"
                hint="PWM duty threshold"
                help="Write when PWM duty changes more than this value."
                value={form.pwm_duty_deadband}
                onChange={(v) => setField("pwm_duty_deadband", v)}
              />
              <NumberField
                label="pwm_norm_deadband"
                hint="Normalized PWM threshold"
                help="Write when normalized PWM changes more than this value."
                value={form.pwm_norm_deadband}
                onChange={(v) => setField("pwm_norm_deadband", v)}
              />
              <NumberField
                label="parameter_deadband"
                hint="Parameter threshold"
                help="Write when control parameters (Kp/Ki/Kd, etc.) change more than this value."
                value={form.parameter_deadband}
                onChange={(v) => setField("parameter_deadband", v)}
              />
              </div>
                </div>
              </>
            )}
          </div>

          <div className="rounded-lg border border-line/60 p-3 space-y-3">
            <h3 className="text-sm font-semibold text-text">Summary Storage</h3>
            <div className="grid gap-3 md:grid-cols-3">
              <SelectFieldLabeled
                label="Summary Enabled"
                hint="Summary switch"
                help="Enabled writes summary windows; Disabled skips summary persistence."
                value={form.summary_enabled}
                onChange={setField}
                fieldKey="summary_enabled"
                options={[
                  { value: "true", label: "Enabled" },
                  { value: "false", label: "Disabled" },
                ]}
              />
              <NumberField
                label="Summary Min Samples"
                hint="Minimum samples"
                help={`Minimum samples required in one summary window before persisting. Default: ${DEFAULT_FORM.summary_min_samples}.`}
                value={form.summary_min_samples}
                onChange={(v) => setField("summary_min_samples", v)}
              />
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <Field
              label="Raw vs Summary"
              hint="Quick reference"
              help="Raw controls per-point writes. Summary controls aggregated window writes."
            >
              <div className="rounded border border-line/60 px-3 py-2 text-xs text-mute">
                Raw: deadband + heartbeat + raw_mode. Summary: summary_enabled + summary_min_samples.
              </div>
            </Field>
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}

          <div className="flex gap-2">
            <Button onClick={onSubmit} disabled={submitting || !!scopeError}>
              {submitting ? "Saving..." : editing ? "Save Changes" : "Create Rule"}
            </Button>
            {editing && <Button variant="ghost" onClick={resetForm}>Cancel</Button>}
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deletingId != null}
        title="Delete Storage Rule"
        description="This action cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        tone="danger"
        onCancel={() => setDeletingId(null)}
        onConfirm={async () => {
          if (deletingId == null) return;
          await deleteRule(deletingId);
          setDeletingId(null);
          if (editing?.id === deletingId) resetForm();
          reload();
        }}
      />
    </div>
  );
}

function Field({
  label,
  hint,
  help,
  children,
}: {
  label: string;
  hint?: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="space-y-1 text-xs text-mute">
      <span className="flex items-center gap-2">
        <span>{label}</span>
        {hint ? <span className="text-[11px] text-mute/80">{hint}</span> : null}
      </span>
      {children}
      {help ? <span className="block text-[11px] leading-5 text-mute/90">{help}</span> : null}
    </label>
  );
}

function NumberField({
  label,
  hint,
  help,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  help?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label} hint={hint} help={help}>
      <Input type="number" step="any" value={value} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function SelectFieldLabeled({
  label,
  hint,
  help,
  value,
  onChange,
  fieldKey,
  options,
}: {
  label: string;
  hint?: string;
  help?: string;
  value: string;
  onChange: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  fieldKey: "enabled" | "summary_enabled";
  options: Array<{ value: "true" | "false"; label: string }>;
}) {
  return (
    <Field label={label} hint={hint} help={help}>
      <Select value={value} onValueChange={(v: "true" | "false") => onChange(fieldKey, v)}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function DeviceScopeSearchSelect({
  open,
  setOpen,
  query,
  setQuery,
  loading,
  selectedCodes,
  items,
  onToggle,
}: {
  open: boolean;
  setOpen: (v: boolean) => void;
  query: string;
  setQuery: (v: string) => void;
  loading: boolean;
  selectedCodes: string[];
  items: Device[];
  onToggle: (d: Device) => void;
}) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const canNavigate = query.trim().length > 0 && items.length > 0;

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapperRef.current) return;
      const target = e.target as Node | null;
      if (target && !wrapperRef.current.contains(target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open, setOpen]);

  useEffect(() => {
    setHighlightedIndex(0);
  }, [open, query, items]);

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
      if (next) onToggle(next);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  }

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        className="flex h-10 w-full items-center justify-between rounded-md border border-line bg-panel2 px-3 text-left text-sm text-text"
        onClick={() => setOpen(!open)}
      >
        <span className="truncate">
          {selectedCodes.length > 0
            ? `${selectedCodes.length} device${selectedCodes.length > 1 ? "s" : ""} selected`
            : "Search and select device(s)"}
        </span>
        <ChevronDown className="h-4 w-4 text-mute" />
      </button>
      {open ? (
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
          <div className="max-h-56 space-y-1 overflow-auto">
            {loading ? <p className="px-2 py-1 text-xs text-mute">Searching...</p> : null}
            {!loading && query.trim().length === 0 ? <p className="px-2 py-1 text-xs text-mute">Type keywords to search devices</p> : null}
            {!loading && query.trim().length > 0 && items.length === 0 ? <p className="px-2 py-1 text-xs text-mute">No match</p> : null}
            {items.map((item, idx) => (
              <button
                key={item.id}
                type="button"
                className={`w-full rounded px-2 py-2 text-left text-sm ${
                  idx === highlightedIndex
                    ? "bg-neon/15 text-neon"
                    : selectedCodes.includes(item.code)
                      ? "bg-neon/10 text-neon"
                      : "text-text hover:bg-white/5"
                }`}
                onMouseEnter={() => setHighlightedIndex(idx)}
                onClick={() => onToggle(item)}
              >
                <div className="truncate">{selectedCodes.includes(item.code) ? "✓ " : ""}{item.name}</div>
                <div className="truncate text-xs text-mute">{item.code} · {item.line} · {item.location}</div>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function formatDuration(msRaw: number): string {
  const ms = Number.isFinite(msRaw) ? Math.max(0, msRaw) : 0;
  if (ms === 0) return "0 ms";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${trimTrailingZeros(seconds)} s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${trimTrailingZeros(minutes)} min`;
  const hours = minutes / 60;
  return `${trimTrailingZeros(hours)} h`;
}

function trimTrailingZeros(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
}

function rawModeBadgeClass(rawMode: string): string {
  if (rawMode === "full") return "border-accent/50 text-accent";
  if (rawMode === "relaxed") return "border-neon/40 text-neon";
  if (rawMode === "strict") return "border-warning/50 text-warning";
  if (rawMode === "disabled") return "border-line/60 text-mute";
  return "border-line/60 text-mute";
}

function extractApiErrorMessage(error: unknown): string {
  const fallback = error instanceof Error ? error.message : String(error);
  if (!fallback) return "Request failed.";
  try {
    const parsed = JSON.parse(fallback) as { detail?: string };
    if (parsed && typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail.trim();
  } catch {
    // keep fallback
  }
  return fallback;
}
