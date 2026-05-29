import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../lib/api";

interface AuthTokens {
  access: string;
  refresh: string;
}

interface AuthContextValue {
  tokens: AuthTokens | null;
  login: (tokens: AuthTokens) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("auth_tokens");
    if (stored) {
      const parsed: AuthTokens = JSON.parse(stored);
      // Re-hydrate access token via refresh on page reload
      api
        .post<AuthTokens>("/v1/auth/refresh", { refresh: parsed.refresh })
        .then((r) => {
          const fresh = r.data;
          localStorage.setItem("auth_tokens", JSON.stringify(fresh));
          setTokens(fresh);
        })
        .catch(() => {
          localStorage.removeItem("auth_tokens");
        })
        .finally(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  const login = (t: AuthTokens) => {
    localStorage.setItem("auth_tokens", JSON.stringify(t));
    setTokens(t);
  };

  const logout = () => {
    if (tokens) {
      api
        .post("/v1/auth/logout", null, {
          headers: { Authorization: `Bearer ${tokens.access}` },
        })
        .catch(() => {});
    }
    localStorage.removeItem("auth_tokens");
    setTokens(null);
  };

  if (!ready) return null;

  return (
    <AuthContext.Provider
      value={{ tokens, login, logout, isAuthenticated: tokens !== null }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
