# Phase 4 Frontend — Indicadores + Business Rules Editor + Audit Log

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/indicadores` (indicator cards + mini charts), `/configuracoes/regras` (admin business rules editor with diff confirmation), and `/logs` (paginated audit log with filters + CSV export). Depends on Phase 4 backend being deployed.

**Architecture:** Three new route pages + shared lib modules for API calls. React Query for data fetching with `refetchInterval` for rules invalidation. Recharts for mini charts (already used in `SimulacaoCharts.tsx`). No WebSocket — React Query polling only.

**Tech Stack:** React, TypeScript, React Query, Recharts, Tailwind, shadcn/ui components, Vite

---

## Prerequisites

Phase 4 backend running (indicators API, business-rules PUT, audit-log API). Dev server at `http://localhost:8000` proxied via Vite.

---

## File Map

**Create:**
- `frontend/src/lib/indicators.ts`
- `frontend/src/lib/audit-log.ts`
- `frontend/src/components/ui/table.tsx`
- `frontend/src/components/ui/toast.tsx`
- `frontend/src/components/ui/textarea.tsx`
- `frontend/src/routes/indicadores/IndicadoresPage.tsx`
- `frontend/src/routes/configuracoes/RegrasPage.tsx`
- `frontend/src/routes/logs/LogsPage.tsx`
- `frontend/src/tests/indicadores.test.tsx`
- `frontend/src/tests/regras.test.tsx`
- `frontend/src/tests/logs.test.tsx`

**Modify:**
- `frontend/src/App.tsx` — add 3 routes
- `frontend/src/hooks/useBusinessRules.ts` — add mutation + `refetchInterval`

---

## Task 1: API Library Modules

**Files:**
- Create: `frontend/src/lib/indicators.ts`
- Create: `frontend/src/lib/audit-log.ts`
- Modify: `frontend/src/hooks/useBusinessRules.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/tests/indicadores.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import * as api from "../lib/indicators";

vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(),
}));

const { apiFetch } = await import("../lib/api");

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe("indicators lib", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchIndicators returns array", async () => {
    (apiFetch as any).mockResolvedValue([
      { codigo: "SELIC", valor: "10.75", unidade: "pct_aa", fonte: "bacen_sgs", stale: false },
    ]);
    const result = await api.fetchIndicators();
    expect(result).toHaveLength(1);
    expect(result[0].codigo).toBe("SELIC");
  });

  it("fetchSeries returns series object", async () => {
    (apiFetch as any).mockResolvedValue({
      codigo: "SELIC",
      range: "12m",
      points: [{ data_referencia: "2026-06-01", valor: "10.75" }],
    });
    const result = await api.fetchSeries("SELIC", "12m");
    expect(result.points).toHaveLength(1);
  });
});
```

Create `frontend/src/tests/logs.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import * as api from "../lib/audit-log";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));

const { apiFetch } = await import("../lib/api");

describe("audit-log lib", () => {
  it("fetchAuditLog returns page", async () => {
    (apiFetch as any).mockResolvedValue({
      items: [{ id: "1", acao: "create", entidade: "client", timestamp: "2026-06-01T00:00:00Z" }],
      next_cursor: null,
    });
    const result = await api.fetchAuditLog({});
    expect(result.items).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run to verify failures**

```bash
cd frontend && npm run test -- --run src/tests/indicadores.test.tsx src/tests/logs.test.tsx
```
Expected: ImportError — modules not found.

- [ ] **Step 3: Create `lib/indicators.ts`**

```typescript
import { apiFetch } from "./api";

export interface IndicatorOut {
  codigo: string;
  valor: string;
  unidade: string;
  fonte: string;
  data_referencia: string;
  coletado_em: string;
  stale: boolean;
}

export interface SeriesPoint {
  data_referencia: string;
  valor: string;
}

export interface SeriesOut {
  codigo: string;
  range: string;
  points: SeriesPoint[];
}

export function fetchIndicators(): Promise<IndicatorOut[]> {
  return apiFetch("/api/v1/indicators");
}

export function fetchSeries(codigo: string, range = "12m"): Promise<SeriesOut> {
  return apiFetch(`/api/v1/indicators/${codigo}/series?range=${range}`);
}

export function triggerRefresh(): Promise<{ enqueued: boolean }> {
  return apiFetch("/api/v1/indicators/refresh", { method: "POST" });
}
```

- [ ] **Step 4: Create `lib/audit-log.ts`**

```typescript
import { apiFetch } from "./api";

export interface AuditLogItem {
  id: string;
  tenant_id: string;
  timestamp: string;
  usuario_id: string | null;
  acao: string;
  entidade: string | null;
  entidade_id: string | null;
  diff_json: Record<string, unknown> | null;
}

export interface AuditLogPage {
  items: AuditLogItem[];
  next_cursor: string | null;
}

export interface AuditLogFilters {
  acao?: string;
  entidade?: string;
  date_from?: string;
  date_to?: string;
  cursor?: string;
}

export function fetchAuditLog(filters: AuditLogFilters): Promise<AuditLogPage> {
  const params = new URLSearchParams();
  if (filters.acao) params.set("acao", filters.acao);
  if (filters.entidade) params.set("entidade", filters.entidade);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.cursor) params.set("cursor", filters.cursor);
  const qs = params.toString();
  return apiFetch(`/api/v1/audit-log${qs ? `?${qs}` : ""}`);
}

export function buildCsvUrl(filters: AuditLogFilters): string {
  const params = new URLSearchParams();
  params.set("format", "csv");
  if (filters.acao) params.set("acao", filters.acao);
  if (filters.entidade) params.set("entidade", filters.entidade);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  return `/api/v1/audit-log?${params.toString()}`;
}
```

- [ ] **Step 5: Update `hooks/useBusinessRules.ts` — add mutation + refetchInterval**

Read the current file first, then append/modify:

The current `useBusinessRules` hook uses `useQuery`. Add:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

// ... existing BusinessRules type and suggestRate ...

export function useBusinessRules() {
  return useQuery({
    queryKey: ["businessRules"],
    queryFn: () => apiFetch<BusinessRules>("/api/v1/business-rules"),
    staleTime: 0,
    refetchInterval: 30_000,
  });
}

export function useUpdateBusinessRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ chave, valor, motivo }: { chave: string; valor: unknown; motivo?: string }) =>
      apiFetch(`/api/v1/business-rules/${chave}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ valor, motivo }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["businessRules"] });
    },
  });
}
```

- [ ] **Step 6: Run tests**

```bash
cd frontend && npm run test -- --run src/tests/indicadores.test.tsx src/tests/logs.test.tsx
```
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/indicators.ts \
        frontend/src/lib/audit-log.ts \
        frontend/src/hooks/useBusinessRules.ts \
        frontend/src/tests/indicadores.test.tsx \
        frontend/src/tests/logs.test.tsx
git commit -m "feat(phase4-fe): indicators + audit-log API lib modules, useBusinessRules mutation"
```

---

## Task 2: shadcn UI Primitives

**Files:**
- Create: `frontend/src/components/ui/table.tsx`
- Create: `frontend/src/components/ui/toast.tsx`
- Create: `frontend/src/components/ui/textarea.tsx`

These follow the shadcn/ui pattern already used in this project (see `badge.tsx`, `button.tsx`).

- [ ] **Step 1: Create `components/ui/table.tsx`**

```tsx
import * as React from "react";
import { cn } from "../../lib/utils";

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative w-full overflow-auto">
      <table ref={ref} className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  )
);
Table.displayName = "Table";

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
  )
);
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
  )
);
TableBody.displayName = "TableBody";

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn("border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted", className)}
      {...props}
    />
  )
);
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn("h-10 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0", className)}
      {...props}
    />
  )
);
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={cn("p-4 align-middle [&:has([role=checkbox])]:pr-0", className)} {...props} />
  )
);
TableCell.displayName = "TableCell";

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow };
```

- [ ] **Step 2: Create `components/ui/textarea.tsx`**

```tsx
import * as React from "react";
import { cn } from "../../lib/utils";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[60px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";

export { Textarea };
```

- [ ] **Step 3: Create `components/ui/toast.tsx`**

Simple toast using a fixed-position div + React state. No library dependency.

```tsx
import * as React from "react";
import { cn } from "../../lib/utils";

interface ToastProps {
  message: string;
  type?: "info" | "success" | "error";
  onClose: () => void;
}

export function Toast({ message, type = "info", onClose }: ToastProps) {
  React.useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-lg px-4 py-3 text-sm shadow-lg",
        type === "success" && "bg-green-600 text-white",
        type === "error" && "bg-red-600 text-white",
        type === "info" && "bg-gray-800 text-white"
      )}
    >
      <span>{message}</span>
      <button onClick={onClose} className="ml-2 opacity-70 hover:opacity-100">✕</button>
    </div>
  );
}

export function useToast() {
  const [toast, setToast] = React.useState<{ message: string; type: "info" | "success" | "error" } | null>(null);

  const show = React.useCallback((message: string, type: "info" | "success" | "error" = "info") => {
    setToast({ message, type });
  }, []);

  const dismiss = React.useCallback(() => setToast(null), []);

  const ToastNode = toast ? <Toast message={toast.message} type={toast.type} onClose={dismiss} /> : null;

  return { show, ToastNode };
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/table.tsx \
        frontend/src/components/ui/toast.tsx \
        frontend/src/components/ui/textarea.tsx
git commit -m "feat(phase4-fe): add Table, Toast, Textarea UI primitives"
```

---

## Task 3: /indicadores Page

**Files:**
- Create: `frontend/src/routes/indicadores/IndicadoresPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `routes/indicadores/IndicadoresPage.tsx`**

```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { fetchIndicators, fetchSeries, triggerRefresh, type IndicatorOut } from "../../lib/indicators";
import { useAuth } from "../../context/AuthContext";

const UNIDADE_LABEL: Record<string, string> = {
  pct_aa: "% a.a.",
  pct_am: "% a.m.",
  pct_ad: "% a.d.",
};

const CODIGO_LABEL: Record<string, string> = {
  SELIC: "SELIC",
  CDI: "CDI",
  IPCA: "IPCA",
  TX_BACEN_VEIC: "Tx Veículos BACEN",
};

function IndicatorCard({ indicator }: { indicator: IndicatorOut }) {
  const { data: series } = useQuery({
    queryKey: ["indicator-series", indicator.codigo],
    queryFn: () => fetchSeries(indicator.codigo, "12m"),
  });

  const chartData = (series?.points ?? []).map((p) => ({
    date: p.data_referencia,
    valor: parseFloat(p.valor),
  }));

  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-muted-foreground">
          {CODIGO_LABEL[indicator.codigo] ?? indicator.codigo}
        </span>
        <div className="flex items-center gap-1.5">
          {indicator.stale && (
            <Badge variant="outline" className="text-yellow-600 border-yellow-400">
              Desatualizado
            </Badge>
          )}
          <Badge variant="outline" className="text-xs">
            {indicator.fonte}
          </Badge>
        </div>
      </div>

      <div className="text-3xl font-bold tabular-nums">
        {parseFloat(indicator.valor).toFixed(2)}
        <span className="text-sm font-normal text-muted-foreground ml-1">
          {UNIDADE_LABEL[indicator.unidade] ?? indicator.unidade}
        </span>
      </div>

      <p className="text-xs text-muted-foreground">
        Ref.: {indicator.data_referencia} · Coletado:{" "}
        {new Date(indicator.coletado_em).toLocaleString("pt-BR")}
      </p>

      {chartData.length > 0 && (
        <div className="h-20 mt-1">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <XAxis dataKey="date" hide />
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                formatter={(v: number) => [`${v.toFixed(4)}`, ""]}
                labelFormatter={(l) => `Data: ${l}`}
              />
              <Line
                type="monotone"
                dataKey="valor"
                stroke="#3b82f6"
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function IndicadoresPage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const { data: indicators, isLoading } = useQuery({
    queryKey: ["indicators"],
    queryFn: fetchIndicators,
    refetchInterval: 60_000,
  });

  const refresh = useMutation({
    mutationFn: triggerRefresh,
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["indicators"] }), 3000);
    },
  });

  if (isLoading) {
    return <div className="p-6 text-muted-foreground text-sm">Carregando indicadores…</div>;
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Indicadores Econômicos</h1>
        {user?.role === "admin" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            {refresh.isPending ? "Atualizando…" : "↻ Atualizar agora"}
          </Button>
        )}
      </div>

      {(!indicators || indicators.length === 0) ? (
        <div className="rounded-xl border p-8 text-center text-muted-foreground text-sm">
          Nenhum indicador disponível. Clique em "Atualizar agora" para buscar.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {indicators.map((ind) => (
            <IndicatorCard key={ind.codigo} indicator={ind} />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register route in `App.tsx`**

Read `frontend/src/App.tsx` first to see the current route structure, then add:

```tsx
import IndicadoresPage from "./routes/indicadores/IndicadoresPage";
```

Add route inside the authenticated section (same level as `/simulacao`):

```tsx
<Route path="/indicadores" element={<IndicadoresPage />} />
```

- [ ] **Step 3: Run dev server and verify the page loads**

```bash
cd frontend && npm run dev &
# Visit http://localhost:5173/indicadores — verify cards render (may be empty until backend has data)
```

If backend is running with seeded data, cards should appear. If not, an empty state message should show.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/indicadores/IndicadoresPage.tsx \
        frontend/src/App.tsx
git commit -m "feat(phase4-fe): /indicadores page with SELIC/CDI/IPCA/TX_BACEN_VEIC cards + mini charts"
```

---

## Task 4: /configuracoes/regras Page

**Files:**
- Create: `frontend/src/routes/configuracoes/RegrasPage.tsx`
- Modify: `frontend/src/App.tsx`

This page is admin-only. It shows all `BusinessRules` keys as an editable table. `taxa_por_prazo_curva` gets a dynamic row editor; all others get a single input.

- [ ] **Step 1: Create `routes/configuracoes/RegrasPage.tsx`**

```tsx
import { useState } from "react";
import { useBusinessRules, useUpdateBusinessRule } from "../../hooks/useBusinessRules";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Badge } from "../../components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../../components/ui/table";
import { useToast } from "../../components/ui/toast";
import type { BusinessRules } from "../../routes/simulacao/types";

type RateCurvePoint = { ate_meses: number; taxa_mensal: string };

// ── Scalar editor ─────────────────────────────────────────────────────────────

function ScalarEditor({
  chave,
  value,
  onSave,
}: {
  chave: string;
  value: unknown;
  onSave: (v: unknown, motivo?: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));
  const [motivo, setMotivo] = useState("");

  if (!editing) {
    return (
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm">{String(value)}</span>
        <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
          Editar
        </Button>
      </div>
    );
  }

  const handleSave = () => {
    // Attempt type coercion: numbers stay numbers, booleans stay booleans
    let parsed: unknown = draft;
    if (draft === "true") parsed = true;
    else if (draft === "false") parsed = false;
    else if (!isNaN(Number(draft)) && draft.trim() !== "") parsed = Number(draft);
    onSave(parsed, motivo || undefined);
    setEditing(false);
    setMotivo("");
  };

  return (
    <div className="flex flex-col gap-2">
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="font-mono w-48 text-sm"
        onKeyDown={(e) => e.key === "Enter" && handleSave()}
      />
      <Input
        placeholder="Motivo (opcional)"
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        className="w-48 text-sm"
      />
      <div className="flex gap-2">
        <Button size="sm" onClick={handleSave}>Salvar</Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancelar</Button>
      </div>
    </div>
  );
}

// ── Rate curve editor ─────────────────────────────────────────────────────────

function RateCurveEditor({
  value,
  onSave,
}: {
  value: RateCurvePoint[];
  onSave: (v: RateCurvePoint[], motivo?: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<RateCurvePoint[]>(value);
  const [motivo, setMotivo] = useState("");

  if (!editing) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">{value.length} ponto(s)</span>
        <Button size="sm" variant="ghost" onClick={() => { setRows([...value]); setEditing(true); }}>
          Editar
        </Button>
      </div>
    );
  }

  const updateRow = (i: number, field: keyof RateCurvePoint, val: string) => {
    setRows((prev) => prev.map((r, idx) =>
      idx === i ? { ...r, [field]: field === "ate_meses" ? parseInt(val) || 0 : val } : r
    ));
  };

  const addRow = () => setRows((prev) => [...prev, { ate_meses: 0, taxa_mensal: "0" }]);
  const removeRow = (i: number) => setRows((prev) => prev.filter((_, idx) => idx !== i));

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-16">até</span>
            <Input
              className="w-20 font-mono text-sm"
              value={String(row.ate_meses)}
              onChange={(e) => updateRow(i, "ate_meses", e.target.value)}
              placeholder="meses"
            />
            <span className="text-xs text-muted-foreground w-16">taxa</span>
            <Input
              className="w-24 font-mono text-sm"
              value={row.taxa_mensal}
              onChange={(e) => updateRow(i, "taxa_mensal", e.target.value)}
              placeholder="0.0120"
            />
            <Button size="sm" variant="ghost" onClick={() => removeRow(i)}>✕</Button>
          </div>
        ))}
      </div>
      <Button size="sm" variant="outline" onClick={addRow}>+ Adicionar ponto</Button>
      <div className="flex gap-2 items-center">
        <Input
          placeholder="Motivo (opcional)"
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          className="w-48 text-sm"
        />
        <Button size="sm" onClick={() => { onSave(rows, motivo || undefined); setEditing(false); }}>
          Salvar
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancelar</Button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RegrasPage() {
  const { data: rules, isLoading } = useBusinessRules();
  const update = useUpdateBusinessRule();
  const { show, ToastNode } = useToast();

  const handleSave = (chave: string, valor: unknown, motivo?: string) => {
    update.mutate(
      { chave, valor, motivo },
      {
        onSuccess: () => show(`Regra "${chave}" atualizada`, "success"),
        onError: () => show(`Erro ao salvar "${chave}"`, "error"),
      }
    );
  };

  if (isLoading) {
    return <div className="p-6 text-muted-foreground text-sm">Carregando regras…</div>;
  }

  if (!rules) return null;

  const entries = Object.entries(rules) as [keyof BusinessRules, unknown][];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4">
      {ToastNode}
      <h1 className="text-xl font-semibold">Regras de Negócio</h1>
      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Chave</TableHead>
              <TableHead>Valor</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map(([chave, value]) => (
              <TableRow key={chave}>
                <TableCell className="font-mono text-sm w-64">{chave}</TableCell>
                <TableCell>
                  {chave === "taxa_por_prazo_curva" ? (
                    <RateCurveEditor
                      value={value as RateCurvePoint[]}
                      onSave={(v, m) => handleSave(chave, v, m)}
                    />
                  ) : (
                    <ScalarEditor
                      chave={chave}
                      value={value}
                      onSave={(v, m) => handleSave(chave, v, m)}
                    />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register route in `App.tsx`**

```tsx
import RegrasPage from "./routes/configuracoes/RegrasPage";
```

```tsx
// Inside admin/manager section, wrapped in RequireRole:
<Route path="/configuracoes/regras" element={
  <RequireRole roles={["admin"]}>
    <RegrasPage />
  </RequireRole>
} />
```

Check `RequireRole.tsx` for the correct prop name (`roles` vs `role`).

- [ ] **Step 3: Verify in browser**

With dev server running, visit `http://localhost:5173/configuracoes/regras` as admin. Verify:
- Table renders all rule keys
- Scalar values open inline edit on click
- `taxa_por_prazo_curva` shows row editor
- Saving a value shows success toast
- Refreshing page shows updated value

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/configuracoes/RegrasPage.tsx \
        frontend/src/App.tsx
git commit -m "feat(phase4-fe): /configuracoes/regras admin page with inline edit + curve editor"
```

---

## Task 5: /logs Page

**Files:**
- Create: `frontend/src/routes/logs/LogsPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `routes/logs/LogsPage.tsx`**

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Badge } from "../../components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../../components/ui/table";
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "../../components/ui/collapsible";
import { fetchAuditLog, buildCsvUrl, type AuditLogFilters, type AuditLogItem } from "../../lib/audit-log";

function DiffViewer({ diff }: { diff: Record<string, unknown> | null }) {
  if (!diff) return <span className="text-muted-foreground text-xs">—</span>;
  return (
    <pre className="text-xs bg-muted rounded p-2 overflow-auto max-h-40 whitespace-pre-wrap">
      {JSON.stringify(diff, null, 2)}
    </pre>
  );
}

function LogRow({ item }: { item: AuditLogItem }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen} asChild>
      <>
        <TableRow className="cursor-pointer" onClick={() => setOpen((v) => !v)}>
          <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
            {new Date(item.timestamp).toLocaleString("pt-BR")}
          </TableCell>
          <TableCell>
            <Badge variant="outline" className="text-xs">{item.acao}</Badge>
          </TableCell>
          <TableCell className="text-sm">{item.entidade ?? "—"}</TableCell>
          <TableCell className="font-mono text-xs text-muted-foreground">
            {item.usuario_id ? item.usuario_id.slice(0, 8) + "…" : "—"}
          </TableCell>
          <TableCell className="text-xs">
            <CollapsibleTrigger asChild>
              <Button size="sm" variant="ghost" className="h-6 px-2">
                {open ? "▲" : "▼"}
              </Button>
            </CollapsibleTrigger>
          </TableCell>
        </TableRow>
        <CollapsibleContent asChild>
          <TableRow>
            <TableCell colSpan={5} className="bg-muted/30 p-3">
              <DiffViewer diff={item.diff_json} />
            </TableCell>
          </TableRow>
        </CollapsibleContent>
      </>
    </Collapsible>
  );
}

export default function LogsPage() {
  const [filters, setFilters] = useState<AuditLogFilters>({});
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [history, setHistory] = useState<(string | undefined)[]>([undefined]);
  const [page, setPage] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-log", filters, cursor],
    queryFn: () => fetchAuditLog({ ...filters, cursor }),
  });

  const applyFilters = (next: Partial<AuditLogFilters>) => {
    setFilters((prev) => ({ ...prev, ...next }));
    setCursor(undefined);
    setHistory([undefined]);
    setPage(0);
  };

  const nextPage = () => {
    if (!data?.next_cursor) return;
    setHistory((h) => [...h, data.next_cursor!]);
    setCursor(data.next_cursor);
    setPage((p) => p + 1);
  };

  const prevPage = () => {
    if (page === 0) return;
    const prev = history[page - 1];
    setHistory((h) => h.slice(0, -1));
    setCursor(prev);
    setPage((p) => p - 1);
  };

  const csvUrl = buildCsvUrl(filters);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Log de Auditoria</h1>
        <a
          href={csvUrl}
          download="audit-log.csv"
          className="text-sm text-blue-600 hover:underline"
        >
          Exportar CSV
        </a>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <Input
          placeholder="Ação (ex: create, update)"
          className="w-48 text-sm"
          onChange={(e) => applyFilters({ acao: e.target.value || undefined })}
        />
        <Input
          placeholder="Entidade (ex: client)"
          className="w-48 text-sm"
          onChange={(e) => applyFilters({ entidade: e.target.value || undefined })}
        />
        <Input
          type="date"
          className="w-40 text-sm"
          onChange={(e) => applyFilters({ date_from: e.target.value || undefined })}
        />
        <Input
          type="date"
          className="w-40 text-sm"
          onChange={(e) => applyFilters({ date_to: e.target.value || undefined })}
        />
      </div>

      {isLoading ? (
        <div className="text-muted-foreground text-sm">Carregando…</div>
      ) : (
        <>
          <div className="rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Ação</TableHead>
                  <TableHead>Entidade</TableHead>
                  <TableHead>Usuário</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground py-8 text-sm">
                      Nenhum registro encontrado.
                    </TableCell>
                  </TableRow>
                ) : (
                  data?.items.map((item) => <LogRow key={item.id} item={item} />)
                )}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex justify-between items-center text-sm text-muted-foreground">
            <span>Página {page + 1}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={prevPage} disabled={page === 0}>
                ← Anterior
              </Button>
              <Button size="sm" variant="outline" onClick={nextPage} disabled={!data?.next_cursor}>
                Próxima →
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register route in `App.tsx`**

```tsx
import LogsPage from "./routes/logs/LogsPage";
```

```tsx
// manager/admin only:
<Route path="/logs" element={
  <RequireRole roles={["admin", "manager"]}>
    <LogsPage />
  </RequireRole>
} />
```

- [ ] **Step 3: Verify in browser**

With dev server running, visit `http://localhost:5173/logs`. Verify:
- Table renders with correct columns
- Expanding a row shows `diff_json`
- Ação/Entidade filters reduce results
- Date range filters work
- CSV download link triggers file download
- Pagination works for > 20 results

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/logs/LogsPage.tsx \
        frontend/src/App.tsx
git commit -m "feat(phase4-fe): /logs page with filters, expandable diffs, CSV export, cursor pagination"
```

---

## Task 6: Final Frontend Verification

- [ ] **Step 1: Run frontend tests**

```bash
cd frontend && npm run test -- --run
```
Expected: All tests PASS.

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Acceptance walkthrough in browser**

Start backend + frontend:

```bash
# Terminal 1: backend
cd backend && uv run uvicorn finacialsim_saas.main:app --reload

# Terminal 2: frontend
cd frontend && npm run dev
```

Walk through:

| Check | Expected |
|---|---|
| `/indicadores` as admin | Cards for all 4 codigos; "↻ Atualizar agora" button visible |
| `/indicadores` as user | Cards visible; no refresh button |
| Mini chart on SELIC card | Line chart renders if data exists |
| `/configuracoes/regras` as admin | Table of all rule keys; inline edit works; saves toast |
| `/configuracoes/regras` as manager | 403 redirect |
| `taxa_por_prazo_curva` row editor | Add/remove rows; save |
| `/logs` as admin | Paginated table; expand row shows diff |
| `/logs` filter ação=create | Only create entries |
| CSV export | Downloads `audit-log.csv` |
| `/logs` as user | Shows only own entries |

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore(phase4-fe): frontend complete — indicadores, regras, logs pages verified"
```
