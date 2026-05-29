import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../context/AuthContext";

interface Props {
  roles: string[];
  children: ReactNode;
}

export default function RequireRole({ roles, children }: Props) {
  const { tokens, isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  try {
    const payload = JSON.parse(atob(tokens!.access.split(".")[1]));
    if (!roles.includes(payload.role)) return <Navigate to="/" replace />;
  } catch {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
