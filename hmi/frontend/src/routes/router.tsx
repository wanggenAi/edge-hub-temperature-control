import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "@/app/auth";
import { LayoutShell } from "@/components/layout-shell";
import { AlarmsPage } from "@/pages/alarms-page";
import { DeviceDetailPage } from "@/pages/device-detail-page";
import { DeviceManagePage } from "@/pages/device-manage-page";
import { HistoryPage } from "@/pages/history-page";
import { LoginPage } from "@/pages/login-page";
import { OverviewPage } from "@/pages/overview-page";
import { StorageRulesPage } from "@/pages/storage-rules-page";
import { UsersPage } from "@/pages/users-page";
import type { Role } from "@/types";

function Protected() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-6 text-sm text-mute">Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <LayoutShell>
      <Outlet />
    </LayoutShell>
  );
}

function RoleGuard({ roles }: { roles: Role[] }) {
  const { hasRole } = useAuth();
  if (!hasRole(...roles)) return <Navigate to="/" replace />;
  return <Outlet />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/devices/manage" element={<DeviceManagePage />} />
        <Route path="/devices/:id" element={<DeviceDetailPage />} />
        <Route path="/alarms" element={<AlarmsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route element={<RoleGuard roles={["admin"]} />}>
          <Route path="/storage-rules" element={<StorageRulesPage />} />
          <Route path="/users" element={<UsersPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
