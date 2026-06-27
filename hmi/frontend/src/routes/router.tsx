import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "@/app/auth";
import { LayoutShell } from "@/components/layout-shell";
import type { Role } from "@/types";

const LoginPage = lazy(() => import("@/pages/login-page").then((module) => ({ default: module.LoginPage })));
const OverviewPage = lazy(() => import("@/pages/overview-page").then((module) => ({ default: module.OverviewPage })));
const DeviceManagePage = lazy(() => import("@/pages/device-manage-page").then((module) => ({ default: module.DeviceManagePage })));
const DeviceDetailPage = lazy(() => import("@/pages/device-detail-page").then((module) => ({ default: module.DeviceDetailPage })));
const AIPage = lazy(() => import("@/pages/ai-page").then((module) => ({ default: module.AIPage })));
const AlarmsPage = lazy(() => import("@/pages/alarms-page").then((module) => ({ default: module.AlarmsPage })));
const HistoryPage = lazy(() => import("@/pages/history-page").then((module) => ({ default: module.HistoryPage })));
const OpsPage = lazy(() => import("@/pages/ops-page").then((module) => ({ default: module.OpsPage })));
const StorageRulesPage = lazy(() => import("@/pages/storage-rules-page").then((module) => ({ default: module.StorageRulesPage })));
const UsersPage = lazy(() => import("@/pages/users-page").then((module) => ({ default: module.UsersPage })));

function RouteLoading() {
  return <div className="p-6 text-sm text-mute">Loading...</div>;
}

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
    <Suspense fallback={<RouteLoading />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Protected />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/devices/manage" element={<DeviceManagePage />} />
          <Route path="/devices/:id" element={<DeviceDetailPage />} />
          <Route path="/ai" element={<AIPage />} />
          <Route path="/alarms" element={<AlarmsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route element={<RoleGuard roles={["admin"]} />}>
            <Route path="/ops" element={<OpsPage />} />
            <Route path="/storage-rules" element={<StorageRulesPage />} />
            <Route path="/users" element={<UsersPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
