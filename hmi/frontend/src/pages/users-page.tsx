import { FormEvent, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useUsers } from "@/routes/use-data";
import type { Role, UserItem } from "@/types";

const roles: Role[] = ["admin", "operator", "viewer"];

export function UsersPage() {
  const { users, createUser, updateUser, deleteUser, loading, reload } = useUsers();
  const [form, setForm] = useState({ username: "", email: "", password: "", role: "viewer" as Role });
  const [editing, setEditing] = useState<{ id: number; role: Role; active: boolean } | null>(null);
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

  const sortedUsers = useMemo(
    () => [...users].sort((a, b) => a.username.localeCompare(b.username)),
    [users]
  );

  async function submit(e: FormEvent) {
    e.preventDefault();
    setConfirm({
      open: true,
      title: "Confirm User Creation",
      description: `Create user ${form.username || "(no username)"} with role ${form.role}?`,
      tone: "accent",
      action: async () => {
        await createUser({ username: form.username, email: form.email, password: form.password, roles: [form.role] });
        setForm({ username: "", email: "", password: "", role: "viewer" });
        reload();
      },
    });
  }

  async function saveEdit(user: UserItem) {
    if (!editing) return;
    setConfirm({
      open: true,
      title: "Confirm User Update",
      description: `Apply role/status changes for ${user.username}?`,
      tone: "accent",
      action: async () => {
        await updateUser(user.id, {
          roles: [editing.role],
          is_active: editing.active,
        });
        setEditing(null);
        reload();
      },
    });
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>User Management</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-2 md:grid-cols-5" onSubmit={submit}>
            <Input
              placeholder="username"
              value={form.username}
              onChange={(e) => setForm((s) => ({ ...s, username: e.target.value }))}
            />
            <Input
              placeholder="email"
              value={form.email}
              onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))}
            />
            <Input
              placeholder="password"
              type="password"
              value={form.password}
              onChange={(e) => setForm((s) => ({ ...s, password: e.target.value }))}
            />
            <Select value={form.role} onValueChange={(v) => setForm((s) => ({ ...s, role: v as Role }))}>
              <SelectTrigger>
                <SelectValue placeholder="Select role" />
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role} value={role}>
                    {role}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button type="submit">Add User</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>User List</CardTitle>
        </CardHeader>
        <CardContent>
          {loading && <p className="text-sm text-mute">Loading...</p>}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-mute">
                <tr>
                  <th className="py-2">Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sortedUsers.map((u) => {
                  const isEditing = editing?.id === u.id;
                  return (
                    <tr key={u.id} className="border-t border-line/60">
                      <td className="py-2">{u.username}</td>
                      <td>{u.email}</td>
                      <td className="min-w-40">
                        {isEditing ? (
                          <Select
                            value={editing.role}
                            onValueChange={(v) => setEditing((prev) => (prev ? { ...prev, role: v as Role } : prev))}
                          >
                            <SelectTrigger className="h-8">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {roles.map((role) => (
                                <SelectItem key={role} value={role}>
                                  {role}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          u.roles.join(", ")
                        )}
                      </td>
                      <td className="min-w-40">
                        {isEditing ? (
                          <Select
                            value={editing.active ? "active" : "inactive"}
                            onValueChange={(v) => setEditing((prev) => (prev ? { ...prev, active: v === "active" } : prev))}
                          >
                            <SelectTrigger className="h-8">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="active">active</SelectItem>
                              <SelectItem value="inactive">inactive</SelectItem>
                            </SelectContent>
                          </Select>
                        ) : u.is_active ? (
                          "active"
                        ) : (
                          "inactive"
                        )}
                      </td>
                      <td className="space-x-2 text-right">
                        {isEditing ? (
                          <>
                            <Button variant="accent" size="sm" onClick={() => saveEdit(u)}>
                              Save
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>
                              Cancel
                            </Button>
                          </>
                        ) : (
                          <>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setEditing({
                                  id: u.id,
                                  role: (u.roles[0] ?? "viewer") as Role,
                                  active: u.is_active,
                                })
                              }
                            >
                              Edit
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setConfirm({
                                  open: true,
                                  title: "Confirm User Deletion",
                                  description: `Delete user ${u.username}? This action cannot be undone.`,
                                  tone: "danger",
                                  action: async () => {
                                    await deleteUser(u.id);
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
