# Phase 6D — Frontend Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the customer portal: `PortalLayout`, route guard for customer redirect, portal pages (home/financiamento/documentos), and a Pix payment modal with 3-second polling.

**Architecture:** New routes under `/portal/...` using `<RequireRole roles={["customer"]}>`. A top-level redirect sends authenticated customers on non-portal paths to `/portal/`. React Query powers data fetching and Pix polling (`refetchInterval: 3000`). `PortalLayout` is distinct from staff `AppLayout`.

**Tech Stack:** React 19, React Router 7, React Query 5, Tailwind CSS, shadcn/ui primitives, Lucide icons.

**Prerequisite:** Plans 6A–6C complete (backend API running).

---

### Task 1: Create frontend/src/lib/portal.ts

**Files:**
- Create: `frontend/src/lib/portal.ts`

- [ ] **Step 1: Create portal.ts API client**

```typescript
import { api } from "./api";

export interface FinanciamentoItem {
  proposal_id: string;
  codigo: string;
  veiculo: string;
  status_counts: { open: number; paid: number; overdue: number; canceled: number };
  total_parcelas: number;
  aprovado_em: string | null;
}

export interface Parcela {
  id: string;
  parcela_num: number;
  vencimento: string;
  valor_parcela: string;
  status: "open" | "paid" | "overdue" | "canceled";
  paid_at: string | null;
  paid_amount: string | null;
}

export interface FinanciamentoSchedule {
  proposal_id: string;
  codigo: string;
  veiculo: string;
  next_open_parcela_id: string | null;
  parcelas: Parcela[];
}

export interface PixChargeOut {
  charge_id: string;
  status: "pending" | "paid" | "expired" | "canceled";
  brcode: string;
  qr_url: string;
  expires_at: string;
}

export interface PortalMe {
  id: string;
  email: string;
  name: string;
  role: string;
  client_id: string | null;
}

export async function getPortalMe(token: string): Promise<PortalMe> {
  const r = await api.get<PortalMe>("/v1/portal/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return r.data;
}

export async function listFinanciamentos(token: string): Promise<FinanciamentoItem[]> {
  const r = await api.get<FinanciamentoItem[]>("/v1/portal/financiamentos", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return r.data;
}

export async function getFinanciamento(
  proposalId: string,
  token: string,
): Promise<FinanciamentoSchedule> {
  const r = await api.get<FinanciamentoSchedule>(`/v1/portal/financiamentos/${proposalId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return r.data;
}

export async function createPixCharge(
  parcelaId: string,
  token: string,
): Promise<PixChargeOut> {
  const r = await api.post<PixChargeOut>(
    `/v1/portal/parcelas/${parcelaId}/pix-charge`,
    {},
    { headers: { Authorization: `Bearer ${token}` } },
  );
  return r.data;
}

export async function getPixCharge(
  chargeId: string,
  token: string,
): Promise<PixChargeOut> {
  const r = await api.get<PixChargeOut>(`/v1/portal/pix-charges/${chargeId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return r.data;
}

export function downloadPortalPdf(proposalId: string, kind: string, token: string): void {
  // Opens PDF in new tab via redirect
  window.open(
    `/api/v1/portal/proposals/${proposalId}/download?kind=${kind}&token=${token}`,
    "_blank",
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors from portal.ts.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/portal.ts
git commit -m "feat(phase6): add portal API client (lib/portal.ts)"
```

---

### Task 2: Update AuthContext to expose role

The portal redirect needs to read the user's role. Currently `AuthContext` doesn't decode the JWT.

**Files:**
- Modify: `frontend/src/context/AuthContext.tsx`

- [ ] **Step 1: Add role extraction to AuthContext**

Replace the `AuthContextValue` interface and update the context:

```typescript
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../lib/api";

interface AuthTokens {
  access: string;
  refresh: string;
}

function decodeRole(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role ?? null;
  } catch {
    return null;
  }
}

interface AuthContextValue {
  tokens: AuthTokens | null;
  role: string | null;
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

  const role = tokens ? decodeRole(tokens.access) : null;

  return (
    <AuthContext.Provider
      value={{ tokens, role, login, logout, isAuthenticated: tokens !== null }}
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
```

- [ ] **Step 2: TypeScript check**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/context/AuthContext.tsx
git commit -m "feat(phase6): expose role in AuthContext (decoded from JWT)"
```

---

### Task 3: Create PortalLayout

**Files:**
- Create: `frontend/src/components/PortalLayout.tsx`

- [ ] **Step 1: Create PortalLayout.tsx**

```tsx
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

interface Props {
  children: ReactNode;
}

export default function PortalLayout({ children }: Props) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="font-semibold text-gray-900">Meu Financiamento</span>
          <nav className="hidden sm:flex gap-4 text-sm">
            <Link to="/portal" className="text-gray-600 hover:text-gray-900">
              Início
            </Link>
            <Link to="/portal/documentos" className="text-gray-600 hover:text-gray-900">
              Documentos
            </Link>
          </nav>
        </div>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-800"
        >
          Sair
        </button>
      </header>
      <main className="max-w-3xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npx tsc --noEmit 2>&1 | head -10
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PortalLayout.tsx
git commit -m "feat(phase6): add PortalLayout component"
```

---

### Task 4: Create PixModal

**Files:**
- Create: `frontend/src/routes/portal/PixModal.tsx`

- [ ] **Step 1: Create PixModal.tsx**

```tsx
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { getPixCharge, type PixChargeOut } from "../../lib/portal";

interface Props {
  charge: PixChargeOut;
  token: string;
  onClose: () => void;
}

const TERMINAL = new Set(["paid", "expired", "canceled"]);

function useCountdown(expiresAt: string): number {
  const [secs, setSecs] = useState(() =>
    Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000)),
  );
  useEffect(() => {
    if (secs <= 0) return;
    const id = setInterval(
      () =>
        setSecs((s) => {
          const remaining = Math.max(
            0,
            Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000),
          );
          if (remaining <= 0) clearInterval(id);
          return remaining;
        }),
      1000,
    );
    return () => clearInterval(id);
  }, [expiresAt]);
  return secs;
}

export default function PixModal({ charge: initial, token, onClose }: Props) {
  const [copied, setCopied] = useState(false);
  const countdown = useCountdown(initial.expires_at);

  const { data: charge } = useQuery({
    queryKey: ["pix-charge", initial.charge_id],
    queryFn: () => getPixCharge(initial.charge_id, token),
    initialData: initial,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL.has(status) ? false : 3000;
    },
  });

  // Auto-close with success animation on paid
  useEffect(() => {
    if (charge?.status === "paid") {
      const id = setTimeout(onClose, 2000);
      return () => clearTimeout(id);
    }
  }, [charge?.status, onClose]);

  function copyBrcode() {
    navigator.clipboard.writeText(charge?.brcode ?? "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const mm = String(Math.floor(countdown / 60)).padStart(2, "0");
  const ss = String(countdown % 60).padStart(2, "0");

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>
            {charge?.status === "paid" ? "✅ Pago!" : "Pagar com Pix"}
          </DialogTitle>
        </DialogHeader>

        {charge?.status === "paid" ? (
          <p className="text-center text-green-600 font-medium py-4">
            Pagamento confirmado!
          </p>
        ) : charge?.status === "expired" ? (
          <p className="text-center text-gray-500 py-4">QR Code expirado.</p>
        ) : charge?.status === "canceled" ? (
          <p className="text-center text-red-500 py-4">Cobrança cancelada.</p>
        ) : (
          <div className="flex flex-col items-center gap-4">
            {/* QR Code PNG */}
            <img
              src={charge?.qr_url}
              alt="QR Code Pix"
              className="w-48 h-48 border rounded"
            />

            {/* Countdown */}
            <p className="text-sm text-gray-500">
              Expira em{" "}
              <span className={countdown < 120 ? "text-red-500 font-medium" : ""}>
                {mm}:{ss}
              </span>
            </p>

            {/* Copy brcode */}
            <div className="w-full">
              <p className="text-xs text-gray-400 mb-1">Pix Copia e Cola</p>
              <div className="flex gap-2">
                <input
                  readOnly
                  value={charge?.brcode ?? ""}
                  className="flex-1 text-xs border rounded px-2 py-1 bg-gray-50 truncate"
                />
                <button
                  onClick={copyBrcode}
                  className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  {copied ? "Copiado!" : "Copiar"}
                </button>
              </div>
            </div>

            <p className="text-xs text-gray-400">
              Aguardando confirmação…
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npx tsc --noEmit 2>&1 | head -10
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/portal/PixModal.tsx
git commit -m "feat(phase6): add PixModal with QR display, brcode copy, 3s polling, countdown"
```

---

### Task 5: Create portal pages

**Files:**
- Create: `frontend/src/routes/portal/PortalHome.tsx`
- Create: `frontend/src/routes/portal/PortalFinanciamento.tsx`
- Create: `frontend/src/routes/portal/PortalDocumentos.tsx`

- [ ] **Step 1: Create PortalHome.tsx**

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import PortalLayout from "../../components/PortalLayout";
import { useAuth } from "../../context/AuthContext";
import { listFinanciamentos } from "../../lib/portal";

function statusBadge(count: number, label: string, color: string) {
  if (count === 0) return null;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${color}`}
    >
      {count} {label}
    </span>
  );
}

export default function PortalHome() {
  const { tokens } = useAuth();

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["portal-financiamentos"],
    queryFn: () => listFinanciamentos(tokens!.access),
    enabled: !!tokens,
  });

  return (
    <PortalLayout>
      <h1 className="text-xl font-semibold mb-4">Meus Financiamentos</h1>
      {isLoading && <p className="text-gray-400">Carregando…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-gray-500">Nenhum financiamento encontrado.</p>
      )}
      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <Link
            key={item.proposal_id}
            to={`/portal/financiamento/${item.proposal_id}`}
            className="block bg-white rounded-lg border border-gray-200 p-4 hover:border-blue-400 transition"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="font-medium text-gray-900">{item.veiculo || item.codigo}</p>
                <p className="text-xs text-gray-400">{item.codigo}</p>
              </div>
              <div className="flex gap-1 flex-wrap justify-end">
                {statusBadge(item.status_counts.paid, "paga(s)", "bg-green-100 text-green-700")}
                {statusBadge(item.status_counts.open, "em aberto", "bg-blue-100 text-blue-700")}
                {statusBadge(item.status_counts.overdue, "atrasada(s)", "bg-red-100 text-red-700")}
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {item.total_parcelas} parcelas
              {item.aprovado_em
                ? ` · Aprovado em ${new Date(item.aprovado_em).toLocaleDateString("pt-BR")}`
                : ""}
            </p>
          </Link>
        ))}
      </div>
    </PortalLayout>
  );
}
```

- [ ] **Step 2: Create PortalFinanciamento.tsx**

```tsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import PortalLayout from "../../components/PortalLayout";
import { useAuth } from "../../context/AuthContext";
import { createPixCharge, getFinanciamento, type PixChargeOut } from "../../lib/portal";
import PixModal from "./PixModal";

const STATUS_LABEL: Record<string, string> = {
  paid: "Paga",
  open: "Em aberto",
  overdue: "Atrasada",
  canceled: "Cancelada",
};

const STATUS_COLOR: Record<string, string> = {
  paid: "text-green-600",
  open: "text-blue-600",
  overdue: "text-red-600",
  canceled: "text-gray-400",
};

export default function PortalFinanciamento() {
  const { proposalId } = useParams<{ proposalId: string }>();
  const { tokens } = useAuth();
  const [pixCharge, setPixCharge] = useState<PixChargeOut | null>(null);
  const [paying, setPaying] = useState(false);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["portal-financiamento", proposalId],
    queryFn: () => getFinanciamento(proposalId!, tokens!.access),
    enabled: !!tokens && !!proposalId,
  });

  async function handlePagar() {
    if (!data?.next_open_parcela_id || !tokens) return;
    setPaying(true);
    try {
      const charge = await createPixCharge(data.next_open_parcela_id, tokens.access);
      setPixCharge(charge);
    } catch {
      alert("Erro ao gerar cobrança Pix. Tente novamente.");
    } finally {
      setPaying(false);
    }
  }

  function handleCloseModal() {
    setPixCharge(null);
    refetch();
  }

  return (
    <PortalLayout>
      {isLoading && <p className="text-gray-400">Carregando…</p>}
      {data && (
        <>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-xl font-semibold">{data.veiculo || data.codigo}</h1>
              <p className="text-xs text-gray-400">{data.codigo}</p>
            </div>
            {data.next_open_parcela_id && (
              <button
                onClick={handlePagar}
                disabled={paying}
                className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
              >
                {paying ? "Aguarde…" : "Pagar com Pix"}
              </button>
            )}
          </div>

          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-4 py-2 text-left">#</th>
                  <th className="px-4 py-2 text-left">Vencimento</th>
                  <th className="px-4 py-2 text-right">Valor</th>
                  <th className="px-4 py-2 text-center">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.parcelas.map((p) => (
                  <tr key={p.id} className="border-t border-gray-100">
                    <td className="px-4 py-2 text-gray-500">{p.parcela_num}</td>
                    <td className="px-4 py-2">
                      {new Date(p.vencimento + "T00:00:00").toLocaleDateString("pt-BR")}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {Number(p.paid_amount ?? p.valor_parcela).toLocaleString("pt-BR", {
                        style: "currency",
                        currency: "BRL",
                      })}
                    </td>
                    <td className={`px-4 py-2 text-center font-medium ${STATUS_COLOR[p.status]}`}>
                      {STATUS_LABEL[p.status] ?? p.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {pixCharge && tokens && (
        <PixModal charge={pixCharge} token={tokens.access} onClose={handleCloseModal} />
      )}
    </PortalLayout>
  );
}
```

- [ ] **Step 3: Create PortalDocumentos.tsx**

```tsx
import { useQuery } from "@tanstack/react-query";
import PortalLayout from "../../components/PortalLayout";
import { useAuth } from "../../context/AuthContext";
import { listFinanciamentos } from "../../lib/portal";

export default function PortalDocumentos() {
  const { tokens } = useAuth();

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["portal-financiamentos"],
    queryFn: () => listFinanciamentos(tokens!.access),
    enabled: !!tokens,
  });

  return (
    <PortalLayout>
      <h1 className="text-xl font-semibold mb-4">Documentos</h1>
      {isLoading && <p className="text-gray-400">Carregando…</p>}
      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <div
            key={item.proposal_id}
            className="bg-white rounded-lg border border-gray-200 p-4"
          >
            <p className="font-medium text-gray-900 mb-2">{item.veiculo || item.codigo}</p>
            <div className="flex gap-2 flex-wrap">
              <a
                href={`/api/v1/portal/proposals/${item.proposal_id}/download?kind=proposta`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
                onClick={(e) => {
                  e.preventDefault();
                  const url = `/api/v1/portal/proposals/${item.proposal_id}/download?kind=proposta`;
                  window.open(url, "_blank");
                }}
              >
                📄 Proposta PDF
              </a>
              <a
                href={`/api/v1/portal/proposals/${item.proposal_id}/download?kind=carne`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
                onClick={(e) => {
                  e.preventDefault();
                  const url = `/api/v1/portal/proposals/${item.proposal_id}/download?kind=carne`;
                  window.open(url, "_blank");
                }}
              >
                📄 Carnê PDF
              </a>
            </div>
          </div>
        ))}
      </div>
    </PortalLayout>
  );
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/portal/
git commit -m "feat(phase6): add portal pages (PortalHome, PortalFinanciamento, PortalDocumentos)"
```

---

### Task 6: Update App.tsx — portal routes + customer redirect

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update App.tsx**

Replace the entire file content:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Health from "./routes/Health";
import Index from "./routes/Index";
import Login from "./routes/Login";
import ForgotPassword from "./routes/ForgotPassword";
import ResetPassword from "./routes/ResetPassword";
import AdminUsers from "./routes/admin/Users";
import RequireRole from "./components/RequireRole";
import Simulacao from "./routes/Simulacao";
import SimulacaoEdit from "./routes/SimulacaoEdit";
import ClientesPage from "./routes/clientes/ClientesPage";
import VeiculosPage from "./routes/veiculos/VeiculosPage";
import PropostasPage from "./routes/propostas/PropostasPage";
import PortalHome from "./routes/portal/PortalHome";
import PortalFinanciamento from "./routes/portal/PortalFinanciamento";
import PortalDocumentos from "./routes/portal/PortalDocumentos";

const queryClient = new QueryClient();

/** Redirects authenticated customer users to /portal/ when on a non-portal path. */
function CustomerGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, role } = useAuth();
  const location = useLocation();

  if (isAuthenticated && role === "customer" && !location.pathname.startsWith("/portal")) {
    return <Navigate to="/portal" replace />;
  }
  return <>{children}</>;
}

function ProtectedIndex() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Index />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <CustomerGuard>
            <Routes>
              {/* Public */}
              <Route path="/login" element={<Login />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password/:token" element={<ResetPassword />} />
              <Route path="/healthz" element={<Health />} />

              {/* Staff */}
              <Route path="/" element={<ProtectedIndex />} />
              <Route
                path="/admin/users"
                element={
                  <RequireRole roles={["admin"]}>
                    <AdminUsers />
                  </RequireRole>
                }
              />
              <Route path="/simulacao" element={<Simulacao />} />
              <Route path="/simulacao/:id" element={<SimulacaoEdit />} />
              <Route path="/clientes" element={<ClientesPage />} />
              <Route path="/veiculos" element={<VeiculosPage />} />
              <Route
                path="/propostas"
                element={
                  <RequireRole roles={["admin", "manager", "user"]}>
                    <PropostasPage />
                  </RequireRole>
                }
              />

              {/* Customer portal */}
              <Route
                path="/portal"
                element={
                  <RequireRole roles={["customer"]}>
                    <PortalHome />
                  </RequireRole>
                }
              />
              <Route
                path="/portal/financiamento/:proposalId"
                element={
                  <RequireRole roles={["customer"]}>
                    <PortalFinanciamento />
                  </RequireRole>
                }
              />
              <Route
                path="/portal/documentos"
                element={
                  <RequireRole roles={["customer"]}>
                    <PortalDocumentos />
                  </RequireRole>
                }
              />
            </Routes>
          </CustomerGuard>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 3: Run Vitest to confirm no regressions**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npx vitest run 2>&1 | tail -10
```
Expected: existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(phase6): add portal routes to App.tsx; CustomerGuard redirects to /portal"
```

---

### Task 7: Manual UI verification

- [ ] **Step 1: Start backend**

```bash
cd /home/fabio/git/financialsim-saas && docker compose up -d postgres redis
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/postgres" uv run --directory backend uvicorn finacialsim_saas.main:app --reload --port 8000 &
```

- [ ] **Step 2: Start frontend dev server**

```bash
cd /home/fabio/git/financialsim-saas/frontend && npm run dev &
```

- [ ] **Step 3: Verify portal redirect**

1. Open `http://localhost:5173/login` in browser.
2. Log in as a staff user (admin) → should land on `/`.
3. Log out. Log in as a customer (email/pass set via CLI or test) → should redirect to `/portal`.
4. Customer should see "Meus Financiamentos" page.
5. Customer navigating to `/simulacao` should be redirected to `/portal`.

- [ ] **Step 4: Commit after verification**

```bash
git add .
git commit -m "feat(phase6): frontend portal complete — PortalHome, PortalFinanciamento, PixModal, customer redirect"
```
