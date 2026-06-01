# Phase 5D — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Gerar proposta" to the simulation detail page with 2s render-status polling (60s max), download/approve buttons, and a `/propostas` list page.

**Architecture:** New `frontend/src/lib/proposals.ts` API client. `SimulacaoEdit.tsx` extended with proposal section below the schedule. `PropostasPage.tsx` is a new route with paginated list + status filter.

**Tech Stack:** React 18, TypeScript, TanStack Query, Shadcn UI, Tailwind CSS

**Prerequisite:** Phase 5B backend deployed locally (or mocked). Phase 5C tests green.

---

## Task 13: Proposals API client

**Files:**
- Create: `frontend/src/lib/proposals.ts`

- [ ] **Step 13.1 — Create proposals API client**

Create `frontend/src/lib/proposals.ts`:
```typescript
import { api } from "./api";

export interface ProposalOut {
  id: string;
  tenant_id: string;
  simulation_id: string;
  codigo: string;
  gerado_por: string;
  gerado_em: string;
  validade_dias: number;
  render_status: "pending" | "rendering" | "ready" | "failed";
  render_error: string | null;
  status: "rascunho" | "ready" | "aprovada" | "cancelada";
  pdf_key: string | null;
  carne_key: string | null;
  aprovado_por: string | null;
  aprovado_em: string | null;
  cancelado_por: string | null;
  cancelado_em: string | null;
}

export interface ProposalListItem {
  id: string;
  codigo: string;
  simulation_id: string;
  render_status: ProposalOut["render_status"];
  status: ProposalOut["status"];
  gerado_em: string;
}

export interface ProposalListPage {
  items: ProposalListItem[];
  next_cursor: string | null;
}

export async function createProposal(simulationId: string): Promise<ProposalOut> {
  const r = await api("/api/v1/proposals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ simulation_id: simulationId }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.message ?? `HTTP ${r.status}`);
  }
  return r.json();
}

export async function getProposal(id: string): Promise<ProposalOut> {
  const r = await api(`/api/v1/proposals/${id}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function listProposals(params?: {
  status?: string;
  cursor?: string;
  limit?: number;
}): Promise<ProposalListPage> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.cursor) q.set("cursor", params.cursor);
  if (params?.limit) q.set("limit", String(params.limit));
  const r = await api(`/api/v1/proposals?${q}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function approveProposal(id: string): Promise<ProposalOut> {
  const r = await api(`/api/v1/proposals/${id}/approve`, { method: "POST" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.message ?? `HTTP ${r.status}`);
  }
  return r.json();
}

export async function cancelProposal(id: string): Promise<ProposalOut> {
  const r = await api(`/api/v1/proposals/${id}/cancel`, { method: "POST" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.message ?? `HTTP ${r.status}`);
  }
  return r.json();
}

export async function generateCarne(id: string): Promise<ProposalOut> {
  const r = await api(`/api/v1/proposals/${id}/render-carne`, { method: "POST" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function downloadUrl(id: string, kind: "proposta" | "carne"): string {
  return `/api/v1/proposals/${id}/download?kind=${kind}`;
}
```

- [ ] **Step 13.2 — Verify TypeScript compiles**

```bash
cd /home/fj/git/financialsim-saas/frontend
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 13.3 — Commit**

```bash
git add frontend/src/lib/proposals.ts
git commit -m "feat(phase5): proposals API client (create/get/list/approve/cancel/carne/download)"
```

---

## Task 14: SimulacaoEdit — proposal section

**Files:**
- Modify: `frontend/src/routes/SimulacaoEdit.tsx`

The proposal section renders below the amortization table. It has four states:

1. **No proposal yet** → "Gerar proposta" button
2. **Polling** (`pending`/`rendering`) → spinner pill + cancel-polling after 60s
3. **Ready** → "Baixar proposta (PDF)" + "Aprovar proposta" buttons
4. **Aprovada** → "Gerar carnê" + "Cancelar proposta" buttons
5. **Failed** → error message + (admin only) "Re-renderizar"

- [ ] **Step 14.1 — Read current SimulacaoEdit.tsx**

Read `frontend/src/routes/SimulacaoEdit.tsx` to understand the current structure before modifying.

- [ ] **Step 14.2 — Add proposal section to SimulacaoEdit.tsx**

After the existing imports, add:
```typescript
import { useEffect, useRef, useState, useCallback } from "react";
import {
  ProposalOut,
  approveProposal,
  cancelProposal,
  createProposal,
  downloadUrl,
  generateCarne,
  getProposal,
} from "@/lib/proposals";
```

Add the `ProposalSection` component in the same file (before the default export):
```typescript
function ProposalSection({ simulationId }: { simulationId: string }) {
  const [proposal, setProposal] = useState<ProposalOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      pollCountRef.current = 0;
      pollRef.current = setInterval(async () => {
        pollCountRef.current += 1;
        if (pollCountRef.current >= 30) {
          // 30 × 2s = 60s max
          stopPolling();
          setError("Render timeout — tente re-renderizar como admin.");
          return;
        }
        try {
          const p = await getProposal(id);
          setProposal(p);
          if (p.render_status === "ready" || p.render_status === "failed") {
            stopPolling();
          }
        } catch {
          stopPolling();
        }
      }, 2000);
    },
    [stopPolling]
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleGerar = async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await createProposal(simulationId);
      setProposal(p);
      if (p.render_status === "pending" || p.render_status === "rendering") {
        startPolling(p.id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao gerar proposta");
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!proposal) return;
    setLoading(true);
    setError(null);
    try {
      const p = await approveProposal(proposal.id);
      setProposal(p);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao aprovar");
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!proposal) return;
    setLoading(true);
    setError(null);
    try {
      const p = await cancelProposal(proposal.id);
      setProposal(p);
      setShowCancelDialog(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao cancelar");
    } finally {
      setLoading(false);
    }
  };

  const handleCarne = async () => {
    if (!proposal) return;
    setLoading(true);
    try {
      await generateCarne(proposal.id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao gerar carnê");
    } finally {
      setLoading(false);
    }
  };

  const renderStatusPill = (status: ProposalOut["render_status"]) => {
    const map = {
      pending: "bg-yellow-100 text-yellow-800",
      rendering: "bg-blue-100 text-blue-800",
      ready: "bg-green-100 text-green-800",
      failed: "bg-red-100 text-red-800",
    } as const;
    const label = {
      pending: "Aguardando…",
      rendering: "Renderizando…",
      ready: "Pronto",
      failed: "Falhou",
    } as const;
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${map[status]}`}>
        {(status === "pending" || status === "rendering") && (
          <span className="h-2 w-2 animate-spin rounded-full border-2 border-current border-t-transparent" />
        )}
        {label[status]}
      </span>
    );
  };

  return (
    <div className="mt-6 rounded-lg border p-4">
      <h3 className="mb-3 text-base font-semibold">Proposta</h3>

      {!proposal && (
        <button
          onClick={handleGerar}
          disabled={loading}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Gerando…" : "Gerar proposta"}
        </button>
      )}

      {proposal && (
        <div className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-medium">{proposal.codigo}</span>
            {renderStatusPill(proposal.render_status)}
            <span className="text-muted-foreground">
              Status: <strong>{proposal.status}</strong>
            </span>
          </div>

          {proposal.render_status === "failed" && proposal.render_error && (
            <p className="text-sm text-destructive">{proposal.render_error}</p>
          )}

          <div className="flex flex-wrap gap-2">
            {proposal.render_status === "ready" && (
              <>
                <a
                  href={downloadUrl(proposal.id, "proposta")}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
                >
                  Baixar proposta (PDF)
                </a>
                {proposal.status === "ready" && (
                  <button
                    onClick={handleApprove}
                    disabled={loading}
                    className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Aprovar proposta
                  </button>
                )}
              </>
            )}

            {proposal.status === "aprovada" && (
              <>
                <button
                  onClick={handleCarne}
                  disabled={loading}
                  className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
                >
                  Gerar carnê
                </button>
                {proposal.carne_key && (
                  <a
                    href={downloadUrl(proposal.id, "carne")}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
                  >
                    Baixar carnê (PDF)
                  </a>
                )}
                <button
                  onClick={() => setShowCancelDialog(true)}
                  disabled={loading}
                  className="rounded border border-destructive px-3 py-1.5 text-sm font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
                >
                  Cancelar proposta
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

      {showCancelDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="rounded-lg bg-background p-6 shadow-lg max-w-sm w-full">
            <h4 className="font-semibold mb-2">Cancelar proposta</h4>
            <p className="text-sm text-muted-foreground mb-4">
              Esta ação cancelará todas as parcelas e desativará o acesso do cliente. Não pode ser desfeita.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowCancelDialog(false)}
                className="rounded border px-3 py-1.5 text-sm"
              >
                Voltar
              </button>
              <button
                onClick={handleCancel}
                disabled={loading}
                className="rounded bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground disabled:opacity-50"
              >
                Confirmar cancelamento
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

Then add `<ProposalSection simulationId={sim.id} />` at the bottom of the JSX in `SimulacaoEdit`, below the schedule table. The `sim.id` should already be available from the loaded simulation data.

- [ ] **Step 14.3 — TypeScript check**

```bash
cd /home/fj/git/financialsim-saas/frontend
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 14.4 — Commit**

```bash
git add frontend/src/routes/SimulacaoEdit.tsx
git commit -m "feat(phase5): add ProposalSection to SimulacaoEdit (generate/poll/download/approve/cancel/carne)"
```

---

## Task 15: PropostasPage list

**Files:**
- Create: `frontend/src/routes/propostas/PropostasPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 15.1 — Create PropostasPage**

Create `frontend/src/routes/propostas/PropostasPage.tsx`:
```typescript
import { useEffect, useState } from "react";
import {
  ProposalListItem,
  ProposalListPage,
  listProposals,
} from "@/lib/proposals";

const STATUS_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "rascunho", label: "Rascunho" },
  { value: "ready", label: "Pronto" },
  { value: "aprovada", label: "Aprovada" },
  { value: "cancelada", label: "Cancelada" },
];

const STATUS_BADGE: Record<string, string> = {
  rascunho: "bg-gray-100 text-gray-700",
  ready: "bg-green-100 text-green-700",
  aprovada: "bg-blue-100 text-blue-700",
  cancelada: "bg-red-100 text-red-700",
};

export default function PropostasPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState<ProposalListPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | undefined>(undefined);

  const load = async (resetCursor = true) => {
    setLoading(true);
    setError(null);
    try {
      const cur = resetCursor ? undefined : cursor;
      const result = await listProposals({
        status: statusFilter || undefined,
        cursor: cur,
        limit: 20,
      });
      setPage(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao carregar propostas");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const handleNext = async () => {
    if (!page?.next_cursor) return;
    setCursor(page.next_cursor);
    setLoading(true);
    try {
      const result = await listProposals({
        status: statusFilter || undefined,
        cursor: page.next_cursor,
        limit: 20,
      });
      setPage(result);
    } finally {
      setLoading(false);
    }
  };

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold mb-4">Propostas</h1>

      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm font-medium">Status:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border px-2 py-1 text-sm"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => load(true)}
          disabled={loading}
          className="rounded border px-3 py-1 text-sm hover:bg-muted disabled:opacity-50"
        >
          Atualizar
        </button>
      </div>

      {error && <p className="text-sm text-destructive mb-3">{error}</p>}

      {loading && <p className="text-sm text-muted-foreground">Carregando…</p>}

      {!loading && page && (
        <>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Código</th>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 pr-4 font-medium">Render</th>
                <th className="py-2 font-medium">Gerada em</th>
              </tr>
            </thead>
            <tbody>
              {page.items.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-4 text-muted-foreground">
                    Nenhuma proposta encontrada.
                  </td>
                </tr>
              )}
              {page.items.map((p: ProposalListItem) => (
                <tr key={p.id} className="border-b hover:bg-muted/30">
                  <td className="py-2 pr-4 font-mono">{p.codigo}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        STATUS_BADGE[p.status] ?? "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {p.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-muted-foreground">
                    {p.render_status}
                  </td>
                  <td className="py-2 text-muted-foreground">
                    {fmtDate(p.gerado_em)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {page.next_cursor && (
            <div className="mt-4">
              <button
                onClick={handleNext}
                disabled={loading}
                className="rounded border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                Próxima página →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 15.2 — Add route to App.tsx**

Read `frontend/src/App.tsx` to see the existing routing structure.

Then add:
```typescript
import PropostasPage from "./routes/propostas/PropostasPage";
// ... inside the router:
{ path: "/propostas", element: <PropostasPage /> }
```

Also add a nav link if a sidebar/nav exists (follow existing pattern for the simulations link).

- [ ] **Step 15.3 — TypeScript check**

```bash
cd /home/fj/git/financialsim-saas/frontend
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 15.4 — Run frontend tests**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm test -- --run
```
Expected: all tests PASS (no regressions).

- [ ] **Step 15.5 — Commit**

```bash
git add frontend/src/routes/propostas/ \
        frontend/src/App.tsx
git commit -m "feat(phase5): PropostasPage list (paginated, status filter)"
```

---

## Phase 5D complete — Phase 5 fully implemented

All Phase 5 acceptance checklist items are covered:

| Acceptance item | Covered by |
|---|---|
| POST /proposals → 202 | Task 8 + test_proposal_endpoints |
| Second POST → 409 | test_proposal_endpoints |
| Polling pending→ready | SimulacaoEdit ProposalSection |
| Download signed URL serves PDF | Task 5 + test_storage_local |
| Approve → aprovada + parcela_payments | test_proposal_service |
| Vendedor ownership rule | ProposalService._can_act_on |
| Cancel cascade parcela_payments | test_proposal_service |
| Carnê only when aprovada | test_proposal_service |
| Two renders byte-identical | reproducibility from snapshot |
| Storage contract Local + S3 | test_storage_contract |
| Tenant A can't read tenant B | test_proposal_endpoints |
| Failed render surfaces error | test_render_tasks |

---

## Next

After all Phase 5 plans pass and tests are green, run the finishing-a-development-branch skill to merge to master.
