import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAlarmsHmi } from "@/routes/use-data";
import type { AlarmRuleItem } from "@/types";

export function AlarmsPage() {
  const {
    loading,
    activeItems,
    activeTotal,
    activeStats,
    activePage,
    activePageSize,
    activeStatus,
    activeQ,
    setActivePage,
    setActivePageSize,
    setActiveStatus,
    setActiveQ,
    historyItems,
    historyTotal,
    historyPage,
    historyPageSize,
    historyQ,
    historyRange,
    historyType,
    historySource,
    setHistoryPage,
    setHistoryPageSize,
    setHistoryQ,
    setHistoryRange,
    setHistoryType,
    setHistorySource,
    rules,
    reload,
    updateRule,
  } = useAlarmsHmi();

  const [editingRule, setEditingRule] = useState<AlarmRuleItem | null>(null);
  const [ruleThreshold, setRuleThreshold] = useState("");
  const [ruleHoldSeconds, setRuleHoldSeconds] = useState("60");
  const [ruleLevel, setRuleLevel] = useState("warning");
  const [ruleEnabled, setRuleEnabled] = useState("true");
  const [savingRule, setSavingRule] = useState(false);

  const activeTotalPages = useMemo(() => Math.max(1, Math.ceil(activeTotal / activePageSize)), [activeTotal, activePageSize]);
  const historyTotalPages = useMemo(() => Math.max(1, Math.ceil(historyTotal / historyPageSize)), [historyTotal, historyPageSize]);

  function openRuleEdit(rule: AlarmRuleItem) {
    setEditingRule(rule);
    setRuleThreshold(rule.threshold);
    setRuleHoldSeconds(String(rule.hold_seconds));
    setRuleLevel(rule.severity);
    setRuleEnabled(rule.enabled ? "true" : "false");
  }

  async function saveRule() {
    if (!editingRule) return;
    setSavingRule(true);
    try {
      await updateRule(editingRule.id, {
        threshold: ruleThreshold,
        hold_seconds: Math.max(1, Number(ruleHoldSeconds || 1)),
        level: ruleLevel,
        enabled: ruleEnabled === "true",
      });
      setEditingRule(null);
      reload();
    } finally {
      setSavingRule(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Active Alarms</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-3">
            <StatCard title="Active Total" value={activeStats.active_total} />
            <StatCard title="Critical" value={activeStats.critical} tone="critical" />
            <StatCard title="Warning" value={activeStats.warning} tone="warning" />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="max-w-sm"
              placeholder="Search by alarm/device/reason"
              value={activeQ}
              onChange={(e) => {
                setActiveQ(e.target.value);
                setActivePage(1);
              }}
            />
            <Select
              value={activeStatus}
              onValueChange={(v: "active" | "all") => {
                setActiveStatus(v);
                setActivePage(1);
              }}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="all">All</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={String(activePageSize)}
              onValueChange={(v) => {
                setActivePageSize(Number(v));
                setActivePage(1);
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
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-mute">
                <tr>
                  <th className="py-2">Alarm Name</th>
                  <th>Severity</th>
                  <th>Device</th>
                  <th>Triggered At</th>
                  <th>Status</th>
                  <th>Reason</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {activeItems.map((a) => (
                  <tr key={a.id} className="border-t border-line/60">
                    <td className="py-2 font-medium text-text">{a.alarm_name}</td>
                    <td><Badge className={levelBadge(a.severity)}>{a.severity}</Badge></td>
                    <td>{a.device_code} · {a.device_name}</td>
                    <td>{new Date(a.triggered_at).toLocaleString()}</td>
                    <td>
                      <Badge className={a.status === "Active" ? "border-danger/50 text-danger" : "border-accent/50 text-accent"}>
                        {a.status}
                      </Badge>
                    </td>
                    <td className="max-w-[460px] truncate text-mute">{a.reason}</td>
                    <td className="text-mute">{a.acknowledged ? "Acknowledged" : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {loading && <p className="text-sm text-mute">Loading active alarms...</p>}
          {!loading && activeItems.length === 0 && <p className="text-sm text-mute">No alarms found.</p>}

          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" disabled={activePage <= 1} onClick={() => setActivePage(activePage - 1)}>Prev</Button>
            <span className="text-xs text-mute">Page {activePage} / {activeTotalPages}</span>
            <Button variant="ghost" size="sm" disabled={activePage >= activeTotalPages} onClick={() => setActivePage(activePage + 1)}>Next</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Alarm History</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-[minmax(240px,1fr)_120px_180px_180px]">
            <Input
              className="max-w-none"
              placeholder="Search by device/alarm"
              value={historyQ}
              onChange={(e) => {
                setHistoryQ(e.target.value);
                setHistoryPage(1);
              }}
            />
            <Select
              value={historyRange}
              onValueChange={(v: "24h" | "7d") => {
                setHistoryRange(v);
                setHistoryPage(1);
              }}
            >
              <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="24h">24h</SelectItem>
                <SelectItem value="7d">7d</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={historyType ?? "all"}
              onValueChange={(v) => {
                setHistoryType(v === "all" ? undefined : v);
                setHistoryPage(1);
              }}
            >
              <SelectTrigger className="min-w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                <SelectItem value="out_of_band">Out of Band</SelectItem>
                <SelectItem value="sensor_invalid">Sensor Invalid</SelectItem>
                <SelectItem value="high_saturation">High Saturation</SelectItem>
                <SelectItem value="param_apply_failed">Param Apply Failed</SelectItem>
                <SelectItem value="device_offline">Device Offline</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={historySource ?? "all"}
              onValueChange={(v) => {
                setHistorySource(v === "all" ? undefined : v);
                setHistoryPage(1);
              }}
            >
              <SelectTrigger className="min-w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Sources</SelectItem>
                <SelectItem value="telemetry">telemetry</SelectItem>
                <SelectItem value="params_ack">params_ack</SelectItem>
                <SelectItem value="device_status">device_status</SelectItem>
                <SelectItem value="rule_engine">rule_engine</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-mute">
                <tr>
                  <th className="py-2">Time</th>
                  <th>Device</th>
                  <th>Alarm Type</th>
                  <th>Severity</th>
                  <th>Duration</th>
                  <th>Recovery</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {historyItems.map((h) => (
                  <tr key={h.id} className="border-t border-line/60">
                    <td className="py-2">{new Date(h.time).toLocaleString()}</td>
                    <td>{h.device_code} · {h.device_name}</td>
                    <td>{alarmTypeLabel(h.alarm_type)}</td>
                    <td><Badge className={levelBadge(h.severity)}>{h.severity}</Badge></td>
                    <td>{h.duration_seconds == null ? "-" : formatDuration(h.duration_seconds)}</td>
                    <td>{h.recovery}</td>
                    <td>{sourceLabel(h.source)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {loading && <p className="text-sm text-mute">Loading history...</p>}
          {!loading && historyItems.length === 0 && <p className="text-sm text-mute">No history in this range.</p>}

          <div className="flex items-center justify-end gap-2">
            <Select
              value={String(historyPageSize)}
              onValueChange={(v) => {
                setHistoryPageSize(Number(v));
                setHistoryPage(1);
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
            <Button variant="ghost" size="sm" disabled={historyPage <= 1} onClick={() => setHistoryPage(historyPage - 1)}>Prev</Button>
            <span className="text-xs text-mute">Page {historyPage} / {historyTotalPages}</span>
            <Button variant="ghost" size="sm" disabled={historyPage >= historyTotalPages} onClick={() => setHistoryPage(historyPage + 1)}>Next</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alarm Rules</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-mute">
                <tr>
                  <th className="py-2">Rule Name</th>
                  <th>Target</th>
                  <th>Threshold</th>
                  <th>Hold Duration</th>
                  <th>Severity</th>
                  <th>Enabled</th>
                  <th>Edit</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id} className="border-t border-line/60">
                    <td className="py-2">
                      <div className="font-medium">{r.name}</div>
                      <div className="text-xs text-mute">{r.rule_code}</div>
                    </td>
                    <td>{r.target}</td>
                    <td>{r.operator} {r.threshold}</td>
                    <td>{r.hold_seconds}s</td>
                    <td><Badge className={levelBadge(r.severity)}>{r.severity}</Badge></td>
                    <td>{r.enabled ? "Yes" : "No"}</td>
                    <td>
                      <Button size="sm" variant="ghost" onClick={() => openRuleEdit(r)}>
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={Boolean(editingRule)}
        title={editingRule ? `Edit Rule: ${editingRule.name}` : "Edit Rule"}
        description={
          editingRule ? (
            <div className="space-y-2">
              <Input value={ruleThreshold} onChange={(e) => setRuleThreshold(e.target.value)} placeholder="Threshold" />
              <Input value={ruleHoldSeconds} onChange={(e) => setRuleHoldSeconds(e.target.value)} placeholder="Hold seconds" type="number" />
              <Select value={ruleLevel} onValueChange={setRuleLevel}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="critical">critical</SelectItem>
                  <SelectItem value="warning">warning</SelectItem>
                  <SelectItem value="info">info</SelectItem>
                </SelectContent>
              </Select>
              <Select value={ruleEnabled} onValueChange={setRuleEnabled}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">Enabled</SelectItem>
                  <SelectItem value="false">Disabled</SelectItem>
                </SelectContent>
              </Select>
              <div className="text-xs text-mute">
                Last Updated: {editingRule ? new Date(editingRule.updated_at).toLocaleString() : "-"} · Updated By: {editingRule?.updated_by ?? "-"}
              </div>
            </div>
          ) : (
            "Rule editor"
          )
        }
        confirmLabel={savingRule ? "Saving..." : "Save Rule"}
        busy={savingRule}
        onCancel={() => !savingRule && setEditingRule(null)}
        onConfirm={saveRule}
      />
    </div>
  );
}

function StatCard({ title, value, tone = "default" }: { title: string; value: number; tone?: "default" | "critical" | "warning" }) {
  const cls = tone === "critical" ? "text-danger" : tone === "warning" ? "text-warn" : "text-neon";
  return (
    <div className="rounded-lg border border-line bg-panel2 p-3">
      <div className="text-xs uppercase tracking-wide text-mute">{title}</div>
      <div className={`mt-1 text-2xl font-semibold ${cls}`}>{value}</div>
    </div>
  );
}

function levelBadge(level: string) {
  if (level === "critical") return "border-danger/60 text-danger";
  if (level === "warning") return "border-warn/60 text-warn";
  return "border-neon/50 text-neon";
}

function formatDuration(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function alarmTypeLabel(code: string): string {
  const map: Record<string, string> = {
    out_of_band: "Out of Band",
    sensor_invalid: "Sensor Invalid",
    high_saturation: "High Saturation",
    param_apply_failed: "Param Apply Failed",
    device_offline: "Device Offline",
  };
  return map[code] ?? code;
}

function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    telemetry: "Telemetry",
    params_ack: "Params Ack",
    device_status: "Device Status",
    rule_engine: "Rule Engine",
  };
  return map[source] ?? source;
}
