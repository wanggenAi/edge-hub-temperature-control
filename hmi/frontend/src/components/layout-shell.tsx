import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Activity, Bell, Gauge, HardDrive, History, LogOut, PanelLeftClose, PanelLeftOpen, Users } from "lucide-react";

import { useAuth } from "@/app/auth";
import { Badge } from "@/components/ui/badge";

export function LayoutShell({ children }: { children: React.ReactNode }) {
  const { user, logout, hasRole } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between px-4 py-3">
          <div>
            <div className="text-lg font-bold text-neon">Intelligent Temperature</div>
            <div className="text-xs text-mute">Industrial Multi-Device HMI</div>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <Badge className="border-accent/60 text-accent">Online</Badge>
            <span className="text-mute">User: {user?.username}</span>
            <button className="inline-flex items-center gap-1 text-mute hover:text-text" onClick={logout}>
              <LogOut className="h-4 w-4" /> Logout
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1600px] gap-4 p-4">
        <aside className={`${collapsed ? "w-16" : "w-56"} shrink-0 rounded-xl border border-line/80 bg-panel/90 p-2.5 shadow-panel transition-all`}>
          <div className="mb-3 flex items-center justify-between gap-2 rounded border border-neon/25 bg-neon/10 px-2 py-2 text-sm font-semibold text-neon">
            <span className={collapsed ? "hidden" : "block"}>Factory HMI Line</span>
            <button className="rounded border border-line/60 p-1 text-mute hover:text-text" onClick={() => setCollapsed((s) => !s)}>
              {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </button>
          </div>
          <nav className="space-y-1">
            <NavItem to="/" icon={<Gauge className="h-4 w-4" />} label="Overview" collapsed={collapsed} />
            <NavItem to="/devices/manage" icon={<HardDrive className="h-4 w-4" />} label="Device Management" collapsed={collapsed} />
            <NavItem to="/alarms" icon={<Bell className="h-4 w-4" />} label="Alarms" collapsed={collapsed} />
            <NavItem to="/history" icon={<History className="h-4 w-4" />} label="History" collapsed={collapsed} />
            {hasRole("admin") && (
              <NavItem to="/users" icon={<Users className="h-4 w-4" />} label="User Management" collapsed={collapsed} />
            )}
          </nav>
          <div className={`mt-5 rounded border border-line/60 bg-panel2/70 p-2 text-[11px] text-mute ${collapsed ? "hidden" : "block"}`}>
            <div className="mb-1 flex items-center gap-1 text-accent">
              <Activity className="h-3 w-3" /> Current Role
            </div>
            <div>{user?.roles.join(", ")}</div>
          </div>
        </aside>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

function NavItem({ to, icon, label, collapsed = false }: { to: string; icon: React.ReactNode; label: string; collapsed?: boolean }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "flex items-center rounded-md py-2 text-sm transition-colors",
          collapsed ? "justify-center px-2" : "gap-2 px-3",
          isActive ? "bg-neon/15 text-neon" : "text-mute hover:bg-white/5 hover:text-text",
        ].join(" ")
      }
      end={to === "/"}
    >
      {icon}
      {!collapsed && label}
    </NavLink>
  );
}

export function LogoLink() {
  return <Link to="/" className="text-neon">Home</Link>;
}
