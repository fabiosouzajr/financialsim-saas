# Arquitetura

> Este documento e um resumo. A spec completa esta em
> [`docs/superpowers/specs/2026-05-23-finacialsim-design.md`](superpowers/specs/2026-05-23-finacialsim-design.md).

Camadas:

- `app/core/` — calculo financeiro puro
- `app/data/` — SQLAlchemy + Alembic
- `app/integrations/` — FIPE, BACEN, fallback chains
- `app/services/` — orquestracao
- `app/ui/` — NiceGUI

Dependencias: cada camada superior depende apenas das inferiores.

Arquivos importantes:

- `app/main.py` — entry point
- `app/core/price_table.py` — Tabela Price
- `app/core/cet.py` — CET via TIR (bisecao pura Python)
- `app/services/simulation_service.py` — orquestracao da simulacao
- `app/reports/proposta.html` — template do PDF
- `scripts/build_exe.py` — empacotamento PyInstaller
