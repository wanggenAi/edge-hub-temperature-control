import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useDeviceManage } from "@/routes/use-data";

export function DeviceManagePage() {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");
  const { items, total, page, pageSize, q, loading, setPage, setPageSize, setQ, reload, createDevice, updateDevice, deleteDevice } = useDeviceManage();

  const [form, setForm] = useState({
    code: "",
    name: "",
    line: "Line 1",
    location: "Zone A",
    target_temp: "37",
  });
  const [editing, setEditing] = useState<{ id: number; name: string; line: string; location: string; target_temp: string; status: string } | null>(null);
  const [confirm, setConfirm] = useState<{
    open: boolean;
    title: string;
    description: string;
    tone?: "accent" | "danger";
    action: null | (() => Promise<void>);
  }>({
    open: false,
    title: "",
    description: "",
    tone: "accent",
    action: null,
  });
  const [confirmBusy, setConfirmBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setConfirm({
      open: true,
      title: "Confirm Device Creation",
      description: `Create device ${form.code || "(no code)"} with target ${form.target_temp}°C?`,
      tone: "accent",
      action: async () => {
        await createDevice({
          code: form.code,
          name: form.name,
          line: form.line,
          location: form.location,
          target_temp: Number(form.target_temp),
          status: "active",
          current_temp: Number(form.target_temp) - 0.8,
          pwm_output: 30,
          is_alarm: false,
          is_online: true,
        });
        setForm({ code: "", name: "", line: "Line 1", location: "Zone A", target_temp: "37" });
        reload();
      },
    });
  }

  async function saveEdit() {
    if (!editing) return;
    setConfirm({
      open: true,
      title: "Confirm Device Update",
      description: `Save changes for device #${editing.id}?`,
      tone: "accent",
      action: async () => {
        await updateDevice(editing.id, {
          name: editing.name,
          line: editing.line,
          location: editing.location,
          target_temp: Number(editing.target_temp),
          status: editing.status,
        });
        setEditing(null);
        reload();
      },
    });
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Device Management</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-2 md:grid-cols-6" onSubmit={submit}>
            <Input
              placeholder="Code (TC-401)"
              value={form.code}
              onChange={(e) => setForm((s) => ({ ...s, code: e.target.value }))}
            />
            <Input placeholder="Name" value={form.name} onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} />
            <Input placeholder="Line" value={form.line} onChange={(e) => setForm((s) => ({ ...s, line: e.target.value }))} />
            <Input
              placeholder="Location"
              value={form.location}
              onChange={(e) => setForm((s) => ({ ...s, location: e.target.value }))}
            />
            <Input
              placeholder="Target Temp"
              type="number"
              value={form.target_temp}
              onChange={(e) => setForm((s) => ({ ...s, target_temp: e.target.value }))}
            />
            <Button type="submit">Add Device</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Device List</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="max-w-sm"
              placeholder="Search by code/name/line/location"
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
                <SelectItem value="10">10 / page</SelectItem>
                <SelectItem value="20">20 / page</SelectItem>
                <SelectItem value="50">50 / page</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="ghost" onClick={reload}>Refresh</Button>
            <span className="text-xs text-mute">Total: {total}</span>
          </div>

          {loading && <p className="text-sm text-mute">Loading...</p>}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-mute">
                <tr>
                  <th className="py-2">Code</th>
                  <th>Name</th>
                  <th>Line</th>
                  <th>Location</th>
                  <th>Target</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((d) => {
                  const isEditing = editing?.id === d.id;
                  return (
                    <tr key={d.id} className="border-t border-line/60">
                      <td className="py-2">{d.code}</td>
                      <td>
                        {isEditing ? (
                          <Input className="h-8" value={editing.name} onChange={(e) => setEditing((s) => (s ? { ...s, name: e.target.value } : s))} />
                        ) : (
                          d.name
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <Input className="h-8" value={editing.line} onChange={(e) => setEditing((s) => (s ? { ...s, line: e.target.value } : s))} />
                        ) : (
                          d.line
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <Input className="h-8" value={editing.location} onChange={(e) => setEditing((s) => (s ? { ...s, location: e.target.value } : s))} />
                        ) : (
                          d.location
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <Input className="h-8" type="number" value={editing.target_temp} onChange={(e) => setEditing((s) => (s ? { ...s, target_temp: e.target.value } : s))} />
                        ) : (
                          `${d.target_temp.toFixed(1)}°C`
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <Select value={editing.status} onValueChange={(v) => setEditing((s) => (s ? { ...s, status: v } : s))}>
                            <SelectTrigger className="h-8 min-w-32">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="active">active</SelectItem>
                              <SelectItem value="maintenance">maintenance</SelectItem>
                              <SelectItem value="offline">offline</SelectItem>
                            </SelectContent>
                          </Select>
                        ) : (
                          d.status
                        )}
                      </td>
                      <td className="space-x-2 text-right">
                        {isEditing ? (
                          <>
                            <Button variant="accent" size="sm" disabled={!canEdit} onClick={saveEdit}>Save</Button>
                            <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>Cancel</Button>
                          </>
                        ) : (
                          <>
                            <Button variant="ghost" size="sm" onClick={() => navigate(`/devices/${d.id}`)}>
                              Open
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={!canEdit}
                              onClick={() =>
                                setEditing({
                                  id: d.id,
                                  name: d.name,
                                  line: d.line,
                                  location: d.location,
                                  target_temp: String(d.target_temp),
                                  status: d.status,
                                })
                              }
                            >
                              Edit
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={!canEdit}
                              onClick={() =>
                                setConfirm({
                                  open: true,
                                  title: "Confirm Device Deletion",
                                  description: `Delete ${d.code} · ${d.name}? This action cannot be undone.`,
                                  tone: "danger",
                                  action: async () => {
                                    await deleteDevice(d.id);
                                    reload();
                                  },
                                })
                              }
                            >
                              Delete
                            </Button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</Button>
            <span className="text-xs text-mute">Page {page} / {totalPages}</span>
            <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirm.open}
        title={confirm.title}
        description={confirm.description}
        tone={confirm.tone ?? "accent"}
        confirmLabel={confirm.tone === "danger" ? "Delete" : "Confirm"}
        busy={confirmBusy}
        onCancel={() => !confirmBusy && setConfirm((s) => ({ ...s, open: false }))}
        onConfirm={async () => {
          if (!confirm.action) return;
          setConfirmBusy(true);
          try {
            await confirm.action();
            setConfirm((s) => ({ ...s, open: false }));
          } finally {
            setConfirmBusy(false);
          }
        }}
      />
    </div>
  );
}
