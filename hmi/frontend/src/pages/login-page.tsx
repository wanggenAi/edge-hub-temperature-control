import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>System Login</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="mb-1 block text-sm text-mute">Username / Email</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" />
            </div>
            <div>
              <label className="mb-1 block text-sm text-mute">Password</label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <p className="text-sm text-danger">{error}</p>}
            <Button className="w-full" disabled={submitting} type="submit">
              {submitting ? "Signing in..." : "Login"}
            </Button>
            <p className="text-xs text-mute">Demo: admin/admin123, operator1/operator123, viewer1/viewer123</p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
