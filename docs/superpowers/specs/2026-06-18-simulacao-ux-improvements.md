# Simulação UX Improvements — Design Spec

**Date:** 2026-06-18
**Scope:** `frontend/src/routes/simulacao/SimulacaoForm.tsx` only
**Backend changes:** None

---

## 1. Combobox for Cliente and Veículo fields

### Current problem
Both pickers show a persistent list whenever results exist. After selecting an item the list stays open, the selected state is not clearly communicated, and the search always filters by `placa` only (useless for searching by brand or model).

### Target behavior (both pickers)
- The input shows the selected item's display name after selection.
- The dropdown appears **only** while the user is actively typing (`open=true`).
- On item click: record selection, close dropdown (`open=false`).
- On blur: close dropdown after 150 ms delay (so a click on a list item registers before blur fires).
- On focus / typing after a selection is already made: clear the selection, set `open=true`, let the user re-search.

### ClientPicker

No API change — clients already support `?q=` free-text search. Changes:

- Add `open: boolean` state (default `false`).
- Input `onChange`: set `open=true`; if an item was previously selected, clear it so the form field reverts to empty until a new selection is made.
- Item click: call parent `onChange(id)`, write display name into input, `setOpen(false)`.
- Input `onBlur`: `setTimeout(() => setOpen(false), 150)`.
- Dropdown renders only when `open && data?.items.length > 0`.
- Keep `+ Novo Cliente` button.

### VehiclePicker

Backend only accepts `?placa=` filter — not useful for free-text. Strategy: **load up to 100 active vehicles once, filter client-side**.

- Query key `["vehicles-all"]`, fetches `listVehicles({ status: "ativo", limit: 100 })`. `listVehicles` TypeScript signature gains `limit?: number`.
- Client-side filter: case-insensitive match of typed text against `` `${marca} ${modelo} ${ano_modelo} ${placa ?? ""}` ``.
- Same `open` combobox behavior as ClientPicker.
- Keep `+ Novo Veículo` button.
- **Known limitation:** fleets with >100 active vehicles will see a truncated list. Accepted for current scope.

---

## 2. Entrada auto-fill from minimum on vehicle selection

When the user selects a vehicle that carries a FIPE or reference value:

1. Set `valor_veiculo = fipeValue` (existing behavior).
2. If `rules` is loaded: compute `entrada = parseFloat(fipeValue) * parseFloat(rules.entrada_minima_pct)`.
3. Set `valor_entrada_brl = entrada.toFixed(2)`.
4. The existing `useEffect` on `[valorVeiculo, valorEntradaBrl]` automatically re-syncs `valor_entrada_pct`.

**Guards:**
- Only fires when `rules` is loaded and `fipeValue` parses to a valid positive number.
- Does **not** fire on manual edits to `valor_veiculo`; only on vehicle picker selection.
- Does **not** fire in edit mode (vehicle is pre-selected via `initialValues`, not re-selected by the user).

---

## 3. IPVA and Emplacamento always present in new simulations

### Default extras for new simulations

The form `defaultValues.extras` is initialized with:

```
[
  { tipo: "ipva",        nome: "IPVA",        valor_total: "0.00", modalidade: "rateio_ciclico", duracao_meses: 12, ordem: 0 },
  { tipo: "emplacamento", nome: "Emplacamento", valor_total: "0.00", modalidade: "rateio_ciclico", duracao_meses: 12, ordem: 1 },
]
```

`initialValues?.extras`, when provided (edit mode), overrides this default entirely — edit mode shows exactly what was saved. The "always present" rule applies to new simulations only.

### Update valores on vehicle selection

After a vehicle is selected with a known `tipo` (carro / moto / caminhao) and a valid `fipeValue`, and `rules` is loaded:

- Find the `"ipva"` extra by index via `getValues("extras").findIndex(e => e.tipo === "ipva")`.
- Compute `parseFloat(fipeValue) * parseFloat(rules[`ipva_pct_${tipo}`])` → `setValue(`extras.${idx}.valor_total`, computed.toFixed(2))`.
- Find the `"emplacamento"` extra similarly.
- Set `valor_total = rules[`emplacamento_valor_${tipo}`]`.
- If either index is `-1` (user deleted the row), skip gracefully.

### Emplacamento rateio: 12 months

`duracao_meses` for Emplacamento is hard-coded to `12`, same as IPVA. The `rateio_emplacamento_meses_default` business rule (currently 3) is ignored for this field.

### Extras section opens by default

Set `defaultOpen={true}` on the extras `<Collapsible>` — it always has items on new simulations.

### Quick-add buttons

Remove `+ IPVA` and `+ Emplacamento` pill buttons (always pre-seeded now).
Keep `+ Proteção` and `+ Extra customizado`.
The `✕` delete button remains on all rows including IPVA and Emplacamento — they are defaults, not locks.

---

## 4. Visualizar button

### Placement

When `onSave` is provided (new simulation page):
```
[ Visualizar ]  [ Salvar simulação ]
```
Two buttons side by side, full row width split evenly. Visualizar is outline/secondary; Salvar is filled/primary.

When `onSave` is not provided (read-only / view mode):
```
[ Visualizar ]
```
Single button, full width.

### Button behavior

1. On click: compute `toPayload(watchAll)`. Validate form has `valor_veiculo > 0`, `taxa_mensal > 0`, `prazo_meses > 0`. If invalid, show no-op (button stays enabled, nothing opens).
2. Call `requestPreview(payload)`. Button enters loading/disabled state.
3. Watch `preview` state (already in the component). When `preview` becomes non-null, open the modal (`setVisualizarOpen(true)`). Button returns to normal.
4. If the request errors, button returns to normal, modal does not open.

`requestPreview` has a 400 ms debounce; the button loading state covers the full debounce + request time.

### Modal

A `<Dialog>` (`max-w-3xl`, scrollable body, close button in header) containing:

```
<ResultCards summary={preview.summary} loading={false} />
<SimulacaoCharts rows={preview.rows} />
<ScheduleTable rows={preview.rows} />
```

All three components are already in `routes/simulacao/`. Add them as imports to `SimulacaoForm.tsx`.

---

## 5. Out of scope

- `Simulacao.tsx` right-column preview: the parent's `useSimulationPreview()` instance is disconnected from `SimulacaoForm`'s state and is always empty. Pre-existing issue; not touched here.
- `SimulacaoEdit.tsx`: not touched.
- All backend files: not touched.
- `listVehicles` TypeScript signature: gains `limit?: number` — minimal, necessary change.

---

## Files changed

| File | Change |
|------|--------|
| `frontend/src/routes/simulacao/SimulacaoForm.tsx` | All changes above |
| `frontend/src/lib/vehicles.ts` | Add `limit?: number` to `listVehicles` params |
