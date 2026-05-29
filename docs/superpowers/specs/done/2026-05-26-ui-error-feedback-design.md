# Design Spec — UI Error Feedback for Simulation & Vehicle Flows

**Date:** 2026-05-26  
**Status:** Approved (post grill-me review)

---

## Problem Statement

`simular()` in `app/ui/pages/simulacao.py` has no try-except around the `SimulationService.run_and_save()` call. When business-rule validation fails (e.g., minimum down payment not met, grace period too long), `SimulationServiceError` propagates as an unhandled exception — the UI crashes silently with no feedback to the user.

Secondary gaps:
- A placeholder `Vehicle` record is committed to the DB before validation runs; if validation fails, the vehicle is left as an orphan.
- `_cadastrar_e_usar()` in `simulacao.py` and the save handlers in `veiculos.py` have no broad exception catch for unexpected errors (DB crash, network failure, etc.).
- `gerar_pdf()` has a bare `except Exception` but no logging.

---

## Scope

### In scope
- `simular()`: handle `SimulationServiceError` (one toast per message, `timeout=0`) and unexpected `Exception` (generic toast + log).
- `simular()`: fix orphan vehicle via `flush()` instead of `commit()`.
- `simular()`: add `SimulationServiceError` to import block.
- `_cadastrar_e_usar()` in `simulacao.py`: add broad `except Exception` after existing `VehicleServiceError` catch.
- `gerar_pdf()` in `simulacao.py`: add `logger.exception()` to existing `except Exception`; add `from loguru import logger` import.
- `_salvar_fipe()` in `veiculos.py` (~line 341): add broad `except Exception` after `VehicleServiceError`.
- `_salvar_manual()` in `veiculos.py` (~line 380): add broad `except Exception` after `VehicleServiceError`.
- `_save_edit()` in `veiculos.py` (~line 484): add broad `except Exception` after `VehicleServiceError`.

### Out of scope
- Changes to `validators.py`, `simulation_service.py`, or `models.py`.
- FIPE async fetch handlers (`_load_brands_sim`, etc.) — they already use `Err` return values.
- A true NiceGUI framework-level exception hook (not available for client-side WebSocket event handlers).
- New test files — existing service-layer tests cover validation logic; UI wiring is verified by smoke test.

---

## Error Taxonomy

| Exception | Source | UI Response |
|-----------|--------|-------------|
| `SimulationServiceError` | Business-rule validation in `run_and_save()` | One `ui.notify(issue.message, type="negative", timeout=0)` per issue in `e.issues` |
| `VehicleServiceError` | Vehicle CRUD operations | Already handled — `ui.notify(str(e), type="negative")` (unchanged) |
| `Exception` (unexpected) | DB crash, math error, unhandled edge case | `handle_unexpected(exc, context)` → log + `ui.notify("Erro inesperado. Tente novamente.", type="negative")` |

---

## Architecture

### New file: `app/ui/error_handler.py`

```python
from loguru import logger
from nicegui import ui


def handle_unexpected(exc: Exception, context: str) -> None:
    logger.opt(exception=exc).error(f"Unexpected error [{context}]")
    ui.notify("Erro inesperado. Tente novamente.", type="negative")
```

`logger.opt(exception=exc)` is used instead of `logger.exception()` so the traceback is captured explicitly from the exception object — works correctly regardless of whether `sys.exc_info()` is set at the call site.

Imported by `simulacao.py` and `veiculos.py`. One place to change the log level, message format, or add alerting later.

### Why not a NiceGUI global hook?

NiceGUI's `@app.exception_handler` (FastAPI/Starlette) only intercepts HTTP 500 errors on REST routes — it does not intercept exceptions thrown inside client-side WebSocket event handlers (button clicks, etc.). There is no clean NiceGUI 2.x API for a true client-event global hook without relying on undocumented internals.

---

## Per-Callsite Changes

### `app/ui/pages/simulacao.py` — imports

Add to the existing `simulation_service` import:
```python
from app.services.simulation_service import (
    SimulationInputDTO,
    SimulationService,
    SimulationServiceError,  # add this
)
```

Add at top of file:
```python
from loguru import logger
from app.ui.error_handler import handle_unexpected
```

### `app/ui/pages/simulacao.py` — `simular()`

1. **Orphan vehicle fix:** Change `session.commit()` → `session.flush()` for the placeholder Vehicle (~line 391). `flush()` assigns `v.id` without committing; if `run_and_save()` raises before any simulation data is committed, the `with` block exits and the session rolls back the flushed vehicle automatically.

2. **Error handling:** Wrap the entire `simular()` body in:
   ```python
   try:
       ... # existing code
   except SimulationServiceError as e:
       for issue in e.issues:
           ui.notify(issue.message, type="negative", timeout=0)
   except Exception as exc:
       handle_unexpected(exc, "simular")
   ```

### `app/ui/pages/simulacao.py` — `gerar_pdf()`

Add `logger.exception()` inside the existing `except Exception`:
```python
except Exception as exc:
    logger.exception("PDF generation failed")
    ui.notify(f"Erro ao gerar PDF: {exc}", type="negative")
```

### `app/ui/pages/simulacao.py` — `_cadastrar_e_usar()`

Add broad catch after the existing `VehicleServiceError`:
```python
except VehicleServiceError as e:
    ui.notify(str(e), type="negative")
except Exception as exc:
    handle_unexpected(exc, "cadastrar_e_usar")
```

### `app/ui/pages/veiculos.py` — `_salvar_fipe()` (~line 341)

Add broad catch after the existing `VehicleServiceError`:
```python
except VehicleServiceError as e:
    ui.notify(str(e), type="negative")
except Exception as exc:
    handle_unexpected(exc, "veiculos.salvar_fipe")
```

### `app/ui/pages/veiculos.py` — `_salvar_manual()` (~line 380)

Add broad catch after the existing `VehicleServiceError`:
```python
except VehicleServiceError as e:
    ui.notify(str(e), type="negative")
except Exception as exc:
    handle_unexpected(exc, "veiculos.salvar_manual")
```

### `app/ui/pages/veiculos.py` — `_save_edit()` (~line 484)

Add broad catch after the existing `VehicleServiceError`:
```python
except VehicleServiceError as e:
    ui.notify(str(e), type="negative")
    return
except Exception as exc:
    handle_unexpected(exc, "veiculos.save_edit")
```

---

## Testing

No new test files. Existing service-layer and integration tests cover validation logic (`validators.py`, `simulation_service.py`). The `except` wiring is verified by smoke test during implementation.

---

## File Inventory

| File | Action |
|------|--------|
| `app/ui/error_handler.py` | **New** — `handle_unexpected()` |
| `app/ui/pages/simulacao.py` | **Modify** — imports, `simular()`, `gerar_pdf()`, `_cadastrar_e_usar()` |
| `app/ui/pages/veiculos.py` | **Modify** — `_salvar_fipe()`, `_salvar_manual()`, `_save_edit()` |
| `.wolf/anatomy.md` | Update with new `error_handler.py` entry |

---

## Grill-Me Decision Log

| # | Decision | Choice |
|---|----------|--------|
| 1 | Validation toast timeout | `timeout=0` — no auto-dismiss, user must read and close |
| 2 | Logger in `simulacao.py` | Add `from loguru import logger`; keep specific `gerar_pdf()` message |
| 3 | `_save_edit()` scope | In scope — broad except added for consistency |
| 4 | New tests | None — service-layer tests sufficient; UI wiring verified by smoke test |
| 5 | `handle_unexpected` logger call | `logger.opt(exception=exc).error(...)` — explicit, works outside except context |
| 6 | Generic error message | `"Erro inesperado. Tente novamente."` — short and clean |
