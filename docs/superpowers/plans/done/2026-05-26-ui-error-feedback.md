# UI Error Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface validation and unexpected errors from the simulation and vehicle flows as user-visible NiceGUI toasts instead of unhandled Python exceptions.

**Architecture:** A new `app/ui/error_handler.py` module provides a shared `handle_unexpected()` utility. All event handlers in `simulacao.py` and `veiculos.py` are wrapped in `try/except` blocks — `SimulationServiceError` gets one toast per validation message (`timeout=0`), unexpected exceptions get a generic toast plus a structured log entry.

**Tech Stack:** Python 3.12, NiceGUI 2.x (`ui.notify`), SQLAlchemy 2.x (session flush/rollback), Loguru (`logger.opt(exception=exc).error`)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/ui/error_handler.py` | **Create** | `handle_unexpected(exc, context)` — log + generic toast |
| `app/ui/pages/simulacao.py` | **Modify** | Add imports; fix `simular()` flush + try-except; add logging to `gerar_pdf()`; add broad except to `_cadastrar_e_usar()` |
| `app/ui/pages/veiculos.py` | **Modify** | Add import; add broad except to `_salvar_fipe()`, `_salvar_manual()`, `_save_edit()` |
| `.wolf/anatomy.md` | **Modify** | Add entry for new `error_handler.py` |

---

## Task 1: Create `app/ui/error_handler.py`

**Files:**
- Create: `app/ui/error_handler.py`

- [ ] **Step 1: Create the file**

```python
"""Shared UI error handler for event callbacks."""

from __future__ import annotations

from loguru import logger
from nicegui import ui


def handle_unexpected(exc: Exception, context: str) -> None:
    logger.opt(exception=exc).error(f"Unexpected error [{context}]")
    ui.notify("Erro inesperado. Tente novamente.", type="negative")
```

`logger.opt(exception=exc)` captures the traceback from the exception object directly — unlike `logger.exception()` it works correctly regardless of whether `sys.exc_info()` is populated at the call site.

- [ ] **Step 2: Verify the file is importable**

```
.venv/Scripts/python.exe -c "from app.ui.error_handler import handle_unexpected; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```
git add app/ui/error_handler.py
git commit -m "feat: add handle_unexpected utility for shared error handling"
```

---

## Task 2: Update `simulacao.py` imports

**Files:**
- Modify: `app/ui/pages/simulacao.py` (import block)

The file currently imports from `simulation_service` but omits `SimulationServiceError`. It also has no `logger` or `handle_unexpected` import.

- [ ] **Step 1: Add `SimulationServiceError` to the existing simulation_service import**

Find this block (around line 14):
```python
from app.services.simulation_service import (
    SimulationInputDTO,
    SimulationService,
)
```

Replace with:
```python
from app.services.simulation_service import (
    SimulationInputDTO,
    SimulationService,
    SimulationServiceError,
)
```

- [ ] **Step 2: Add `logger` and `handle_unexpected` imports**

Find this block (after the stdlib imports, before the NiceGUI import):
```python
from decimal import Decimal

from nicegui import app as ng_app, ui
```

Insert `from loguru import logger` between them:
```python
from decimal import Decimal

from loguru import logger
from nicegui import app as ng_app, ui
```

Then find the `app.ui.*` imports block and add `handle_unexpected`:
```python
from app.ui.components.currency_input import CurrencyInput
from app.ui.components.percent_input import PercentInput
from app.ui.error_handler import handle_unexpected   # add this line
from app.ui.layout import shell
```

- [ ] **Step 3: Verify no import errors**

```
.venv/Scripts/python.exe -c "from app.ui.pages.simulacao import build_simulacao_page; print('ok')"
```

Expected output: `ok`

- [ ] **Step 4: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "feat: add SimulationServiceError, logger, handle_unexpected imports to simulacao"
```

---

## Task 3: Fix `simular()` — orphan vehicle + error handling

**Files:**
- Modify: `app/ui/pages/simulacao.py` — `simular()` function (~lines 376–447)

Two changes: (a) change `session.commit()` → `session.flush()` for the placeholder vehicle so a validation failure rolls it back; (b) wrap the entire function body in try-except.

- [ ] **Step 1: Change `session.commit()` → `session.flush()` for the placeholder vehicle**

Find this block inside `simular()` (the `else` branch that creates a placeholder vehicle, around line 385):
```python
        else:
            # veiculo_id is required FK; placeholder stays hidden via list_active/list_all filters
            v = Vehicle(
                fonte="manual", tipo="carro", marca="Manual", modelo="Veiculo",
                ano_modelo=date.today().year, combustivel="Gasolina",
                valor_referencia=valor_veiculo.value,
            )
            session.add(v)
            session.commit()
```

Change `session.commit()` to `session.flush()`:
```python
        else:
            # veiculo_id is required FK; placeholder stays hidden via list_active/list_all filters
            v = Vehicle(
                fonte="manual", tipo="carro", marca="Manual", modelo="Veiculo",
                ano_modelo=date.today().year, combustivel="Gasolina",
                valor_referencia=valor_veiculo.value,
            )
            session.add(v)
            session.flush()
```

`flush()` assigns `v.id` (required by `run_and_save`) without committing. If validation fails and the `with` block exits via exception, SQLAlchemy rolls back the session and the placeholder vehicle is never persisted.

- [ ] **Step 2: Wrap the full `simular()` body in try-except**

The current `simular()` body is: `with SessionLocal() as session:` block (lines ~377–426) followed by card/chart updates (lines ~428–447). Both must be inside the `try` so that on error the KPI update code (which references `sim` and `rows`) is skipped.

Replace the entire body of `simular()` with:

```python
        def simular() -> None:
            try:
                with SessionLocal() as session:
                    if selected_vehicle_id["id"]:
                        v = session.get(Vehicle, selected_vehicle_id["id"])
                        if v is None:
                            ui.notify("Veículo selecionado não encontrado.", type="negative")
                            return
                    else:
                        v = Vehicle(
                            fonte="manual", tipo="carro", marca="Manual", modelo="Veiculo",
                            ano_modelo=date.today().year, combustivel="Gasolina",
                            valor_referencia=valor_veiculo.value,
                        )
                        session.add(v)
                        session.flush()

                    extras = []
                    prazo_int = int(prazo.value or 48)
                    num_anos = math.ceil(prazo_int / 12)
                    if protecao.value > 0:
                        extras.append(Extra("protecao_veicular", "Plano de protecao",
                                            protecao.value, ExtraModalidade.MENSAL_CONTINUO,
                                            prazo_int, 1))
                    if ipva_total.value > 0:
                        extras.append(Extra("ipva", "IPVA", ipva_total.value * num_anos,
                                            ExtraModalidade.RATEIO_MESES,
                                            prazo_int, 2))
                    if empl_total.value > 0:
                        extras.append(Extra("emplacamento", "Emplacamento", empl_total.value * num_anos,
                                            ExtraModalidade.RATEIO_MESES,
                                            prazo_int, 3))

                    sim = SimulationService(session).run_and_save(SimulationInputDTO(
                        criado_por=user_id, cliente_id=None, veiculo_id=v.id,
                        valor_veiculo=valor_veiculo.value, valor_entrada=valor_entrada.value,
                        prazo_meses=prazo_int, taxa_mensal=taxa.value,
                        data_liberacao=date.fromisoformat(inp_lib.value or date.today().isoformat()),
                        data_primeiro_venc=date.fromisoformat(
                            inp_venc.value or (date.today() + timedelta(days=30)).isoformat()
                        ),
                        incluir_iof=bool(incluir_iof.value), tarifas=[], extras=extras,
                    ))
                    last_sim_id["id"] = sim.id
                    session.refresh(sim)

                    from app.data.models import AmortizationRow
                    rows = (
                        session.query(AmortizationRow).filter_by(simulation_id=sim.id)
                        .order_by(AmortizationRow.numero_parcela).all()
                    )

                card_parcela.set(format_brl(sim.valor_parcela))
                if rows:
                    last_idx = min(12, len(rows) - 1)
                    card_total_apos.set(format_brl(rows[last_idx].parcela_total))
                card_financiado.set(format_brl(sim.valor_financiado))
                total_pago_cliente = (
                    sum((Decimal(str(r.parcela_total)) for r in rows), start=Decimal("0"))
                    + valor_entrada.value
                )
                card_total_pago.set(format_brl(total_pago_cliente))
                card_cet.set(f"{format_pct(sim.cet_mes)} a.m.", f"{format_pct(sim.cet_ano)} a.a.")

                juros = [Decimal(str(r.juros)) for r in rows]
                amort = [Decimal(str(r.amortizacao)) for r in rows]
                extras_arr = [Decimal(str(r.extras_total)) for r in rows]
                saldos = [Decimal(str(r.saldo_devedor)) for r in rows]
                totals = [Decimal(str(r.parcela_total)) for r in rows]
                chart_comp.update_figure(composition_chart(juros, amort, extras_arr))
                chart_saldo.update_figure(saldo_devedor_chart(saldos))
                chart_total.update_figure(parcela_total_chart(totals))

            except SimulationServiceError as e:
                for issue in e.issues:
                    ui.notify(issue.message, type="negative", timeout=0)
            except Exception as exc:
                handle_unexpected(exc, "simular")
```

- [ ] **Step 3: Smoke test — trigger a validation error**

Start the app: `.venv/Scripts/python.exe app/main.py`

In the simulation page:
1. Set Valor do veículo to R$ 50.000
2. Set Entrada to R$ 4.500 (9% — below the 10% minimum)
3. Click Simular

Expected: one `ui.notify` toast appears with the validation message and does **not** auto-dismiss. No traceback in the console.

- [ ] **Step 4: Run existing tests**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all existing tests pass.

- [ ] **Step 5: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "fix: handle SimulationServiceError in simular(); flush placeholder vehicle to prevent orphans"
```

---

## Task 4: Fix `gerar_pdf()` and `_cadastrar_e_usar()` in `simulacao.py`

**Files:**
- Modify: `app/ui/pages/simulacao.py` — `gerar_pdf()` (~line 449) and `_cadastrar_e_usar()` (~line 258)

- [ ] **Step 1: Add `logger.exception()` to `gerar_pdf()`**

Find the `except Exception` clause inside `gerar_pdf()`:
```python
            except Exception as exc:
                ui.notify(f"Erro ao gerar PDF: {exc}", type="negative")
```

Replace with:
```python
            except Exception as exc:
                logger.exception("PDF generation failed")
                ui.notify(f"Erro ao gerar PDF: {exc}", type="negative")
```

- [ ] **Step 2: Add broad except to `_cadastrar_e_usar()`**

Find the `except VehicleServiceError` clause inside `_cadastrar_e_usar()`:
```python
                                    except VehicleServiceError as e:
                                        ui.notify(str(e), type="negative")
```

Add the broad catch immediately after:
```python
                                    except VehicleServiceError as e:
                                        ui.notify(str(e), type="negative")
                                    except Exception as exc:
                                        handle_unexpected(exc, "cadastrar_e_usar")
```

- [ ] **Step 3: Run existing tests**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```
git add app/ui/pages/simulacao.py
git commit -m "fix: add logging to gerar_pdf(); add broad except to _cadastrar_e_usar()"
```

---

## Task 5: Fix `veiculos.py` — three handlers

**Files:**
- Modify: `app/ui/pages/veiculos.py` — import block, `_salvar_fipe()` (~line 341), `_salvar_manual()` (~line 380), `_save_edit()` (~line 484)

- [ ] **Step 1: Add `handle_unexpected` import to `veiculos.py`**

Find the existing import from `vehicle_service`:
```python
from app.services.vehicle_service import VehicleService, VehicleServiceError
```

Add the following line immediately after:
```python
from app.ui.error_handler import handle_unexpected
```

- [ ] **Step 2: Add broad except to `_salvar_fipe()` (~line 359)**

Find the `except VehicleServiceError` clause inside `_salvar_fipe()`:
```python
                                        except VehicleServiceError as e:
                                            ui.notify(str(e), type="negative")
```

Add the broad catch immediately after:
```python
                                        except VehicleServiceError as e:
                                            ui.notify(str(e), type="negative")
                                        except Exception as exc:
                                            handle_unexpected(exc, "veiculos.salvar_fipe")
```

- [ ] **Step 3: Add broad except to `_salvar_manual()` (~line 402)**

Find the `except VehicleServiceError` clause inside `_salvar_manual()`:
```python
                                    except VehicleServiceError as e:
                                        ui.notify(str(e), type="negative")
```

Add the broad catch immediately after:
```python
                                    except VehicleServiceError as e:
                                        ui.notify(str(e), type="negative")
                                    except Exception as exc:
                                        handle_unexpected(exc, "veiculos.salvar_manual")
```

- [ ] **Step 4: Add broad except to `_save_edit()` (~line 487)**

Find the `except VehicleServiceError` clause and the `_select_vehicle` call that follows it:
```python
                    except VehicleServiceError as e:
                        ui.notify(str(e), type="negative")
                        return
                _select_vehicle(vid)
```

Add the broad catch immediately after `VehicleServiceError` (keep `return` to prevent `_select_vehicle` from running on error):
```python
                    except VehicleServiceError as e:
                        ui.notify(str(e), type="negative")
                        return
                    except Exception as exc:
                        handle_unexpected(exc, "veiculos.save_edit")
                        return
                _select_vehicle(vid)
```

- [ ] **Step 5: Verify import works**

```
.venv/Scripts/python.exe -c "from app.ui.pages.veiculos import build_veiculos_page; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Run existing tests**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```
git add app/ui/pages/veiculos.py
git commit -m "fix: add broad except to _salvar_fipe, _salvar_manual, _save_edit in veiculos"
```

---

## Task 6: Update `.wolf/anatomy.md` + final verification

**Files:**
- Modify: `.wolf/anatomy.md`

- [ ] **Step 1: Add entry for `error_handler.py` to anatomy.md**

Find the `## app/ui/` section in `.wolf/anatomy.md`. Add a new bullet under it:

```markdown
- `error_handler.py` — handle_unexpected(exc, context): logs via loguru + shows generic toast. Imported by simulacao.py and veiculos.py event handlers. (~120 tok)
```

- [ ] **Step 2: Full smoke test — happy path**

Start the app: `.venv/Scripts/python.exe app/main.py`

1. Set valid inputs (Valor R$ 50.000, Entrada R$ 10.000, Prazo 48, Taxa 1.89%)
2. Click Simular
3. Verify KPI cards update correctly and no error toasts appear

- [ ] **Step 3: Full smoke test — multiple validation errors**

1. Set Entrada to R$ 4.000 (8% — below 10% minimum)
2. Set data de término 100 dias from hoje (above 90-day carência maximum)
3. Click Simular
4. Expected: **two** separate toasts appear, both `type="negative"`, neither auto-dismisses
5. Fix inputs and simulate again — verify clean success with no leftover toasts

- [ ] **Step 4: Run full test suite one final time**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```
git add .wolf/anatomy.md
git commit -m "docs: update anatomy.md with error_handler.py entry"
```
