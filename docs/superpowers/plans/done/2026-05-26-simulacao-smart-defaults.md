# Simulacao Smart Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cliente selector, smart entrada default with live % indicator, and BACEN taxa pre-fill with reactive polling to `app/ui/pages/simulacao.py`.

**Architecture:** All three features share one DB session at page load (RulesService, IndicatorRepository, ClientService). UI widgets and callbacks are wired inside `content()`. No new files, no new services, no migrations.

**Tech Stack:** NiceGUI 2.x (`ui.select`, `ui.label`, `ui.timer`), SQLAlchemy 2.x sessions, existing `CurrencyInput` / `PercentInput` components, `IndicatorRepository`, `ClientService`, `RulesService`.

---

## File Map

| File | Change |
|------|--------|
| `app/ui/pages/simulacao.py` | All changes — 3 new imports, page-data load block, cliente selector, entrada default + pct_label, _set_valor_veiculo extension, taxa default + bacen_hint + poll timer, _update_pct_label + blur bindings, simular() DTO wire, _loaded_sim restore |

---

### Task 1: Add imports

**Files:**
- Modify: `app/ui/pages/simulacao.py:33-34`

- [ ] **Step 1: Add three imports after line 33**

Current block (lines 33–34):
```python
from app.integrations.factory import build_fipe_chain
from app.services.vehicle_service import VehicleService, VehicleServiceError
```

Replace with:
```python
from app.integrations.factory import build_fipe_chain
from app.services.vehicle_service import VehicleService, VehicleServiceError
from app.data.repositories import IndicatorRepository
from app.services.client_service import ClientService
from app.services.rules_service import RulesService
```

- [ ] **Step 2: Verify the app still imports cleanly**

Run:
```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```
Expected: no output (no ImportError).

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): add imports for IndicatorRepository, ClientService, RulesService"
```

---

### Task 2: Page-data loading block

**Files:**
- Modify: `app/ui/pages/simulacao.py:42-46`

- [ ] **Step 1: Insert DB load block at top of content()**

Current lines 42–46:
```python
        def content() -> None:
            user_id = get_logged_user_id() or 0
            last_sim_id: dict[str, int | None] = {"id": None}
            _actions: dict = {}
            selected_vehicle_id: dict[str, int | None] = {"id": None}
```

Replace with:
```python
        def content() -> None:
            user_id = get_logged_user_id() or 0

            with SessionLocal() as _page_session:
                entrada_minima_pct = Decimal(
                    RulesService(_page_session).get_raw("entrada_minima_pct") or "0.10"
                )
                _taxa_row = IndicatorRepository(_page_session).get_latest("TX_BACEN_VEIC")
                taxa_bacen_val: Decimal | None = _taxa_row.valor if _taxa_row else None
                clients = ClientService(_page_session).find("")

            last_sim_id: dict[str, int | None] = {"id": None}
            _actions: dict = {}
            selected_vehicle_id: dict[str, int | None] = {"id": None}
```

- [ ] **Step 2: Verify import cleanly**

Run:
```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```
Expected: no output.

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): load entrada_minima_pct, taxa_bacen_val, clients at page open"
```

---

### Task 3: Cliente selector widget

**Files:**
- Modify: `app/ui/pages/simulacao.py:102-105`

- [ ] **Step 1: Insert cliente selector before the Veículo label**

Current lines 102–105:
```python
                    # ── Seção Veículo ─────────────────────────────────────────
                    ui.label("Veículo").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest"
                    )
```

Replace with:
```python
                    ui.label("Cliente").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest"
                    )
                    _cliente_options: dict[int, str] = {0: "— sem cliente —"}
                    _cliente_options.update(
                        {c.id: f"{c.nome}  ({c.cpf_cnpj})" for c in clients}
                    )
                    cliente_sel = ui.select(
                        _cliente_options,
                        value=0,
                        label="Cliente",
                        with_input=True,
                    ).classes("w-full")

                    # ── Seção Veículo ─────────────────────────────────────────
                    ui.label("Veículo").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest"
                    )
```

- [ ] **Step 2: Verify import cleanly**

```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): add searchable cliente selector"
```

---

### Task 4: Entrada smart default + pct_label + entrada_modified flag

**Files:**
- Modify: `app/ui/pages/simulacao.py:293-294`

- [ ] **Step 1: Replace valor_entrada line and add pct_label + flag**

Current lines 293–294:
```python
                    valor_veiculo = CurrencyInput("Valor do veículo", Decimal("50000"))
                    valor_entrada = CurrencyInput("Entrada (R$)", Decimal("10000"))
```

Replace with:
```python
                    valor_veiculo = CurrencyInput("Valor do veículo", Decimal("50000"))
                    _entrada_default = (
                        entrada_minima_pct * Decimal("50000")
                    ).quantize(Decimal("0.01"))
                    valor_entrada = CurrencyInput("Entrada (R$)", _entrada_default)
                    pct_label = ui.label("").classes("text-xs text-slate-400")
                    entrada_modified: dict[str, bool] = {"v": False}
```

- [ ] **Step 2: Verify import cleanly**

```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): entrada defaults to entrada_minima_pct x valor_veiculo; add pct_label"
```

---

### Task 5: Extend _set_valor_veiculo to recalculate entrada

**Files:**
- Modify: `app/ui/pages/simulacao.py:162-164`

- [ ] **Step 1: Extend _set_valor_veiculo**

Current lines 162–164:
```python
                    def _set_valor_veiculo(val: Decimal) -> None:
                        valor_veiculo.value = val

```

Replace with:
```python
                    def _set_valor_veiculo(val: Decimal) -> None:
                        valor_veiculo.value = val
                        if not entrada_modified["v"]:
                            valor_entrada.value = (
                                entrada_minima_pct * val
                            ).quantize(Decimal("0.01"))
                            _update_pct_label()

```

`_update_pct_label` is defined later in the callbacks section. This is safe: `_set_valor_veiculo` is only called by user-click events (chip buttons), which fire after the full page renders and all callbacks are defined.

- [ ] **Step 2: Verify import cleanly**

```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): chip click recalculates entrada unless user modified it"
```

---

### Task 6: Taxa BACEN pre-fill + bacen_hint + taxa_modified flag

**Files:**
- Modify: `app/ui/pages/simulacao.py:296`

- [ ] **Step 1: Replace taxa line and add hint + flag**

Current line 296:
```python
                    taxa = PercentInput("Taxa mensal", Decimal("0.0189"))
```

Replace with:
```python
                    _taxa_initial = taxa_bacen_val if taxa_bacen_val is not None else Decimal("0")
                    taxa = PercentInput("Taxa mensal", _taxa_initial)
                    if taxa_bacen_val is not None:
                        bacen_hint = ui.label(
                            f"BACEN TX_VEIC: {taxa_bacen_val * 100:.2f}% a.m."
                        ).classes("text-xs italic text-slate-400")
                    else:
                        bacen_hint = ui.label(
                            "sem dados BACEN — informe manualmente"
                        ).classes("text-xs italic text-amber-500")
                    taxa_modified: dict[str, bool] = {"v": False}
```

- [ ] **Step 2: Verify import cleanly**

```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): taxa defaults to BACEN TX_BACEN_VEIC; add bacen_hint label"
```

---

### Task 7: _update_pct_label, blur bindings, taxa wiring, _poll_bacen + timer

**Files:**
- Modify: `app/ui/pages/simulacao.py:380-381`

- [ ] **Step 1: Insert callback block before simular()**

Current lines 380–381:
```python
            # ── Callbacks (bound after UI built via _actions) ─────────────
            def simular() -> None:
```

Replace with:
```python
            # ── Callbacks (bound after UI built via _actions) ─────────────
            def _update_pct_label() -> None:
                if valor_veiculo.value == 0:
                    pct_label.set_visibility(False)
                    return
                pct_label.set_visibility(True)
                pct = valor_entrada.value / valor_veiculo.value
                pct_label.set_text(
                    f"{pct * 100:.1f}%  (min. {entrada_minima_pct * 100:.0f}%)"
                )
                if pct < entrada_minima_pct:
                    pct_label.classes(remove="text-slate-400", add="text-amber-500")
                else:
                    pct_label.classes(remove="text-amber-500", add="text-slate-400")

            valor_veiculo.input.on("blur", lambda _: _update_pct_label())
            valor_entrada.input.on("blur", lambda _: _update_pct_label())
            valor_entrada.input.on("blur", lambda _: entrada_modified.__setitem__("v", True))
            _update_pct_label()

            taxa.input.on("blur", lambda _: taxa_modified.__setitem__("v", True))

            def _poll_bacen() -> None:
                with SessionLocal() as _s:
                    _row = IndicatorRepository(_s).get_latest("TX_BACEN_VEIC")
                    new_val: Decimal | None = _row.valor if _row else None
                if new_val is None:
                    return
                bacen_hint.set_text(f"BACEN TX_VEIC: {new_val * 100:.2f}% a.m.")
                bacen_hint.style("color: rgb(148 163 184)")
                bacen_hint.update()
                if not taxa_modified["v"]:
                    taxa.value = new_val
                    taxa.update()

            ui.timer(60, _poll_bacen)

            def simular() -> None:
```

Note: `valor_veiculo.input` and `valor_entrada.input` are the underlying `ui.input` elements of `CurrencyInput`. `taxa.input` follows the same pattern for `PercentInput`. If `PercentInput` exposes the element under a different attribute name, check `app/ui/components/percent_input.py` and adjust.

- [ ] **Step 2: Verify import cleanly**

```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): add _update_pct_label, blur bindings, _poll_bacen timer"
```

---

### Task 8: Wire cliente_id in simular() DTO

**Files:**
- Modify: `app/ui/pages/simulacao.py:415-416`

- [ ] **Step 1: Replace hardcoded cliente_id=None**

Current lines 415–416:
```python
                        sim = SimulationService(session).run_and_save(SimulationInputDTO(
                            criado_por=user_id, cliente_id=None, veiculo_id=v.id,
```

Replace with:
```python
                        sim = SimulationService(session).run_and_save(SimulationInputDTO(
                            criado_por=user_id,
                            cliente_id=cliente_sel.value if cliente_sel.value != 0 else None,
                            veiculo_id=v.id,
```

- [ ] **Step 2: Verify import cleanly**

```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```

- [ ] **Step 3: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): wire cliente_sel into SimulationInputDTO.cliente_id"
```

---

### Task 9: Restore cliente_id when loading from /veiculos

**Files:**
- Modify: `app/ui/pages/simulacao.py:57-67` (_loaded_sim dict)
- Modify: `app/ui/pages/simulacao.py:336-348` (pre-fill block)

- [ ] **Step 1: Add cliente_id to _loaded_sim dict**

Current lines 57–67:
```python
                    if _sim:
                        _loaded_sim["sim"] = {
                            "valor_veiculo": _sim.valor_veiculo,
                            "valor_entrada": _sim.valor_entrada,
                            "prazo": _sim.prazo_meses,
                            "taxa": _sim.taxa_juros_mes,
                            "incluir_iof": _sim.incluir_iof,
                            "data_liberacao": _sim.data_liberacao.isoformat(),
                            "data_venc": _sim.data_primeiro_venc.isoformat(),
                            "veiculo_id": _sim.veiculo_id,
                            "codigo": _sim.codigo,
                        }
```

Replace with:
```python
                    if _sim:
                        _loaded_sim["sim"] = {
                            "valor_veiculo": _sim.valor_veiculo,
                            "valor_entrada": _sim.valor_entrada,
                            "prazo": _sim.prazo_meses,
                            "taxa": _sim.taxa_juros_mes,
                            "incluir_iof": _sim.incluir_iof,
                            "data_liberacao": _sim.data_liberacao.isoformat(),
                            "data_venc": _sim.data_primeiro_venc.isoformat(),
                            "veiculo_id": _sim.veiculo_id,
                            "codigo": _sim.codigo,
                            "cliente_id": _sim.cliente_id,
                        }
```

- [ ] **Step 2: Restore cliente_sel in pre-fill block**

Current lines 336–348:
```python
                    if _loaded_sim["sim"]:
                        _d = _loaded_sim["sim"]
                        valor_veiculo.value = _d["valor_veiculo"]
                        valor_entrada.value = _d["valor_entrada"]
                        prazo.set_value(_d["prazo"])
                        taxa.value = _d["taxa"]
                        incluir_iof.set_value(_d["incluir_iof"])
                        inp_lib.set_value(_d["data_liberacao"])
                        inp_venc.set_value(_d["data_venc"])
                        selected_vehicle_id["id"] = _d["veiculo_id"]
                        if _d["veiculo_id"]:
                            _build_picker()
                            _show_chips(_d["veiculo_id"])
```

Replace with:
```python
                    if _loaded_sim["sim"]:
                        _d = _loaded_sim["sim"]
                        valor_veiculo.value = _d["valor_veiculo"]
                        valor_entrada.value = _d["valor_entrada"]
                        prazo.set_value(_d["prazo"])
                        taxa.value = _d["taxa"]
                        incluir_iof.set_value(_d["incluir_iof"])
                        inp_lib.set_value(_d["data_liberacao"])
                        inp_venc.set_value(_d["data_venc"])
                        selected_vehicle_id["id"] = _d["veiculo_id"]
                        if _d["veiculo_id"]:
                            _build_picker()
                            _show_chips(_d["veiculo_id"])
                        cliente_sel.value = _d["cliente_id"] or 0
```

- [ ] **Step 3: Verify import cleanly**

```
.venv\Scripts\python.exe -c "import app.ui.pages.simulacao"
```

- [ ] **Step 4: Final run — open the app and test all three features manually**

```
.venv\Scripts\python.exe app/main.py
```

Check:
1. Cliente selector appears above Veículo, is searchable, defaults to "— sem cliente —"
2. Entrada default shows `entrada_minima_pct × 50000` (e.g. 10% → R$ 5.000,00); pct_label shows "10.0%  (min. 10%)" in slate
3. Editing entrada below minimum turns pct_label amber
4. Clicking FIPE/Ref chip recalculates entrada (if not manually edited)
5. Taxa defaults to BACEN value; hint shows correct text and color
6. After 60s, _poll_bacen fires — hint refreshes, taxa only updates if not manually touched
7. Simular() saves simulation with correct cliente_id
8. Loading a simulation from /veiculos restores the cliente selector

- [ ] **Step 5: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat(simulacao): restore cliente_id when loading simulation from /veiculos"
```

---

## Spec Coverage

| Spec Requirement | Task |
|-----------------|------|
| Synchronous DB session reads all page data before UI builds | 2 |
| `entrada_minima_pct` from RulesService | 2 |
| `TX_BACEN_VEIC` from IndicatorRepository | 2 |
| `clients = ClientService.find("")` | 2 |
| Cliente selector with `with_input=True`, sentinel `0` | 3 |
| `"— sem cliente —"` at key `0` | 3 |
| Entrada default = `entrada_minima_pct × 50000` | 4 |
| `pct_label` below valor_entrada | 4 |
| `entrada_modified` flag | 4 |
| Chip click recalculates entrada (when flag not set) | 5 |
| `_update_pct_label` amber warning below minimum | 7 |
| `_update_pct_label` hidden when valor_veiculo == 0 | 7 |
| Blur bindings on both currency fields | 7 |
| Called once at page render | 7 |
| `entrada_modified` set on blur of valor_entrada | 7 |
| Taxa initial = BACEN value or 0 | 6 |
| `bacen_hint` amber when no data, slate when data | 6 |
| `taxa_modified` flag | 6 |
| `_poll_bacen` 60s timer — updates hint always, taxa only if not modified | 7 |
| `cliente_id` wired in SimulationInputDTO | 8 |
| `cliente_id` added to `_loaded_sim["sim"]` dict | 9 |
| `cliente_sel.value` restored in pre-fill block | 9 |
| `nova_a_partir()` — no change (inherits open form values) | not touched |
