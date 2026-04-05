import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useStorageRules } from "@/routes/use-data";
import type { StorageRuleItem } from "@/types";

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
  summary_min_samples: "3",
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
  full: "Write all raw points. Highest fidelity and highest storage usage.",
  relaxed: "Moderate deduplication. Fewer writes on small changes, balanced cost/fidelity.",
  strict: "Aggressive deduplication. Write only on significant changes, lowest storage usage.",
  disabled: "Disable raw writes. Keep summary only (if summary is enabled).",
};

export function StorageRulesPage() {
  const { items, loading, reload, createRule, updateRule, deleteRule } = useStorageRules();
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [editing, setEditing] = useState<StorageRuleItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const sorted = useMemo(
    () => [...items].sort((a, b) => `${a.scope_type}:${a.scope_value}`.localeCompare(`${b.scope_type}:${b.scope_value}`)),
    [items]
  );

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const openEdit = (item: StorageRuleItem) => {
    setEditing(item);
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
  };

  const buildPayload = () => ({
    scope_type: form.scope_type,
    scope_value: form.scope_value.trim(),
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
    setSubmitting(true);
    try {
      const payload = buildPayload();
      if (editing) {
        await updateRule(editing.id, payload);
      } else {
        await createRule(payload);
      }
      resetForm();
      reload();
    } finally {
      setSubmitting(false);
    }
  };

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
                      <div className="font-medium">{item.raw_mode}</div>
                      <div className="text-xs text-mute">{RAW_MODE_HELP[item.raw_mode as FormState["raw_mode"]] ?? "-"}</div>
                    </td>
                    <td className="py-3 align-middle">
                      {item.summary_enabled ? `On (min ${item.summary_min_samples})` : "Off"}
                    </td>
                    <td className="py-3 align-middle">{item.heartbeat_interval_ms} ms</td>
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
        <CardHeader>
          <CardTitle>{editing ? "Edit Storage Rule" : "Create Storage Rule"}</CardTitle>
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
                help="Use * for global. For device scope, use a device code such as TC-101."
              >
                <Input value={form.scope_value} onChange={(e) => setField("scope_value", e.target.value)} />
              </Field>
              <SelectField
                label="Enabled"
                hint="Master switch"
                help="When false, this rule is fully inactive."
                value={form.enabled}
                onChange={(v) => setField("enabled", v === "false" ? "false" : "true")}
                options={["true", "false"]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-line/60 p-3 space-y-3">
            <h3 className="text-sm font-semibold text-text">Raw Storage</h3>
            <div className="grid gap-3 md:grid-cols-3">
              <Field
                label="Raw Mode"
                hint="Raw write strategy"
                help={RAW_MODE_HELP[form.raw_mode]}
              >
                <Select value={form.raw_mode} onValueChange={(v: FormState["raw_mode"]) => setField("raw_mode", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full">full</SelectItem>
                    <SelectItem value="relaxed">relaxed</SelectItem>
                    <SelectItem value="strict">strict</SelectItem>
                    <SelectItem value="disabled">disabled</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <NumberField
                label="Heartbeat Interval ms"
                hint="Keepalive write interval"
                help="Force at least one write every N ms even on tiny changes. Typical: 30000."
                value={form.heartbeat_interval_ms}
                onChange={(v) => setField("heartbeat_interval_ms", v)}
              />
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

          <div className="rounded-lg border border-line/60 p-3 space-y-3">
            <h3 className="text-sm font-semibold text-text">Summary Storage</h3>
            <div className="grid gap-3 md:grid-cols-3">
              <Field
                label="Summary Enabled"
                hint="Summary switch"
                help="true = write summary windows; false = skip summary writes."
              >
                <Select value={form.summary_enabled} onValueChange={(v: "true" | "false") => setField("summary_enabled", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">true</SelectItem>
                    <SelectItem value="false">false</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <NumberField
                label="Summary Min Samples"
                hint="Minimum samples"
                help="Minimum samples required in one summary window before persisting. Typical: 3."
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

          <div className="flex gap-2">
            <Button onClick={onSubmit} disabled={submitting || !form.scope_value.trim()}>
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

function SelectField({
  label,
  hint,
  help,
  value,
  onChange,
  options,
}: {
  label: string;
  hint?: string;
  help?: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <Field label={label} hint={hint} help={help}>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}
