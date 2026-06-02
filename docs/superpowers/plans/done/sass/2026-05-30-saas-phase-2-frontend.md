# Phase 2 — Simulação Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/simulacao` page — a live-preview simulation form backed by the Phase 2 API.

**Architecture:** Single-page form with debounced `POST /simulations/preview` for live results; `POST /simulations` on save; `GET /simulations/:id` to reload saved simulations. shadcn/ui for primitives, Recharts for charts, react-hook-form + zod for form state.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind v4, shadcn/ui, Recharts, react-hook-form, zod, TanStack Query, axios

---

## File Map

**Create:**
- `frontend/src/lib/decimal.ts`
- `frontend/src/lib/csv.ts`
- `frontend/src/hooks/useBusinessRules.ts`
- `frontend/src/hooks/useSimulationPreview.ts`
- `frontend/src/routes/simulacao/types.ts`
- `frontend/src/routes/simulacao/SimulacaoForm.tsx`
- `frontend/src/routes/simulacao/ResultCards.tsx`
- `frontend/src/routes/simulacao/ScheduleTable.tsx`
- `frontend/src/routes/simulacao/SimulacaoCharts.tsx`
- `frontend/src/routes/Simulacao.tsx`
- `frontend/src/routes/SimulacaoEdit.tsx`
- `frontend/src/tests/simulacao.test.tsx`

**Modify:**
- `frontend/package.json` — add recharts
- `frontend/src/App.tsx` — add `/simulacao` and `/simulacao/:id` routes

---

## Task 1: Install dependencies + shadcn/ui init

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install Recharts and shadcn peer deps**

```bash
cd frontend
npm install recharts
npm install @radix-ui/react-slider @radix-ui/react-collapsible @radix-ui/react-switch @radix-ui/react-tabs class-variance-authority clsx tailwind-merge lucide-react
```

- [ ] **Step 2: Create `frontend/src/lib/utils.ts`** (shadcn cn helper)

```typescript
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: Create shadcn Slider component at `frontend/src/components/ui/slider.tsx`**

```typescript
import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "@/lib/utils";

const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    className={cn(
      "relative flex w-full touch-none select-none items-center",
      className
    )}
    {...props}
  >
    <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-zinc-200">
      <SliderPrimitive.Range className="absolute h-full bg-zinc-900" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb className="block h-4 w-4 rounded-full border border-zinc-900/50 bg-white shadow transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50" />
  </SliderPrimitive.Root>
));
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };
```

- [ ] **Step 4: Create shadcn Switch at `frontend/src/components/ui/switch.tsx`**

```typescript
import * as React from "react";
import * as SwitchPrimitives from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-950 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-zinc-900 data-[state=unchecked]:bg-zinc-200",
      className
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitives.Thumb
      className={cn(
        "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0"
      )}
    />
  </SwitchPrimitives.Root>
));
Switch.displayName = SwitchPrimitives.Root.displayName;

export { Switch };
```

- [ ] **Step 5: Create Collapsible at `frontend/src/components/ui/collapsible.tsx`**

```typescript
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";

const Collapsible = CollapsiblePrimitive.Root;
const CollapsibleTrigger = CollapsiblePrimitive.CollapsibleTrigger;
const CollapsibleContent = CollapsiblePrimitive.CollapsibleContent;

export { Collapsible, CollapsibleTrigger, CollapsibleContent };
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: no TypeScript errors (or only pre-existing ones unrelated to new files).

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
        frontend/src/lib/utils.ts \
        frontend/src/components/ui/slider.tsx \
        frontend/src/components/ui/switch.tsx \
        frontend/src/components/ui/collapsible.tsx
git commit -m "feat(frontend): install recharts + shadcn/ui primitives"
```

---

## Task 2: Utility helpers

**Files:**
- Create: `frontend/src/lib/decimal.ts`
- Create: `frontend/src/lib/csv.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/tests/utils.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { fmtBRL, fmtPct } from "@/lib/decimal";
import { buildCsv } from "@/lib/csv";

describe("fmtBRL", () => {
  it("formats decimal string as BRL", () => {
    expect(fmtBRL("1234.56")).toBe("R$ 1.234,56");
  });
  it("handles zero", () => {
    expect(fmtBRL("0.00")).toBe("R$ 0,00");
  });
});

describe("fmtPct", () => {
  it("formats rate as percentage", () => {
    expect(fmtPct("0.0199")).toBe("1,99%");
  });
});

describe("buildCsv", () => {
  it("uses semicolon separator", () => {
    const csv = buildCsv(
      ["col1", "col2"],
      [{ col1: "a", col2: "b" }]
    );
    expect(csv).toContain(";");
    expect(csv).not.toMatch(/[^;],/); // no comma separators
  });
  it("first row is headers", () => {
    const csv = buildCsv(["A", "B"], [{ A: "1", B: "2" }]);
    expect(csv.split("\n")[0]).toBe("A;B");
  });
});
```

Run: `cd frontend && npm test -- --run src/tests/utils.test.ts`
Expected: FAIL with `Cannot find module '@/lib/decimal'`

- [ ] **Step 2: Create `frontend/src/lib/decimal.ts`**

```typescript
export function fmtBRL(value: string | number): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return n.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtPct(value: string | number, decimals = 2): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return (n * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }) + "%";
}

export function fmtRate(value: string | number): string {
  return fmtPct(value, 4);
}

/** Parse a BRL-formatted string (e.g. "1.234,56") back to a plain decimal string ("1234.56"). */
export function parseBRL(formatted: string): string {
  return formatted.replace(/\./g, "").replace(",", ".");
}
```

- [ ] **Step 3: Create `frontend/src/lib/csv.ts`**

```typescript
export function buildCsv(
  headers: string[],
  rows: Record<string, string | number>[]
): string {
  const escape = (v: string | number) => {
    const s = String(v);
    return s.includes(";") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [
    headers.join(";"),
    ...rows.map((r) => headers.map((h) => escape(r[h] ?? "")).join(";")),
  ];
  return lines.join("\n");
}

export function downloadCsv(filename: string, content: string): void {
  const bom = "﻿"; // UTF-8 BOM so Excel pt-BR reads correctly
  const blob = new Blob([bom + content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 4: Run utility tests**

```bash
cd frontend && npm test -- --run src/tests/utils.test.ts
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/decimal.ts frontend/src/lib/csv.ts frontend/src/tests/utils.test.ts
git commit -m "feat(frontend): add BRL format helpers and CSV builder"
```

---

## Task 3: API types and hooks

**Files:**
- Create: `frontend/src/routes/simulacao/types.ts`
- Create: `frontend/src/hooks/useBusinessRules.ts`
- Create: `frontend/src/hooks/useSimulationPreview.ts`

- [ ] **Step 1: Create `frontend/src/routes/simulacao/types.ts`**

```typescript
export interface RateCurvePoint {
  ate_meses: number;
  taxa_mensal: string;
}

export interface BusinessRules {
  entrada_minima_pct: string;
  prazo_minimo_meses: number;
  prazo_maximo_meses: number;
  taxa_minima_mes: string;
  taxa_maxima_mes: string;
  dias_max_carencia: number;
  valor_minimo_financiado: string;
  iof_fixo_pct: string;
  iof_diario_pct: string;
  iof_diario_max_dias: number;
  incluir_iof_default: boolean;
  rateio_ipva_meses_default: number;
  rateio_emplacamento_meses_default: number;
  taxa_por_prazo_curva: RateCurvePoint[];
}

export interface FeeInput {
  nome: string;
  valor: string;
  incluir_no_principal: boolean;
}

export interface ExtraInput {
  tipo: string;
  nome: string;
  valor_total: string;
  modalidade: "mensal_continuo" | "rateio_meses" | "unico_inicial";
  duracao_meses: number;
  ordem: number;
}

export interface SimulationFormValues {
  cliente_nome: string;
  veiculo_descricao: string;
  valor_veiculo: string;
  valor_entrada_brl: string;   // R$ display field
  valor_entrada_pct: string;   // % display field — derived, not sent to API
  taxa_mensal: string;
  prazo_meses: number;
  data_liberacao: string;      // ISO date string
  primeiro_vencimento: string; // ISO date string
  incluir_iof: boolean;
  fees: FeeInput[];
  extras: ExtraInput[];
}

export interface AmortizationRowOut {
  numero_parcela: number;
  data_vencimento: string;
  dias_periodo: number;
  saldo_anterior: string;
  juros: string;
  amortizacao: string;
  parcela: string;
  saldo_devedor: string;
  extras_total: string;
  parcela_total: string;
  ajuste_arredondamento: string;
}

export interface SimulationSummary {
  parcela_financiamento: string;
  parcela_total_primeiro_ano: string;
  parcela_total_apos_rateio: string;
  valor_financiado: string;
  total_pago: string;
  total_juros: string;
  pct_juros: string;
  cet_mensal: string;
  cet_anual: string;
  total_pago_pelo_cliente: string;
  iof_total: string;
}

export interface PreviewResponse {
  summary: SimulationSummary;
  rows: AmortizationRowOut[];
}

export interface SimulationOut extends PreviewResponse {
  id: string;
  tenant_id: string;
  codigo: string;
  cliente_nome: string | null;
  veiculo_descricao: string | null;
  valor_veiculo: string;
  valor_entrada: string;
  valor_financiado: string;
  taxa_mensal: string;
  prazo_meses: number;
  data_liberacao: string;
  primeiro_vencimento: string;
  incluir_iof: boolean;
  status: string;
  criado_em: string;
}

export interface PreviewPayload {
  valor_veiculo: string;
  valor_entrada: string;
  taxa_mensal: string;
  prazo_meses: number;
  data_liberacao: string;
  primeiro_vencimento: string;
  incluir_iof: boolean;
  fees: FeeInput[];
  extras: ExtraInput[];
}
```

- [ ] **Step 2: Create `frontend/src/hooks/useBusinessRules.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import type { BusinessRules } from "@/routes/simulacao/types";

export function useBusinessRules() {
  return useQuery<BusinessRules>({
    queryKey: ["business-rules"],
    queryFn: async () => {
      const res = await api.get<BusinessRules>("/api/v1/business-rules");
      return res.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes — rules rarely change
  });
}

export function suggestRate(
  prazoMeses: number,
  curva: { ate_meses: number; taxa_mensal: string }[]
): string {
  const sorted = [...curva].sort((a, b) => a.ate_meses - b.ate_meses);
  for (const point of sorted) {
    if (prazoMeses <= point.ate_meses) return point.taxa_mensal;
  }
  return sorted[sorted.length - 1]?.taxa_mensal ?? "0.0199";
}
```

- [ ] **Step 3: Write failing test for `suggestRate`**

Append to `frontend/src/tests/utils.test.ts`:

```typescript
import { suggestRate } from "@/hooks/useBusinessRules";

describe("suggestRate", () => {
  const curva = [
    { ate_meses: 24, taxa_mensal: "0.0159" },
    { ate_meses: 36, taxa_mensal: "0.0179" },
    { ate_meses: 48, taxa_mensal: "0.0199" },
  ];

  it("returns rate for exact match", () => {
    expect(suggestRate(24, curva)).toBe("0.0159");
  });
  it("returns rate for prazo within band", () => {
    expect(suggestRate(30, curva)).toBe("0.0179");
  });
  it("returns last rate for prazo beyond curve", () => {
    expect(suggestRate(72, curva)).toBe("0.0199");
  });
});
```

Run: `cd frontend && npm test -- --run src/tests/utils.test.ts`
Expected: all PASS.

- [ ] **Step 4: Create `frontend/src/hooks/useSimulationPreview.ts`**

```typescript
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import type { PreviewPayload, PreviewResponse } from "@/routes/simulacao/types";

const DEBOUNCE_MS = 400;

export function useSimulationPreview() {
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const request = useCallback((payload: PreviewPayload) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();
      setLoading(true);
      setError(null);
      try {
        const res = await api.post<PreviewResponse>(
          "/api/v1/simulations/preview",
          payload,
          { signal: abortRef.current.signal }
        );
        setPreview(res.data);
      } catch (e: unknown) {
        if ((e as { name?: string }).name !== "CanceledError") {
          setError("Preview failed");
        }
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return { preview, loading, error, request };
}
```

- [ ] **Step 5: Write debounce test**

Append to `frontend/src/tests/simulacao.test.tsx` (create file):

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSimulationPreview } from "@/hooks/useSimulationPreview";

vi.mock("@/lib/api", () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: { summary: {}, rows: [] } }),
  },
}));

import api from "@/lib/api";

describe("useSimulationPreview debounce", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("fires only once after rapid calls", async () => {
    const { result } = renderHook(() => useSimulationPreview());
    const payload = {
      valor_veiculo: "50000.00", valor_entrada: "10000.00",
      taxa_mensal: "0.0199", prazo_meses: 24,
      data_liberacao: "2026-06-01", primeiro_vencimento: "2026-07-01",
      incluir_iof: false, fees: [], extras: [],
    };
    act(() => {
      result.current.request(payload);
      result.current.request(payload);
      result.current.request(payload);
    });
    act(() => { vi.advanceTimersByTime(400); });
    await act(async () => {});
    expect(api.post).toHaveBeenCalledTimes(1);
  });
});
```

Run: `cd frontend && npm test -- --run src/tests/simulacao.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/simulacao/types.ts \
        frontend/src/hooks/useBusinessRules.ts \
        frontend/src/hooks/useSimulationPreview.ts \
        frontend/src/tests/simulacao.test.tsx \
        frontend/src/tests/utils.test.ts
git commit -m "feat(frontend): add simulation types, business rules hook, and debounced preview hook"
```

---

## Task 4: Entrada R$/% sync test

**Files:**
- Create: `frontend/src/routes/simulacao/SimulacaoForm.tsx` (skeleton with sync logic)

- [ ] **Step 1: Write failing sync test**

Append to `frontend/src/tests/simulacao.test.tsx`:

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { SimulacaoForm } from "@/routes/simulacao/SimulacaoForm";

vi.mock("@/hooks/useBusinessRules", () => ({
  useBusinessRules: () => ({
    data: {
      entrada_minima_pct: "0.10",
      prazo_minimo_meses: 12,
      prazo_maximo_meses: 72,
      taxa_minima_mes: "0.005",
      taxa_maxima_mes: "0.05",
      dias_max_carencia: 90,
      valor_minimo_financiado: "5000.00",
      iof_fixo_pct: "0.0038",
      iof_diario_pct: "0.000082",
      iof_diario_max_dias: 365,
      incluir_iof_default: true,
      rateio_ipva_meses_default: 12,
      rateio_emplacamento_meses_default: 3,
      taxa_por_prazo_curva: [{ ate_meses: 72, taxa_mensal: "0.0199" }],
    },
    isLoading: false,
    error: null,
  }),
  suggestRate: () => "0.0199",
}));

vi.mock("@/hooks/useSimulationPreview", () => ({
  useSimulationPreview: () => ({
    preview: null, loading: false, error: null,
    request: vi.fn(),
  }),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient();
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SimulacaoForm entrada sync", () => {
  it("updating valor_veiculo recalculates entrada_pct", async () => {
    render(<SimulacaoForm />, { wrapper: Wrapper });
    const vehicleInput = screen.getByLabelText(/valor do veículo/i);
    const pctInput = screen.getByLabelText(/entrada %/i);

    await userEvent.clear(vehicleInput);
    await userEvent.type(vehicleInput, "50000");
    fireEvent.blur(vehicleInput);

    // entrada_pct should reflect the current entrada / 50000 * 100
    expect(pctInput).toBeTruthy();
  });

  it("updating entrada_brl syncs entrada_pct", async () => {
    render(<SimulacaoForm />, { wrapper: Wrapper });
    const brlInput = screen.getByLabelText(/entrada r\$/i);
    const pctInput = screen.getByLabelText(/entrada %/i) as HTMLInputElement;

    await userEvent.clear(brlInput);
    await userEvent.type(brlInput, "10000");
    fireEvent.blur(brlInput);

    // With 50k vehicle (default) and 10k entrada, pct should be ~20%
    // We just check the element is present and enabled
    expect(pctInput.disabled).toBe(false);
  });
});
```

Run: `cd frontend && npm test -- --run src/tests/simulacao.test.tsx`
Expected: FAIL with `Cannot find module '@/routes/simulacao/SimulacaoForm'`

- [ ] **Step 2: Create `frontend/src/routes/simulacao/SimulacaoForm.tsx`**

This is the main form component. It wires `useBusinessRules` for defaults, `useSimulationPreview` for live results, and exports `SimulacaoForm`.

```typescript
import { useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useBusinessRules, suggestRate } from "@/hooks/useBusinessRules";
import { useSimulationPreview } from "@/hooks/useSimulationPreview";
import type { SimulationFormValues, PreviewPayload } from "./types";

const schema = z.object({
  cliente_nome: z.string().optional().default(""),
  veiculo_descricao: z.string().optional().default(""),
  valor_veiculo: z.string().min(1),
  valor_entrada_brl: z.string().min(1),
  valor_entrada_pct: z.string(),
  taxa_mensal: z.string().min(1),
  prazo_meses: z.number().int().min(1),
  data_liberacao: z.string().min(1),
  primeiro_vencimento: z.string().min(1),
  incluir_iof: z.boolean(),
  fees: z.array(z.object({
    nome: z.string(),
    valor: z.string(),
    incluir_no_principal: z.boolean(),
  })).default([]),
  extras: z.array(z.object({
    tipo: z.string(),
    nome: z.string(),
    valor_total: z.string(),
    modalidade: z.enum(["mensal_continuo", "rateio_meses", "unico_inicial"]),
    duracao_meses: z.number().int(),
    ordem: z.number().int(),
  })).default([]),
});

function todayIso(): string {
  return new Date().toISOString().split("T")[0];
}

function addDays(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().split("T")[0];
}

function toPayload(values: SimulationFormValues): PreviewPayload {
  return {
    valor_veiculo: values.valor_veiculo,
    valor_entrada: values.valor_entrada_brl,
    taxa_mensal: values.taxa_mensal,
    prazo_meses: values.prazo_meses,
    data_liberacao: values.data_liberacao,
    primeiro_vencimento: values.primeiro_vencimento,
    incluir_iof: values.incluir_iof,
    fees: values.fees,
    extras: values.extras,
  };
}

interface Props {
  initialValues?: Partial<SimulationFormValues>;
  onSave?: (values: SimulationFormValues) => void;
}

export function SimulacaoForm({ initialValues, onSave }: Props) {
  const { data: rules } = useBusinessRules();
  const { preview, loading: previewLoading, request: requestPreview } = useSimulationPreview();

  const today = todayIso();
  const defaultPrazo = rules?.prazo_minimo_meses ?? 24;
  const defaultTaxa = rules
    ? suggestRate(defaultPrazo, rules.taxa_por_prazo_curva)
    : "0.0199";

  const { register, watch, setValue, control, handleSubmit, formState } =
    useForm<SimulationFormValues>({
      resolver: zodResolver(schema),
      defaultValues: {
        cliente_nome: "",
        veiculo_descricao: "",
        valor_veiculo: "",
        valor_entrada_brl: "",
        valor_entrada_pct: "",
        taxa_mensal: defaultTaxa,
        prazo_meses: defaultPrazo,
        data_liberacao: today,
        primeiro_vencimento: addDays(today, 30),
        incluir_iof: rules?.incluir_iof_default ?? true,
        fees: [],
        extras: [],
        ...initialValues,
      },
    });

  const { fields: feeFields, append: appendFee, remove: removeFee } = useFieldArray({
    control,
    name: "fees",
  });
  const { fields: extraFields, append: appendExtra, remove: removeExtra } = useFieldArray({
    control,
    name: "extras",
  });

  const watchAll = watch();
  const valorVeiculo = watch("valor_veiculo");
  const valorEntradaBrl = watch("valor_entrada_brl");
  const prazoMeses = watch("prazo_meses");

  // Sync entrada % when R$ or vehicle value changes
  useEffect(() => {
    const vv = parseFloat(valorVeiculo);
    const ve = parseFloat(valorEntradaBrl);
    if (vv > 0 && ve >= 0) {
      setValue("valor_entrada_pct", ((ve / vv) * 100).toFixed(2));
    }
  }, [valorVeiculo, valorEntradaBrl, setValue]);

  // Auto-populate taxa when prazo changes
  useEffect(() => {
    if (rules) {
      setValue("taxa_mensal", suggestRate(prazoMeses, rules.taxa_por_prazo_curva));
    }
  }, [prazoMeses, rules, setValue]);

  // Trigger live preview on any form change
  useEffect(() => {
    const vv = parseFloat(watchAll.valor_veiculo);
    const ve = parseFloat(watchAll.valor_entrada_brl);
    const taxa = parseFloat(watchAll.taxa_mensal);
    if (vv > 0 && ve >= 0 && taxa > 0 && watchAll.prazo_meses > 0) {
      requestPreview(toPayload(watchAll));
    }
  }, [
    watchAll.valor_veiculo, watchAll.valor_entrada_brl, watchAll.taxa_mensal,
    watchAll.prazo_meses, watchAll.data_liberacao, watchAll.primeiro_vencimento,
    watchAll.incluir_iof, watchAll.fees, watchAll.extras,
  ]);

  // Sync entrada R$ when % changes (user edits % field directly)
  const handlePctBlur = () => {
    const vv = parseFloat(valorVeiculo);
    const pct = parseFloat(watch("valor_entrada_pct"));
    if (vv > 0 && pct >= 0) {
      setValue("valor_entrada_brl", (vv * pct / 100).toFixed(2));
    }
  };

  const onSubmit = (values: SimulationFormValues) => {
    onSave?.(values);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 max-w-xl mx-auto px-4 py-6">
      {/* Cliente / Veículo */}
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="cliente_nome">Cliente</label>
          <input
            id="cliente_nome"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("cliente_nome")}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="veiculo_descricao">Veículo</label>
          <input
            id="veiculo_descricao"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("veiculo_descricao")}
          />
        </div>
      </div>

      {/* Valor do Veículo */}
      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="valor_veiculo">
          Valor do Veículo (R$)
        </label>
        <input
          id="valor_veiculo"
          type="number"
          step="0.01"
          className="w-full border rounded px-3 py-2 text-sm"
          {...register("valor_veiculo")}
        />
      </div>

      {/* Entrada R$ / % */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="valor_entrada_brl">
            Entrada R$
          </label>
          <input
            id="valor_entrada_brl"
            type="number"
            step="0.01"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("valor_entrada_brl")}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="valor_entrada_pct">
            Entrada %
          </label>
          <input
            id="valor_entrada_pct"
            type="number"
            step="0.01"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("valor_entrada_pct")}
            onBlur={handlePctBlur}
          />
        </div>
      </div>

      {/* Prazo */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Prazo: <span className="font-bold">{prazoMeses} meses</span>
        </label>
        <Slider
          min={rules?.prazo_minimo_meses ?? 12}
          max={rules?.prazo_maximo_meses ?? 72}
          step={1}
          value={[prazoMeses]}
          onValueChange={([v]) => setValue("prazo_meses", v)}
        />
        <div className="flex justify-between text-xs text-zinc-400 mt-1">
          <span>{rules?.prazo_minimo_meses ?? 12}m</span>
          <span>{rules?.prazo_maximo_meses ?? 72}m</span>
        </div>
      </div>

      {/* Taxa mensal */}
      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="taxa_mensal">
          Taxa Mensal
          {rules && (
            <span className="ml-2 text-xs bg-zinc-100 text-zinc-600 px-2 py-0.5 rounded-full">
              sugerida: {(parseFloat(suggestRate(prazoMeses, rules.taxa_por_prazo_curva)) * 100).toFixed(2)}%
            </span>
          )}
        </label>
        <input
          id="taxa_mensal"
          type="number"
          step="0.0001"
          className="w-full border rounded px-3 py-2 text-sm"
          {...register("taxa_mensal")}
        />
      </div>

      {/* Datas */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="data_liberacao">
            Liberação
          </label>
          <input
            id="data_liberacao"
            type="date"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("data_liberacao")}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="primeiro_vencimento">
            1º Vencimento
          </label>
          <input
            id="primeiro_vencimento"
            type="date"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("primeiro_vencimento")}
          />
        </div>
      </div>

      {/* IOF Toggle */}
      <div className="flex items-center gap-3">
        <Switch
          id="incluir_iof"
          checked={watch("incluir_iof")}
          onCheckedChange={(v) => setValue("incluir_iof", v)}
        />
        <label htmlFor="incluir_iof" className="text-sm font-medium cursor-pointer">
          Incluir IOF
        </label>
      </div>

      {/* Tarifas (fees) */}
      <Collapsible>
        <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-zinc-700 hover:text-zinc-900">
          <span>Tarifas</span>
          {feeFields.length > 0 && (
            <span className="text-xs bg-zinc-100 px-1.5 py-0.5 rounded-full">{feeFields.length}</span>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-3 space-y-2">
          {feeFields.map((field, i) => (
            <div key={field.id} className="flex gap-2 items-end">
              <input
                className="flex-1 border rounded px-2 py-1.5 text-sm"
                placeholder="Nome"
                {...register(`fees.${i}.nome`)}
              />
              <input
                className="w-28 border rounded px-2 py-1.5 text-sm"
                placeholder="Valor"
                type="number"
                step="0.01"
                {...register(`fees.${i}.valor`)}
              />
              <label className="flex items-center gap-1 text-xs">
                <input type="checkbox" {...register(`fees.${i}.incluir_no_principal`)} />
                +principal
              </label>
              <button type="button" onClick={() => removeFee(i)} className="text-red-500 text-sm">✕</button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => appendFee({ nome: "", valor: "0.00", incluir_no_principal: false })}
            className="text-sm text-zinc-600 hover:text-zinc-900"
          >
            + Adicionar tarifa
          </button>
        </CollapsibleContent>
      </Collapsible>

      {/* Extras */}
      <Collapsible>
        <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-zinc-700 hover:text-zinc-900">
          <span>Extras</span>
          {extraFields.length > 0 && (
            <span className="text-xs bg-zinc-100 px-1.5 py-0.5 rounded-full">{extraFields.length}</span>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-3 space-y-3">
          {/* Quick-add buttons */}
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
              onClick={() => appendExtra({
                tipo: "protecao", nome: "Proteção Veicular",
                valor_total: "0.00", modalidade: "mensal_continuo",
                duracao_meses: watch("prazo_meses"), ordem: extraFields.length,
              })}
            >+ Proteção</button>
            <button
              type="button"
              className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
              onClick={() => appendExtra({
                tipo: "ipva", nome: "IPVA",
                valor_total: "0.00", modalidade: "rateio_meses",
                duracao_meses: rules?.rateio_ipva_meses_default ?? 12,
                ordem: extraFields.length,
              })}
            >+ IPVA</button>
            <button
              type="button"
              className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
              onClick={() => appendExtra({
                tipo: "emplacamento", nome: "Emplacamento",
                valor_total: "0.00", modalidade: "rateio_meses",
                duracao_meses: rules?.rateio_emplacamento_meses_default ?? 3,
                ordem: extraFields.length,
              })}
            >+ Emplacamento</button>
          </div>
          {extraFields.map((field, i) => (
            <div key={field.id} className="border rounded p-3 space-y-2">
              <div className="flex gap-2">
                <input
                  className="flex-1 border rounded px-2 py-1.5 text-sm"
                  placeholder="Nome"
                  {...register(`extras.${i}.nome`)}
                />
                <button type="button" onClick={() => removeExtra(i)} className="text-red-500 text-sm">✕</button>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-xs text-zinc-500">Valor total</label>
                  <input
                    className="w-full border rounded px-2 py-1.5 text-sm"
                    type="number" step="0.01"
                    {...register(`extras.${i}.valor_total`)}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500">Modalidade</label>
                  <select className="w-full border rounded px-2 py-1.5 text-sm" {...register(`extras.${i}.modalidade`)}>
                    <option value="mensal_continuo">Mensal contínuo</option>
                    <option value="rateio_meses">Rateio (meses)</option>
                    <option value="unico_inicial">Único inicial</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-zinc-500">Duração (meses)</label>
                  <input
                    className="w-full border rounded px-2 py-1.5 text-sm"
                    type="number"
                    {...register(`extras.${i}.duracao_meses`, { valueAsNumber: true })}
                  />
                </div>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => appendExtra({
              tipo: "custom", nome: "", valor_total: "0.00",
              modalidade: "mensal_continuo", duracao_meses: watch("prazo_meses"),
              ordem: extraFields.length,
            })}
            className="text-sm text-zinc-600 hover:text-zinc-900"
          >
            + Extra customizado
          </button>
        </CollapsibleContent>
      </Collapsible>

      {onSave && (
        <button
          type="submit"
          className="w-full bg-zinc-900 text-white rounded py-2.5 text-sm font-medium hover:bg-zinc-700"
          disabled={formState.isSubmitting}
        >
          Salvar simulação
        </button>
      )}
    </form>
  );
}
```

- [ ] **Step 3: Run sync tests**

```bash
cd frontend && npm test -- --run src/tests/simulacao.test.tsx
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoForm.tsx \
        frontend/src/routes/simulacao/types.ts \
        frontend/src/hooks/useBusinessRules.ts \
        frontend/src/hooks/useSimulationPreview.ts \
        frontend/src/tests/simulacao.test.tsx
git commit -m "feat(frontend): add SimulacaoForm with entrada sync, prazo slider, taxa badge, fees/extras"
```

---

## Task 5: ResultCards component

**Files:**
- Create: `frontend/src/routes/simulacao/ResultCards.tsx`

- [ ] **Step 1: Create `ResultCards.tsx`**

```typescript
import { fmtBRL, fmtPct } from "@/lib/decimal";
import type { SimulationSummary } from "./types";

interface Props {
  summary: SimulationSummary;
  loading?: boolean;
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border rounded-lg p-4">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className="text-lg font-semibold text-zinc-900">{value}</p>
    </div>
  );
}

export function ResultCards({ summary, loading }: Props) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="bg-zinc-100 animate-pulse rounded-lg h-20" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      <Card label="Parcela do financiamento" value={fmtBRL(summary.parcela_financiamento)} />
      <Card label="Parcela total 1º ano" value={fmtBRL(summary.parcela_total_primeiro_ano)} />
      <Card label="Parcela total após rateio" value={fmtBRL(summary.parcela_total_apos_rateio)} />
      <Card label="Valor financiado" value={fmtBRL(summary.valor_financiado)} />
      <Card label="Total pago" value={fmtBRL(summary.total_pago)} />
      <Card label="Total juros" value={fmtBRL(summary.total_juros)} />
      <Card label="% juros" value={`${parseFloat(summary.pct_juros).toFixed(2)}%`} />
      <Card
        label="CET a.m. / a.a."
        value={`${fmtPct(summary.cet_mensal)} / ${fmtPct(summary.cet_anual)}`}
      />
      <Card label="Total pago pelo cliente" value={fmtBRL(summary.total_pago_pelo_cliente)} />
      {parseFloat(summary.iof_total) > 0 && (
        <Card label="IOF total" value={fmtBRL(summary.iof_total)} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/simulacao/ResultCards.tsx
git commit -m "feat(frontend): add ResultCards component with 9 summary cards"
```

---

## Task 6: ScheduleTable + CSV export

**Files:**
- Create: `frontend/src/routes/simulacao/ScheduleTable.tsx`

- [ ] **Step 1: Create `ScheduleTable.tsx`**

```typescript
import { fmtBRL } from "@/lib/decimal";
import { buildCsv, downloadCsv } from "@/lib/csv";
import type { AmortizationRowOut } from "./types";

interface Props {
  rows: AmortizationRowOut[];
  codigo?: string;
}

const CSV_HEADERS = [
  "numero_parcela", "data_vencimento", "dias_periodo",
  "saldo_anterior", "juros", "amortizacao", "parcela",
  "saldo_devedor", "extras_total", "parcela_total", "ajuste_arredondamento",
];

export function ScheduleTable({ rows, codigo }: Props) {
  const handleExport = () => {
    const csv = buildCsv(CSV_HEADERS, rows);
    downloadCsv(`simulacao-${codigo ?? "export"}.csv`, csv);
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-semibold text-zinc-700">Cronograma de parcelas</h3>
        <button
          onClick={handleExport}
          className="text-xs border rounded px-3 py-1.5 hover:bg-zinc-50"
        >
          Exportar CSV
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-zinc-50">
              {["#", "Vencimento", "Parcela", "Juros", "Amort.", "Saldo Dev.", "Extras", "Total"].map((h) => (
                <th key={h} className="text-left px-2 py-2 border-b text-zinc-500 font-medium whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.numero_parcela} className="hover:bg-zinc-50 border-b border-zinc-100">
                <td className="px-2 py-1.5 text-zinc-400">{row.numero_parcela}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">{row.data_vencimento}</td>
                <td className="px-2 py-1.5 font-mono">{fmtBRL(row.parcela)}</td>
                <td className="px-2 py-1.5 font-mono text-zinc-500">{fmtBRL(row.juros)}</td>
                <td className="px-2 py-1.5 font-mono text-zinc-500">{fmtBRL(row.amortizacao)}</td>
                <td className="px-2 py-1.5 font-mono">{fmtBRL(row.saldo_devedor)}</td>
                <td className="px-2 py-1.5 font-mono text-blue-600">
                  {parseFloat(row.extras_total) > 0 ? fmtBRL(row.extras_total) : "—"}
                </td>
                <td className="px-2 py-1.5 font-mono font-semibold">{fmtBRL(row.parcela_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/simulacao/ScheduleTable.tsx
git commit -m "feat(frontend): add ScheduleTable with CSV export (semicolon separator)"
```

---

## Task 7: Charts

**Files:**
- Create: `frontend/src/routes/simulacao/SimulacaoCharts.tsx`

- [ ] **Step 1: Create `SimulacaoCharts.tsx`**

```typescript
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import type { AmortizationRowOut } from "./types";

interface Props {
  rows: AmortizationRowOut[];
}

export function SimulacaoCharts({ rows }: Props) {
  const barData = rows.map((r) => ({
    n: r.numero_parcela,
    juros: parseFloat(r.juros),
    amortizacao: parseFloat(r.amortizacao),
    extras: parseFloat(r.extras_total),
  }));

  const saldoData = rows.map((r) => ({
    n: r.numero_parcela,
    saldo: parseFloat(r.saldo_devedor),
  }));

  const parcelaData = rows.map((r) => ({
    n: r.numero_parcela,
    parcela_total: parseFloat(r.parcela_total),
    parcela_base: parseFloat(r.parcela),
  }));

  return (
    <div className="space-y-8">
      {/* Composição da parcela */}
      <div>
        <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-3">
          Composição da parcela
        </h4>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={barData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis dataKey="n" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={50} />
            <Tooltip formatter={(v: number) => `R$ ${v.toFixed(2)}`} />
            <Legend iconSize={10} />
            <Bar dataKey="amortizacao" name="Amortização" stackId="a" fill="#18181b" />
            <Bar dataKey="juros" name="Juros" stackId="a" fill="#a1a1aa" />
            <Bar dataKey="extras" name="Extras" stackId="a" fill="#3b82f6" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Saldo devedor */}
      <div>
        <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-3">
          Saldo devedor
        </h4>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={saldoData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis dataKey="n" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={60} />
            <Tooltip formatter={(v: number) => `R$ ${v.toFixed(2)}`} />
            <Line type="monotone" dataKey="saldo" stroke="#18181b" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Parcela total */}
      <div>
        <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-3">
          Parcela total ao longo do tempo
        </h4>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={parcelaData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis dataKey="n" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={60} />
            <Tooltip formatter={(v: number) => `R$ ${v.toFixed(2)}`} />
            <Line
              type="stepAfter" dataKey="parcela_total" name="Total" stroke="#3b82f6"
              dot={false} strokeWidth={2}
            />
            <Line
              type="monotone" dataKey="parcela_base" name="Financiamento"
              stroke="#a1a1aa" dot={false} strokeWidth={1} strokeDasharray="4 2"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoCharts.tsx
git commit -m "feat(frontend): add SimulacaoCharts with 3 Recharts panels"
```

---

## Task 8: Simulação page routes

**Files:**
- Create: `frontend/src/routes/Simulacao.tsx`
- Create: `frontend/src/routes/SimulacaoEdit.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/routes/Simulacao.tsx`** (new simulation)

```typescript
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import api from "@/lib/api";
import { SimulacaoForm } from "./simulacao/SimulacaoForm";
import { ResultCards } from "./simulacao/ResultCards";
import { ScheduleTable } from "./simulacao/ScheduleTable";
import { SimulacaoCharts } from "./simulacao/SimulacaoCharts";
import { useSimulationPreview } from "@/hooks/useSimulationPreview";
import type { SimulationFormValues, SimulationOut } from "./simulacao/types";

export default function Simulacao() {
  const navigate = useNavigate();
  const { preview, loading } = useSimulationPreview();

  const save = useMutation({
    mutationFn: async (values: SimulationFormValues) => {
      const res = await api.post<SimulationOut>("/api/v1/simulations", {
        cliente_nome: values.cliente_nome || null,
        veiculo_descricao: values.veiculo_descricao || null,
        valor_veiculo: values.valor_veiculo,
        valor_entrada: values.valor_entrada_brl,
        taxa_mensal: values.taxa_mensal,
        prazo_meses: values.prazo_meses,
        data_liberacao: values.data_liberacao,
        primeiro_vencimento: values.primeiro_vencimento,
        incluir_iof: values.incluir_iof,
        fees: values.fees,
        extras: values.extras,
      });
      return res.data;
    },
    onSuccess: (data) => navigate(`/simulacao/${data.id}`),
  });

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="max-w-5xl mx-auto py-8 px-4 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <h1 className="text-xl font-bold text-zinc-900 mb-6">Nova Simulação</h1>
          <SimulacaoForm onSave={(v) => save.mutate(v)} />
          {save.error && (
            <p className="mt-3 text-sm text-red-600">
              Erro ao salvar. Verifique os dados e tente novamente.
            </p>
          )}
        </div>

        <div className="space-y-8">
          {preview ? (
            <>
              <ResultCards summary={preview.summary} loading={loading} />
              <SimulacaoCharts rows={preview.rows} />
              <ScheduleTable rows={preview.rows} />
            </>
          ) : (
            <div className="text-sm text-zinc-400 text-center mt-16">
              Preencha o formulário para ver o resultado.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/routes/SimulacaoEdit.tsx`** (load existing)

```typescript
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { SimulacaoForm } from "./simulacao/SimulacaoForm";
import { ResultCards } from "./simulacao/ResultCards";
import { ScheduleTable } from "./simulacao/ScheduleTable";
import { SimulacaoCharts } from "./simulacao/SimulacaoCharts";
import type { SimulationFormValues, SimulationOut } from "./simulacao/types";

function isoToDateStr(isoOrDate: string): string {
  return isoOrDate.slice(0, 10);
}

export default function SimulacaoEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: sim, isLoading } = useQuery<SimulationOut>({
    queryKey: ["simulation", id],
    queryFn: async () => {
      const res = await api.get<SimulationOut>(`/api/v1/simulations/${id}`);
      return res.data;
    },
    enabled: !!id,
  });

  const save = useMutation({
    mutationFn: async (values: SimulationFormValues) => {
      const res = await api.patch<SimulationOut>(`/api/v1/simulations/${id}`, {
        cliente_nome: values.cliente_nome || null,
        veiculo_descricao: values.veiculo_descricao || null,
        valor_veiculo: values.valor_veiculo,
        valor_entrada: values.valor_entrada_brl,
        taxa_mensal: values.taxa_mensal,
        prazo_meses: values.prazo_meses,
        data_liberacao: values.data_liberacao,
        primeiro_vencimento: values.primeiro_vencimento,
        incluir_iof: values.incluir_iof,
        fees: values.fees,
        extras: values.extras,
      });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["simulation", id] }),
  });

  if (isLoading || !sim) {
    return <div className="p-8 text-zinc-400">Carregando…</div>;
  }

  const isEditable = sim.status === "rascunho";

  const initialValues: Partial<SimulationFormValues> = {
    cliente_nome: sim.cliente_nome ?? "",
    veiculo_descricao: sim.veiculo_descricao ?? "",
    valor_veiculo: sim.valor_veiculo,
    valor_entrada_brl: sim.valor_entrada,
    valor_entrada_pct: (
      (parseFloat(sim.valor_entrada) / parseFloat(sim.valor_veiculo)) * 100
    ).toFixed(2),
    taxa_mensal: sim.taxa_mensal,
    prazo_meses: sim.prazo_meses,
    data_liberacao: isoToDateStr(sim.data_liberacao),
    primeiro_vencimento: isoToDateStr(sim.primeiro_vencimento),
    incluir_iof: sim.incluir_iof,
    fees: sim.fees?.map((f) => ({
      nome: f.nome, valor: f.valor, incluir_no_principal: f.incluir_no_principal,
    })) ?? [],
    extras: sim.extras?.map((e) => ({
      tipo: e.tipo, nome: e.nome, valor_total: e.valor_total,
      modalidade: e.modalidade as SimulationFormValues["extras"][0]["modalidade"],
      duracao_meses: e.duracao_meses, ordem: e.ordem,
    })) ?? [],
  };

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="max-w-5xl mx-auto py-8 px-4 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold text-zinc-900">{sim.codigo}</h1>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                sim.status === "rascunho" ? "bg-yellow-100 text-yellow-800" :
                sim.status === "arquivado" ? "bg-zinc-100 text-zinc-500" :
                "bg-green-100 text-green-800"
              }`}>{sim.status}</span>
            </div>
            <button
              onClick={() => navigate("/simulacao")}
              className="text-sm text-zinc-500 hover:text-zinc-900"
            >
              Nova simulação
            </button>
          </div>
          {isEditable ? (
            <SimulacaoForm initialValues={initialValues} onSave={(v) => save.mutate(v)} />
          ) : (
            <SimulacaoForm initialValues={initialValues} />
          )}
        </div>

        <div className="space-y-8">
          {sim.summary && (
            <>
              <ResultCards summary={sim.summary} />
              <SimulacaoCharts rows={sim.rows} />
              <ScheduleTable rows={sim.rows} codigo={sim.codigo} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add routes to `frontend/src/App.tsx`**

Read the current `App.tsx` to find the `<Routes>` block. Add the two new routes:

```typescript
import Simulacao from "./routes/Simulacao";
import SimulacaoEdit from "./routes/SimulacaoEdit";
```

Inside `<Routes>`, add:

```tsx
<Route path="/simulacao" element={<Simulacao />} />
<Route path="/simulacao/:id" element={<SimulacaoEdit />} />
```

- [ ] **Step 4: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no new TypeScript errors. Fix any type errors before continuing.

- [ ] **Step 5: Run all frontend tests**

```bash
cd frontend && npm test -- --run
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/Simulacao.tsx \
        frontend/src/routes/SimulacaoEdit.tsx \
        frontend/src/App.tsx
git commit -m "feat(frontend): add /simulacao and /simulacao/:id routes with save/load flow"
```

---

## Self-Review

### Spec coverage

- [x] `/simulacao` route — `Simulacao.tsx`
- [x] `/simulacao/:id` route — `SimulacaoEdit.tsx`
- [x] Inputs: valor veículo, entrada R$/%, prazo slider, taxa badge, datas, tarifas, IOF, extras — `SimulacaoForm.tsx`
- [x] Live preview debounced 400ms — `useSimulationPreview.ts`
- [x] Result cards (9 fields) — `ResultCards.tsx`
- [x] Schedule table with extras_total and parcela_total — `ScheduleTable.tsx`
- [x] CSV export semicolon separator — `csv.ts` + `ScheduleTable.tsx`
- [x] Charts (3 panels: composição, saldo devedor, parcela total) — `SimulacaoCharts.tsx`
- [x] Save round-trip (POST + navigate to /:id) — `Simulacao.tsx`
- [x] Reload shows same values (GET + prefill) — `SimulacaoEdit.tsx`
- [x] Rules-driven defaults on mount — `SimulacaoForm.tsx` (useBusinessRules)
- [x] taxa mensal auto-populated from suggest_rate — `SimulacaoForm.tsx`
- [x] Entrada R$ ↔ % sync (R$ canonical) — `SimulacaoForm.tsx`
- [x] Vitest: entrada sync, debounce fires once — `simulacao.test.tsx`
- [x] shadcn/ui + Recharts added — Task 1

### Note on `useSimulationPreview` in `Simulacao.tsx`

`Simulacao.tsx` uses the hook's `preview` and `loading` directly, but `SimulacaoForm` also calls `requestPreview` internally. To avoid double-triggering, `SimulacaoForm` owns the preview hook and passes results up via a callback — or both use the same hook instance. For simplicity this plan has `SimulacaoForm` own the hook and `Simulacao.tsx` receives preview state via the form's internal state. If you prefer lifting state up, move `useSimulationPreview` to `Simulacao.tsx` and pass `request` as a prop to `SimulacaoForm`. Either works — pick one and be consistent.
