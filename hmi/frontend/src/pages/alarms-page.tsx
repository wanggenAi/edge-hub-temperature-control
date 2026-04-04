import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAlarmCenter } from "@/routes/use-data";

export function AlarmsPage() {
  const { items, total, page, pageSize, q, loading, setPage, setPageSize, setQ, reload } = useAlarmCenter();

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Alarm Center</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="max-w-sm"
              placeholder="Search alarms by title/message/device"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                setPageSize(Number(v));
                setPage(1);
              }}
            >
              <SelectTrigger className="h-9 w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="20">20 / page</SelectItem>
                <SelectItem value="50">50 / page</SelectItem>
                <SelectItem value="100">100 / page</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="ghost" onClick={reload}>Refresh</Button>
            <span className="text-xs text-mute">Total: {total}</span>
          </div>

          {loading && <p className="text-sm text-mute">Loading alarms...</p>}

          <div className="space-y-2">
            {items.map((alarm) => (
              <div key={alarm.id} className="rounded-lg border border-line bg-panel2 p-3">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <div className="font-semibold text-text">{alarm.title}</div>
                  <div className="flex items-center gap-2">
                    <Badge className={levelBadge(alarm.level)}>{alarm.level}</Badge>
                    <Badge className={alarm.is_active ? "border-danger/50 text-danger" : "border-accent/50 text-accent"}>
                      {alarm.is_active ? "active" : "acknowledged"}
                    </Badge>
                  </div>
                </div>
                <div className="mb-1 text-sm text-mute">{alarm.message}</div>
                <div className="text-xs text-mute">
                  {alarm.device_code} · {alarm.device_name} · {new Date(alarm.created_at).toLocaleString()}
                </div>
              </div>
            ))}
            {!loading && items.length === 0 && <p className="text-sm text-mute">No alarms found.</p>}
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</Button>
            <span className="text-xs text-mute">Page {page} / {totalPages}</span>
            <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function levelBadge(level: string) {
  if (level === "critical") return "border-danger/60 text-danger";
  if (level === "warning") return "border-warn/60 text-warn";
  return "border-neon/50 text-neon";
}
