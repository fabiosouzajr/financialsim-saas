# Simulação UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the Simulação form with proper combobox pickers, auto-filled entrada minimum, always-present IPVA/Emplacamento extras, and a Visualizar modal.

**Architecture:** All changes are in `SimulacaoForm.tsx` (one component file) plus a one-line addition to `vehicles.ts`. No backend changes. ClientPicker becomes a controlled combobox with server search; VehiclePicker loads all active vehicles once and filters client-side. IPVA and Emplacamento are pre-seeded in form defaultValues and updated when a vehicle is selected.

**Tech Stack:** React 18, React Hook Form, Zod, TanStack Query, Tailwind CSS, shadcn/ui Dialog

---

## File Map

| File | What changes |
|------|-------------|
| `frontend/src/lib/vehicles.ts` | Add `limit?: number` to `listVehicles` params |
| `frontend/src/routes/simulacao/SimulacaoForm.tsx` | All UX changes — comboboxes, defaults, Visualizar |

---

### Task 1: Add `limit` param to `listVehicles`

**Files:**
- Modify: `frontend/src/lib/vehicles.ts`

- [ ] **Step 1: Add `limit` to the params type and pass it through**

In `frontend/src/lib/vehicles.ts`, replace the `listVehicles` function signature:

```ts
// Before
export async function listVehicles(params?: { status?: string; placa?: string; cursor?: string }): Promise<VehicleListPage> {

// After
export async function listVehicles(params?: { status?: string; placa?: string; cursor?: string; limit?: number }): Promise<VehicleListPage> {
```

The function body (`api.get("/v1/vehicles", { params })`) passes all params to axios unchanged — no other edits needed.

- [ ] **Step 2: Verify TypeScript is happy**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/vehicles.ts
git commit -m "feat(vehicles): add limit param to listVehicles"
```

---

### Task 2: ClientPicker — proper combobox

**Files:**
- Modify: `frontend/src/routes/simulacao/SimulacaoForm.tsx` (the `ClientPicker` function, lines ~128–170)

**Key decisions:**
- Dropdown only renders when `open=true` AND results exist.
- `onMouseDown={e => e.preventDefault()}` on each dropdown item prevents the input blur from firing before the click registers.
- When the user types while a client is already selected, the parent's `client_id` is cleared immediately so the form reflects no selection until a new one is made.
- `enabled: open && q.length > 0` avoids fetching until the user actually types.

- [ ] **Step 1: Rewrite ClientPicker**

Replace the entire `ClientPicker` function in `SimulacaoForm.tsx`:

```tsx
function ClientPicker({ value, onChange, error, onNew }: {
  value: string; onChange: (id: string) => void; error?: string; onNew?: () => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["clients", q],
    queryFn: () => listClients({ q: q || undefined }),
    staleTime: 30_000,
    enabled: open && q.length > 0,
  });
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium">Cliente</label>
        {onNew && (
          <button type="button" onClick={onNew} className="text-xs text-blue-600 hover:text-blue-800">
            + Novo Cliente
          </button>
        )}
      </div>
      <div className="relative">
        <input
          className="w-full border rounded px-3 py-2 text-sm"
          placeholder="Buscar cliente por nome ou CPF..."
          value={q}
          onChange={e => {
            setQ(e.target.value);
            setOpen(true);
            if (value) onChange("");
          }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {open && data?.items && data.items.length > 0 ? (
          <div className="absolute z-10 w-full border rounded-md bg-white shadow-md max-h-40 overflow-y-auto mt-1">
            {data.items.map(c => (
              <button
                key={c.id}
                type="button"
                onMouseDown={e => e.preventDefault()}
                onClick={() => { onChange(c.id); setQ(c.nome); setOpen(false); }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-50 ${value === c.id ? "bg-zinc-100 font-medium" : ""}`}
              >
                {c.nome} <span className="text-zinc-400 text-xs">{c.cpf_cnpj}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Manual smoke test**

Start the dev server (`npm run dev` in `frontend/`). On the Nova Simulação page:
- Type "jo" in Cliente → dropdown appears with matching clients.
- Click a client → input shows client name, dropdown closes.
- Type again → dropdown re-opens, `client_id` cleared.
- Tab away without selecting → dropdown closes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoForm.tsx
git commit -m "feat(simulacao): ClientPicker combobox — open/close on type/select"
```

---

### Task 3: VehiclePicker — client-side filter combobox

**Files:**
- Modify: `frontend/src/routes/simulacao/SimulacaoForm.tsx` (the `VehiclePicker` function, lines ~172–223)

**Key decisions:**
- Load all active vehicles once with `queryKey: ["vehicles-all"]` and `limit: 100`. React Query caches this for 5 minutes.
- Filter client-side against `marca + modelo + ano_modelo + placa`.
- `useMemo` keeps the filter from re-running on every render.
- Add `useMemo` to the React import at the top of the file.

- [ ] **Step 1: Add `useMemo` to React import**

At the top of `SimulacaoForm.tsx`, the import is:
```tsx
import { useEffect, useState } from "react";
```

Change to:
```tsx
import { useEffect, useMemo, useState } from "react";
```

- [ ] **Step 2: Rewrite VehiclePicker**

Replace the entire `VehiclePicker` function:

```tsx
function VehiclePicker({ value, onChange, error, onNew }: {
  value: string;
  onChange: (id: string, fipeValue: string | null, tipo: string | null) => void;
  error?: string;
  onNew?: () => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["vehicles-all"],
    queryFn: () => listVehicles({ status: "ativo", limit: 100 }),
    staleTime: 5 * 60_000,
  });

  const filtered = useMemo(() => {
    if (!data?.items || !q.trim()) return [];
    const term = q.trim().toLowerCase();
    return data.items.filter(v =>
      `${v.marca} ${v.modelo} ${v.ano_modelo} ${v.placa ?? ""}`.toLowerCase().includes(term)
    );
  }, [data, q]);

  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium">Veículo</label>
        {onNew && (
          <button type="button" onClick={onNew} className="text-xs text-blue-600 hover:text-blue-800">
            + Novo Veículo
          </button>
        )}
      </div>
      <div className="relative">
        <input
          className="w-full border rounded px-3 py-2 text-sm"
          placeholder="Buscar veículo por marca, modelo ou placa..."
          value={q}
          onChange={e => {
            setQ(e.target.value);
            setOpen(true);
            if (value) onChange("", null, null);
          }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {open && filtered.length > 0 ? (
          <div className="absolute z-10 w-full border rounded-md bg-white shadow-md max-h-40 overflow-y-auto mt-1">
            {filtered.map(v => (
              <button
                key={v.id}
                type="button"
                onMouseDown={e => e.preventDefault()}
                onClick={() => {
                  onChange(v.id, v.valor_fipe ?? v.valor_referencia ?? null, v.tipo);
                  setQ(`${v.marca} ${v.modelo} ${v.ano_modelo}`);
                  setOpen(false);
                }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-50 ${value === v.id ? "bg-zinc-100 font-medium" : ""}`}
              >
                {v.marca} {v.modelo} {v.ano_modelo}
                {v.placa && <span className="text-zinc-400 text-xs ml-1">· {v.placa}</span>}
                {(v.valor_fipe ?? v.valor_referencia) && (
                  <span className="text-zinc-400 text-xs ml-1">
                    · R$ {Number(v.valor_fipe ?? v.valor_referencia).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                  </span>
                )}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Manual smoke test**

On the Nova Simulação page:
- Type "toyo" in Veículo → dropdown shows matching vehicles by marca.
- Type a partial plate like "ABC" → matches vehicles with that plate.
- Select a vehicle → input shows `Marca Modelo Ano`, dropdown closes.
- Type again → re-opens, `vehicle_id` cleared.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoForm.tsx
git commit -m "feat(simulacao): VehiclePicker combobox — client-side filter across marca/modelo/placa"
```

---

### Task 4: Default IPVA and Emplacamento in form extras

**Files:**
- Modify: `frontend/src/routes/simulacao/SimulacaoForm.tsx` (the `SimulacaoForm` component)

**Key decisions:**
- IPVA and Emplacamento are in `defaultValues.extras`. When `initialValues` is provided (edit mode), its `extras` property overrides the defaults entirely — edit mode shows exactly what was saved.
- `duracao_meses: 12` for both (spec decision — ignores `rateio_emplacamento_meses_default`).
- Extras `<Collapsible>` opens by default (`defaultOpen`).
- Remove `+ IPVA` and `+ Emplacamento` pill buttons from the quick-add row.

- [ ] **Step 1: Update `defaultValues.extras`**

In the `useForm` call inside `SimulacaoForm`, find:

```tsx
extras: [],
...initialValues,
```

Replace with:

```tsx
extras: [
  { tipo: "ipva", nome: "IPVA", valor_total: "0.00", modalidade: "rateio_ciclico" as const, duracao_meses: 12, ordem: 0 },
  { tipo: "emplacamento", nome: "Emplacamento", valor_total: "0.00", modalidade: "rateio_ciclico" as const, duracao_meses: 12, ordem: 1 },
],
...initialValues,
```

(The `...initialValues` spread at the end still overrides `extras` when `initialValues.extras` is provided, which is the correct edit-mode behavior.)

- [ ] **Step 2: Set extras Collapsible to defaultOpen**

Find the extras `<Collapsible>` opening tag:

```tsx
<Collapsible>
  <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-zinc-700 hover:text-zinc-900">
    <span>Extras</span>
```

Change to:

```tsx
<Collapsible defaultOpen>
  <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-zinc-700 hover:text-zinc-900">
    <span>Extras</span>
```

- [ ] **Step 3: Remove IPVA and Emplacamento quick-add buttons**

Find the quick-add pill button row inside `<CollapsibleContent>`. It currently has three buttons: `+ Proteção`, `+ IPVA`, `+ Emplacamento`. Remove the IPVA and Emplacamento buttons, keep Proteção:

```tsx
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
</div>
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Manual smoke test**

Open Nova Simulação:
- Extras section is open by default showing IPVA (R$ 0,00, rateio cíclico, 12 meses) and Emplacamento (R$ 0,00, rateio cíclico, 12 meses).
- Quick-add row shows only `+ Proteção` and `+ Extra customizado`.
- Clicking ✕ on IPVA removes it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoForm.tsx
git commit -m "feat(simulacao): IPVA and Emplacamento pre-seeded in extras defaults"
```

---

### Task 5: Vehicle selection — update IPVA/Emplacamento values and auto-fill entrada

**Files:**
- Modify: `frontend/src/routes/simulacao/SimulacaoForm.tsx` (the `VehiclePicker` `onChange` handler in `SimulacaoForm`, and the `useForm` destructure)

**Key decisions:**
- `getValues` from `useForm` is needed to read current extras indexes at selection time.
- IPVA and Emplacamento updates use `findIndex` — if the user deleted a row, `findIndex` returns `-1` and we skip gracefully.
- Entrada minimum fires only when `fipeValue` is a valid positive number and `rules` is loaded.

- [ ] **Step 1: Add `getValues` to the `useForm` destructure**

Find:
```tsx
const { register, watch, setValue, control, handleSubmit, formState } =
  useForm<SimulationFormValues>({
```

Add `getValues`:
```tsx
const { register, watch, setValue, getValues, control, handleSubmit, formState } =
  useForm<SimulationFormValues>({
```

- [ ] **Step 2: Extend the VehiclePicker onChange handler**

In the JSX of `SimulacaoForm`, find the `<VehiclePicker>` usage:

```tsx
<VehiclePicker
  value={watch("vehicle_id") ?? ""}
  onChange={(id, fipeValue, tipo) => {
    setValue("vehicle_id", id);
    if (fipeValue) setValue("valor_veiculo", fipeValue);
    setSelectedVehicle({ fipeValue: fipeValue ?? null, tipo: tipo ?? null });
  }}
  onNew={() => setVehicleModalOpen(true)}
/>
```

Replace the `onChange` handler with:

```tsx
onChange={(id, fipeValue, tipo) => {
  setValue("vehicle_id", id);
  if (fipeValue) {
    setValue("valor_veiculo", fipeValue);

    // Auto-fill entrada minimum
    if (rules) {
      const minPct = parseFloat(rules.entrada_minima_pct);
      const vv = parseFloat(fipeValue);
      if (!isNaN(minPct) && !isNaN(vv) && vv > 0) {
        setValue("valor_entrada_brl", (vv * minPct).toFixed(2));
      }
    }

    // Update IPVA and Emplacamento valores
    if (rules && isValidTipo(tipo)) {
      const currentExtras = getValues("extras");

      const ipvaIdx = currentExtras.findIndex(e => e.tipo === "ipva");
      if (ipvaIdx >= 0) {
        const ipvaPct = parseFloat(rules[`ipva_pct_${tipo}`]);
        const vv = parseFloat(fipeValue);
        if (!isNaN(ipvaPct) && !isNaN(vv)) {
          setValue(`extras.${ipvaIdx}.valor_total`, (vv * ipvaPct).toFixed(2));
        }
      }

      const emplacIdx = currentExtras.findIndex(e => e.tipo === "emplacamento");
      if (emplacIdx >= 0) {
        setValue(`extras.${emplacIdx}.valor_total`, rules[`emplacamento_valor_${tipo}`]);
      }
    }
  }
  setSelectedVehicle({ fipeValue: fipeValue ?? null, tipo: tipo ?? null });
}}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. (The `rules[`ipva_pct_${tipo}`]` access pattern already existed in the original code, TypeScript is fine with it given `isValidTipo` narrowing.)

- [ ] **Step 4: Manual smoke test**

On Nova Simulação:
- Select a "carro" vehicle with a known FIPE value (e.g., R$ 100.000,00).
- Verify `Entrada R$` auto-populates with `R$ valor_veiculo × entrada_minima_pct` (e.g., 20% → R$ 20.000,00).
- Verify IPVA row updates from R$ 0,00 to the computed value (e.g., 2% of R$ 100.000 → R$ 2.000,00).
- Verify Emplacamento row updates to the configured flat value for "carro".
- Select a different vehicle → values update.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoForm.tsx
git commit -m "feat(simulacao): auto-fill entrada and update IPVA/Emplacamento on vehicle select"
```

---

### Task 6: Visualizar button and modal

**Files:**
- Modify: `frontend/src/routes/simulacao/SimulacaoForm.tsx`

**Key decisions:**
- `pendingVisualize` state: set to `true` when button is clicked. A `useEffect` watches `[preview, pendingVisualize]`; when `preview` arrives while `pendingVisualize=true`, it opens the modal and resets the flag.
- If `preview` already exists when button is clicked (from auto-preview), open the modal immediately.
- Imports `ResultCards`, `SimulacaoCharts`, `ScheduleTable` from the same directory.
- Button layout: `[Visualizar] [Salvar simulação]` side by side when `onSave` is provided; `[Visualizar]` full-width otherwise.

- [ ] **Step 1: Add imports for the preview components**

At the top of `SimulacaoForm.tsx`, after the existing imports, add:

```tsx
import { ResultCards } from "./ResultCards";
import { SimulacaoCharts } from "./SimulacaoCharts";
import { ScheduleTable } from "./ScheduleTable";
```

- [ ] **Step 2: Add `pendingVisualize` and `visualizarOpen` state**

Inside `SimulacaoForm`, after the existing `useState` declarations (e.g., after `vehicleModalOpen`):

```tsx
const [pendingVisualize, setPendingVisualize] = useState(false);
const [visualizarOpen, setVisualizarOpen] = useState(false);
```

- [ ] **Step 3: Add the useEffect to open modal when preview arrives**

After the existing `useEffect` blocks (before `handlePctBlur`), add:

```tsx
useEffect(() => {
  if (pendingVisualize && preview) {
    setVisualizarOpen(true);
    setPendingVisualize(false);
  }
}, [preview, pendingVisualize]);
```

- [ ] **Step 4: Replace the submit button section with the two-button layout**

Find the existing submit button:

```tsx
{onSave && (
  <button
    type="submit"
    className="w-full bg-zinc-900 text-white rounded py-2.5 text-sm font-medium hover:bg-zinc-700"
    disabled={formState.isSubmitting}
  >
    Salvar simulação
  </button>
)}
```

Replace with:

```tsx
<div className="flex gap-2">
  <button
    type="button"
    disabled={pendingVisualize}
    onClick={() => {
      const vv = parseFloat(watch("valor_veiculo"));
      const taxa = parseFloat(watch("taxa_mensal"));
      const prazo = watch("prazo_meses");
      if (!(vv > 0 && taxa > 0 && prazo > 0)) return;
      if (preview) {
        setVisualizarOpen(true);
      } else {
        setPendingVisualize(true);
        requestPreview(toPayload(watchAll));
      }
    }}
    className={`border border-zinc-300 text-zinc-700 rounded py-2.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 ${onSave ? "flex-1" : "w-full"}`}
  >
    {pendingVisualize ? "Calculando..." : "Visualizar"}
  </button>
  {onSave && (
    <button
      type="submit"
      className="flex-1 bg-zinc-900 text-white rounded py-2.5 text-sm font-medium hover:bg-zinc-700"
      disabled={formState.isSubmitting}
    >
      Salvar simulação
    </button>
  )}
</div>
```

- [ ] **Step 5: Add the Visualizar Dialog**

After the two VehicleModal/ClientModal Dialog blocks (near the bottom of the `<form>`), add:

```tsx
<Dialog open={visualizarOpen} onOpenChange={setVisualizarOpen}>
  <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto bg-white text-gray-900">
    <DialogHeader>
      <DialogTitle className="text-gray-900 text-lg font-semibold">Simulação</DialogTitle>
    </DialogHeader>
    {preview ? (
      <div className="space-y-6">
        <ResultCards summary={preview.summary} loading={false} />
        <SimulacaoCharts rows={preview.rows} />
        <ScheduleTable rows={preview.rows} />
      </div>
    ) : (
      <div className="text-sm text-zinc-400 text-center py-8">Calculando...</div>
    )}
  </DialogContent>
</Dialog>
```

- [ ] **Step 6: Remove the now-unused hidden preview spans**

Find and delete:

```tsx
{/* Hidden preview state for parent usage */}
{previewLoading && <span style={{ display: "none" }}>preview-loading</span>}
{preview && <span style={{ display: "none" }}>preview-ready</span>}
```

- [ ] **Step 7: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 8: Manual smoke test**

On Nova Simulação:
- Fill in valor_veiculo, select a vehicle (triggers auto-preview in background).
- Click "Visualizar" → if preview already exists, modal opens immediately with ResultCards + chart + table.
- Click "Visualizar" before any auto-preview fires (clear valor_veiculo, re-enter it, click quickly) → button shows "Calculando...", modal opens when data arrives.
- Click "Visualizar" with no values → nothing happens (button is a no-op).
- Modal has a close button (shadcn Dialog default) and is scrollable for long schedules.
- "Salvar simulação" button still works independently.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoForm.tsx
git commit -m "feat(simulacao): Visualizar button opens preview modal without saving"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Covered by |
|---|---|
| ClientPicker combobox (open/close, blur delay, clear on type) | Task 2 |
| VehiclePicker client-side filter, limit=100 | Tasks 1 + 3 |
| Entrada auto-fill on vehicle select | Task 5 |
| IPVA + Emplacamento in defaultValues | Task 4 |
| Vehicle select updates IPVA/Emplacamento valores | Task 5 |
| Emplacamento duracao_meses = 12 | Task 4 |
| Extras defaultOpen | Task 4 |
| Remove IPVA/Emplacamento quick-add buttons | Task 4 |
| Visualizar button (wait for data, then open) | Task 6 |
| Visualizar modal content | Task 6 |
| `vehicles.ts` limit param | Task 1 |

**Placeholder scan:** None found. All steps have concrete code.

**Type consistency:**
- `getValues` added in Task 5 Step 1 — used in Step 2. ✓
- `pendingVisualize` added in Task 6 Step 2 — used in Steps 3, 4. ✓
- `visualizarOpen` added in Task 6 Step 2 — used in Steps 4, 5. ✓
- `ResultCards`, `SimulacaoCharts`, `ScheduleTable` imported in Step 1 — used in Step 5. ✓
- `isValidTipo` already defined in the file — reused in Task 5. ✓
- `requestPreview` already available from `useSimulationPreview()` — used in Task 6. ✓
