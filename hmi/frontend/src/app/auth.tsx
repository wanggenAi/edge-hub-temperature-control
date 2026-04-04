import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { Me, Role } from "@/types";

type AuthContextValue = {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("token");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(username: string, password: string) {
    const token = await api.login(username, password);
    localStorage.setItem("token", token.access_token);
    const me = await api.me();
    setUser(me);
  }

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login,
      logout,
      hasRole: (...roles: Role[]) => Boolean(user?.roles.some((r) => roles.includes(r))),
    }),
    [user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used under AuthProvider");
  return ctx;
}
