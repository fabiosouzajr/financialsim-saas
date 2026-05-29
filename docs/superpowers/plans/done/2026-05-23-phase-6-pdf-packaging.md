# Phase 6 — PDF, empacotamento e instalação

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`.

**Goal:** Finalize the PDF de proposta (WeasyPrint), build distributable installers (Windows NSIS, Linux AppImage, macOS .app/DMG), write install scripts, set up GitHub Actions release workflow, and write end-user documentation.

**Architecture:** PDF rendering lives in `app/reports/proposta.html` (Jinja2 template) consumed by `proposal_service.render_pdf()`. PyInstaller specs live in `scripts/`. Install scripts under `scripts/install_*`. CI under `.github/workflows/`.

**Tech Stack:** WeasyPrint, Jinja2, PyInstaller, NSIS, AppImage tooling, `create-dmg`, GitHub Actions.

**Dependencies:** Phases 1–5 complete.

---

## Task 1: PDF template and `proposal_service.render_pdf`

**Files:**

- Create: `app/reports/__init__.py` (empty)
- Create: `app/reports/proposta.html`
- Create: `app/reports/proposta.css`
- Modify: `app/services/proposal_service.py` (add `render_pdf`)
- Create: `tests/unit/services/test_proposal_render.py`

- [ ] **Step 1: Write `proposta.css`**

`app/reports/proposta.css`:

```css
@page { size: A4; margin: 1.5cm; }
body { font-family: Inter, "Segoe UI", sans-serif; color: #1A2233; font-size: 11pt; }
h1, h2, h3 { color: #1565C0; margin: 0.6em 0 0.3em; }
h1 { font-size: 18pt; }
h2 { font-size: 14pt; }
.kpi-row { display: flex; gap: 0.8em; margin: 0.8em 0; }
.kpi { flex: 1; background: #F5F7FB; padding: 0.6em 0.8em; border-radius: 6px; }
.kpi .label { font-size: 9pt; color: #6B7785; }
.kpi .value { font-size: 14pt; font-weight: 700; color: #1565C0; }
table { width: 100%; border-collapse: collapse; margin: 0.6em 0; font-size: 10pt; }
th, td { padding: 0.35em 0.5em; border-bottom: 1px solid #DCE2EA; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { background: #F5F7FB; color: #1A2233; font-weight: 600; }
tr.subtotal td { font-weight: 700; }
.note { font-size: 9pt; color: #6B7785; margin-top: 0.6em; }
.signatures { display: flex; justify-content: space-between; margin-top: 2.5em; }
.signatures div { width: 45%; border-top: 1px solid #1A2233; padding-top: 0.4em; text-align: center; font-size: 9pt; }
.extra-row { background: #FFF7E6; }
```

- [ ] **Step 2: Write `proposta.html` (Jinja2)**

`app/reports/proposta.html`:

```html
<!doctype html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Proposta {{ proposal.codigo }}</title></head>
<body>
  <h1>{{ loja.nome }} — Proposta de financiamento</h1>
  <p>
    Proposta <strong>{{ proposal.codigo }}</strong> emitida em {{ proposal.gerado_em_br }} —
    validade {{ proposal.validade_dias }} dias.
  </p>

  <h2>Cliente</h2>
  <p>
    {{ cliente.nome }} —
    {{ "CPF" if cliente.tipo == "PF" else "CNPJ" }}: {{ cliente.cpf_cnpj_fmt }}
    {% if cliente.telefone %}— Tel.: {{ cliente.telefone }}{% endif %}
  </p>

  <h2>Veículo</h2>
  <p>
    {{ veiculo.marca }} {{ veiculo.modelo }} ({{ veiculo.ano_modelo }})
    {% if veiculo.codigo_fipe %} — FIPE {{ veiculo.codigo_fipe }} ref. {{ veiculo.mes_referencia_fipe }}{% endif %}
    — Valor de venda: {{ sim.valor_veiculo_brl }}
  </p>

  <h2>Condições do financiamento</h2>
  <div class="kpi-row">
    <div class="kpi"><div class="label">Valor financiado</div><div class="value">{{ sim.valor_financiado_brl }}</div></div>
    <div class="kpi"><div class="label">Entrada</div><div class="value">{{ sim.valor_entrada_brl }} ({{ sim.pct_entrada_pct }})</div></div>
    <div class="kpi"><div class="label">Prazo</div><div class="value">{{ sim.prazo_meses }} meses</div></div>
  </div>
  <div class="kpi-row">
    <div class="kpi"><div class="label">Taxa a.m.</div><div class="value">{{ sim.taxa_juros_mes_pct }}</div></div>
    <div class="kpi"><div class="label">Taxa a.a.</div><div class="value">{{ sim.taxa_juros_ano_pct }}</div></div>
    <div class="kpi"><div class="label">CET a.m.</div><div class="value">{{ sim.cet_mes_pct }}</div></div>
    <div class="kpi"><div class="label">CET a.a.</div><div class="value">{{ sim.cet_ano_pct }}</div></div>
  </div>
  <p>
    IOF: {% if sim.incluir_iof %}{{ sim.iof_total_brl }}{% else %}<em>não incluído</em>{% endif %}
    — Tarifas: {{ sim.tarifas_total_brl }}
  </p>

  {% if extras %}
  <h2>Custos adicionais mensais</h2>
  <table>
    <thead><tr><th>Item</th><th>Modalidade</th><th>Valor total</th><th>Duração</th><th>Por parcela</th></tr></thead>
    <tbody>
      {% for e in extras %}
      <tr>
        <td>{{ e.nome }}</td>
        <td>{{ e.modalidade_label }}</td>
        <td>{{ e.valor_total_brl }}</td>
        <td>{{ e.duracao_meses }} parcelas</td>
        <td>{{ e.valor_por_parcela_brl }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}

  <h2>Resumo financeiro</h2>
  <div class="kpi-row">
    <div class="kpi"><div class="label">Parcela financiamento</div><div class="value">{{ sim.valor_parcela_brl }}</div></div>
    <div class="kpi"><div class="label">Parcela total 1º ano</div><div class="value">{{ sim.parcela_total_1ano_brl }}</div></div>
    <div class="kpi"><div class="label">Parcela total após rateio</div><div class="value">{{ sim.parcela_total_apos_brl }}</div></div>
  </div>
  <div class="kpi-row">
    <div class="kpi"><div class="label">Total pago financiamento</div><div class="value">{{ sim.total_pago_brl }}</div></div>
    <div class="kpi"><div class="label">Total juros</div><div class="value">{{ sim.total_juros_brl }} ({{ sim.pct_juros_pct }})</div></div>
    <div class="kpi"><div class="label">Total pago pelo cliente</div><div class="value">{{ sim.total_pago_cliente_brl }}</div></div>
  </div>

  <h2>Cronograma de amortização</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Vencimento</th><th>Juros</th><th>Amortização</th><th>Parcela</th><th>Extras</th><th>Parcela total</th><th>Saldo devedor</th></tr>
    </thead>
    <tbody>
      {% for r in cronograma %}
      <tr {% if r.extras_brl != "R$ 0,00" %}class="extra-row"{% endif %}>
        <td>{{ r.numero }}</td><td>{{ r.venc }}</td>
        <td>{{ r.juros_brl }}</td><td>{{ r.amortizacao_brl }}</td>
        <td>{{ r.parcela_brl }}</td><td>{{ r.extras_brl }}</td>
        <td><strong>{{ r.parcela_total_brl }}</strong></td>
        <td>{{ r.saldo_brl }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <p class="note">
    Custos adicionais (proteção veicular, IPVA, emplacamento) não compõem o CET por
    serem despesas externas ao crédito.
  </p>

  <div class="signatures">
    <div>Cliente</div>
    <div>Vendedor — {{ vendedor.nome }}</div>
  </div>
</body>
</html>
```

- [ ] **Step 3: Write the failing test**

`tests/unit/services/test_proposal_render.py`:

```python
import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.auth_service import AuthService
from app.services.client_service import ClientService
from app.services.proposal_service import ProposalService
from app.services.simulation_service import SimulationInputDTO, SimulationService


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def test_render_pdf_creates_file(session):
    user = AuthService(session).create_user("v", "123456", "vendedor")
    client = ClientService(session).create_pf(nome="Maria", cpf="52998224725", criado_por=user.id)
    from app.data.models import Vehicle
    v = Vehicle(fonte="manual", tipo="carro", marca="F", modelo="M",
                ano_modelo=2024, combustivel="G", valor_referencia=Decimal("50000"))
    session.add(v); session.commit()

    sim = SimulationService(session).run_and_save(SimulationInputDTO(
        criado_por=user.id, cliente_id=client.id, veiculo_id=v.id,
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        prazo_meses=24, taxa_mensal=Decimal("0.015"),
        data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
        incluir_iof=True, tarifas=[], extras=[],
    ))
    proposal = ProposalService(session).create(sim.id, gerado_por=user.id)

    with tempfile.TemporaryDirectory() as out_dir:
        out_path = Path(out_dir) / "out.pdf"
        ProposalService(session).render_pdf(proposal.id, out_path,
                                            loja={"nome": "Loja Demo"},
                                            vendedor={"nome": "Joao"})
        assert out_path.exists()
        assert out_path.stat().st_size > 1000  # non-empty
        with open(out_path, "rb") as f:
            header = f.read(4)
        assert header == b"%PDF"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/unit/services/test_proposal_render.py -v`
Expected: FAIL — `render_pdf` not defined.

- [ ] **Step 5: Add `render_pdf` to `proposal_service.py`**

Append to `app/services/proposal_service.py`:

```python
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

from app.utils.br_format import format_brl, format_date_br, format_pct


_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
_jinja_env = Environment(loader=FileSystemLoader(str(_REPORTS_DIR)), autoescape=True)


_MODALIDADE_LABEL = {
    "mensal_continuo": "Mensal contínuo",
    "rateio_meses": "Rateio em meses",
    "unico_inicial": "Único (1ª parcela)",
}


def _format_cpf_cnpj(s: str, tipo: str) -> str:
    if tipo == "PF" and len(s) == 11:
        return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"
    if tipo == "PJ" and len(s) == 14:
        return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"
    return s


class _RenderHelper:
    """Augmentation methods on ProposalService - kept in same module for simplicity."""


def _build_template_context(snap: dict, loja: dict, vendedor: dict, gerado_em: datetime, validade: int) -> dict:
    sim = snap["simulation"]
    rows = snap["cronograma"]
    extras = snap["extras"]
    cliente = snap["cliente"]
    veiculo = snap["veiculo"]

    parcela_total_1ano = rows[0]["parcela_total"] if rows else "0"
    last_idx = min(12, len(rows) - 1) if rows else 0
    parcela_total_apos = rows[last_idx]["parcela_total"] if rows else "0"

    def _D(s):  # str -> Decimal
        from decimal import Decimal
        return Decimal(s)

    return {
        "loja": loja,
        "vendedor": vendedor,
        "proposal": {
            "codigo": snap.get("proposta", {}).get("codigo", "PROP-XXX"),
            "gerado_em_br": format_date_br(gerado_em.date()),
            "validade_dias": validade,
        },
        "cliente": {
            **cliente,
            "cpf_cnpj_fmt": _format_cpf_cnpj(cliente["cpf_cnpj"], cliente["tipo"]),
        },
        "veiculo": veiculo,
        "sim": {
            **sim,
            "valor_veiculo_brl": format_brl(_D(sim["valor_veiculo"])),
            "valor_entrada_brl": format_brl(_D(sim["valor_entrada"])),
            "pct_entrada_pct": format_pct(_D(sim["pct_entrada"])),
            "valor_financiado_brl": format_brl(_D(sim["valor_financiado"])),
            "valor_parcela_brl": format_brl(_D(sim["valor_parcela"])),
            "total_pago_brl": format_brl(_D(sim["total_pago"])),
            "total_juros_brl": format_brl(_D(sim["total_juros"])),
            "iof_total_brl": format_brl(_D(sim["iof_total"])),
            "tarifas_total_brl": format_brl(_D(sim["tarifas_total"])),
            "taxa_juros_mes_pct": format_pct(_D(sim["taxa_juros_mes"]), 4),
            "taxa_juros_ano_pct": format_pct(_D(sim["taxa_juros_ano"]), 2),
            "cet_mes_pct": format_pct(_D(sim["cet_mes"]), 4),
            "cet_ano_pct": format_pct(_D(sim["cet_ano"]), 2),
            "pct_juros_pct": format_pct(_D(sim["pct_juros"]), 2),
            "parcela_total_1ano_brl": format_brl(_D(parcela_total_1ano)),
            "parcela_total_apos_brl": format_brl(_D(parcela_total_apos)),
            "total_pago_cliente_brl": format_brl(
                _D(sim["total_pago"]) + _D(sim["extras_total_acumulado"])
            ),
        },
        "extras": [
            {
                **e,
                "modalidade_label": _MODALIDADE_LABEL.get(e["modalidade"], e["modalidade"]),
                "valor_total_brl": format_brl(_D(e["valor_total"])),
                "valor_por_parcela_brl": format_brl(_D(e["valor_por_parcela"])),
            }
            for e in extras
        ],
        "cronograma": [
            {
                "numero": r["numero"],
                "venc": format_date_br(date.fromisoformat(r["venc"])),
                "juros_brl": format_brl(_D(r["juros"])),
                "amortizacao_brl": format_brl(_D(r["amortizacao"])),
                "parcela_brl": format_brl(_D(r["parcela"])),
                "extras_brl": format_brl(_D(r["extras"])),
                "parcela_total_brl": format_brl(_D(r["parcela_total"])),
                "saldo_brl": format_brl(_D(r["saldo"])),
            }
            for r in rows
        ],
    }


# Monkey-patch / extend ProposalService:

class _ExtendedProposalService:
    """Defined as a mixin pattern - the actual ProposalService gets the method below."""


def render_pdf(self, proposal_id: int, output_path: Path,
               loja: dict | None = None, vendedor: dict | None = None) -> Path:
    from app.data.models import Proposal
    proposal = self.session.get(Proposal, proposal_id)
    if proposal is None:
        raise ValueError("proposal not found")
    snap = json.loads(proposal.snapshot_json)
    snap.setdefault("proposta", {})["codigo"] = proposal.codigo

    ctx = _build_template_context(
        snap,
        loja=loja or {"nome": "Loja"},
        vendedor=vendedor or {"nome": "Vendedor"},
        gerado_em=proposal.gerado_em,
        validade=proposal.validade_dias,
    )
    template = _jinja_env.get_template("proposta.html")
    html_str = template.render(**ctx)
    css = CSS(filename=str(_REPORTS_DIR / "proposta.css"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str).write_pdf(str(output_path), stylesheets=[css])

    proposal.pdf_path = str(output_path)
    self.session.commit()
    return output_path


# Attach to ProposalService at import time
from app.services.proposal_service import ProposalService as _PS
_PS.render_pdf = render_pdf  # type: ignore[attr-defined]
```

> **Note:** Cleaner alternative is to inline `render_pdf` directly inside `ProposalService` from the start in Phase 4. The patch-style above is provided for clarity; if you prefer, move this method into `ProposalService` body in Phase 4 Task 8.

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/services/test_proposal_render.py -v`
Expected: PASS (assumes WeasyPrint native deps are installed; if not, install via system package manager).

- [ ] **Step 7: Commit**

```bash
git add app/reports/ app/services/proposal_service.py tests/unit/services/test_proposal_render.py
git commit -m "feat(reports): PDF proposta with WeasyPrint + extras block"
```

---

## Task 2: Add "Gerar PDF" button to Simulação and Comparativo

**Files:**

- Modify: `app/ui/pages/simulacao.py` (add PDF button after saving simulation)
- Create: `app/ui/pages/_proposal_helper.py` (small helper used by simulacao)

- [ ] **Step 1: Write helper**

`app/ui/pages/_proposal_helper.py`:

```python
"""Helper to generate PDF from a simulation in UI context."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from nicegui import ui

from app.services.proposal_service import ProposalService


def generate_and_open_pdf(session, simulation_id: int, user_id: int,
                          data_dir: Path) -> Path | None:
    proposal = ProposalService(session).create(simulation_id, gerado_por=user_id)
    out_dir = data_dir / "propostas"
    out_path = out_dir / f"{proposal.codigo}.pdf"
    ProposalService(session).render_pdf(
        proposal.id, out_path,
        loja={"nome": "FinacialSim Loja"},
        vendedor={"nome": "Vendedor"},
    )
    _open_in_default_viewer(out_path)
    ui.notify(f"PDF gerado: {out_path.name}", type="positive")
    return out_path


def _open_in_default_viewer(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
```

- [ ] **Step 2: Wire the button into `simulacao.py`**

Modify the `simulacao.py` page (inside the `content()` function, after the `ui.button("Simular", ...)` line) to expose a `Gerar PDF` button that uses the last saved simulation id stored on the page state. A minimal addition:

```python
last_sim_id: dict[str, int | None] = {"id": None}

def simular() -> None:
    # ... existing code that creates `sim` ...
    last_sim_id["id"] = sim.id  # store after save
    # ... existing UI updates ...

def gerar_pdf() -> None:
    if last_sim_id["id"] is None:
        ui.notify("Simule antes de gerar PDF", type="warning")
        return
    from app.main import _platform_data_dir
    with SessionLocal() as session:
        generate_and_open_pdf(session, last_sim_id["id"], user_id, _platform_data_dir())

ui.button("Gerar PDF", on_click=gerar_pdf).classes("ml-2")
```

- [ ] **Step 3: Manual verify**

Run: `python -m app.main`. Open Simulação, run simulação, click "Gerar PDF". PDF should open in default viewer.

- [ ] **Step 4: Commit**

```bash
git add app/ui/pages/_proposal_helper.py app/ui/pages/simulacao.py
git commit -m "feat(ui): PDF generation button on simulacao page"
```

---

## Task 3: PyInstaller build script

**Files:**

- Create: `scripts/__init__.py` (empty)
- Create: `scripts/build_exe.py`
- Create: `scripts/finacialsim.spec`
- Create: `assets/icon.ico` (placeholder — replace with actual icon)

- [ ] **Step 1: Write the PyInstaller spec**

`scripts/finacialsim.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
project_root = Path.cwd()

a = Analysis(
    ["app/main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ("app/reports/proposta.html", "app/reports"),
        ("app/reports/proposta.css", "app/reports"),
        ("docs", "docs"),
        ("alembic.ini", "."),
        ("app/data/migrations", "app/data/migrations"),
    ],
    hiddenimports=[
        "weasyprint", "scipy.optimize", "apscheduler", "bcrypt",
        "plotly.graph_objects", "nicegui",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_path = "assets/icon.ico" if sys.platform.startswith("win") else "assets/icon.png"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FinacialSim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_path if Path(icon_path).exists() else None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="FinacialSim",
)
```

- [ ] **Step 2: Write `build_exe.py`**

`scripts/build_exe.py`:

```python
"""Cross-platform PyInstaller builder."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    dist = project_root / "dist"
    build = project_root / "build"

    for path in (dist, build):
        if path.exists():
            shutil.rmtree(path)

    cmd = ["pyinstaller", "scripts/finacialsim.spec", "--clean", "--noconfirm"]
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=project_root)
    if proc.returncode != 0:
        return proc.returncode

    print("\nBuild complete. Output:")
    print(f"  - {dist / 'FinacialSim'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Generate placeholder icons**

Run (creates a placeholder PNG you can later replace with a real icon):

```bash
python -c "from PIL import Image; img=Image.new('RGBA',(256,256),(21,101,192,255)); img.save('assets/icon.png')"
python -c "from PIL import Image; img=Image.new('RGBA',(256,256),(21,101,192,255)); img.save('assets/icon.ico')"
```

(Pillow is required; `pip install Pillow`.)

- [ ] **Step 4: Build and verify (current platform)**

Run:

```bash
pip install pyinstaller pillow
python scripts/build_exe.py
```

Expected: `dist/FinacialSim/` directory exists with the executable.

- [ ] **Step 5: Run the bundled binary**

Run (Windows): `dist\FinacialSim\FinacialSim.exe`
Run (Linux): `./dist/FinacialSim/FinacialSim`
Run (macOS): `./dist/FinacialSim/FinacialSim`

Expected: window opens, login works.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_exe.py scripts/finacialsim.spec assets/
git commit -m "feat(build): PyInstaller spec + builder script"
```

---

## Task 4: Windows NSIS installer

**Files:**

- Create: `scripts/installer.nsi`

- [ ] **Step 1: Write NSIS script**

`scripts/installer.nsi`:

```nsi
!define APPNAME "FinacialSim"
!define APPVERSION "1.0.0"
!define APPDIR "FinacialSim"

OutFile "..\dist\FinacialSim-Setup-${APPVERSION}.exe"
InstallDir "$PROGRAMFILES64\${APPDIR}"
RequestExecutionLevel admin
Name "${APPNAME}"

Page directory
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\dist\${APPDIR}\*.*"

  CreateDirectory "$SMPROGRAMS\${APPDIR}"
  CreateShortcut "$SMPROGRAMS\${APPDIR}\${APPNAME}.lnk" "$INSTDIR\FinacialSim.exe"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\FinacialSim.exe"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${APPVERSION}"
  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPDIR}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd
```

- [ ] **Step 2: Build installer (on Windows host with NSIS installed)**

Run (Windows only):

```bash
makensis scripts/installer.nsi
```

Expected: `dist/FinacialSim-Setup-1.0.0.exe` created. Double-click to install.

- [ ] **Step 3: Verify installation**

Install on a clean VM, run from Start Menu, login, run a simulation, generate PDF. All should work without Python on host.

- [ ] **Step 4: Commit**

```bash
git add scripts/installer.nsi
git commit -m "feat(build): NSIS installer for Windows"
```

---

## Task 5: Linux AppImage + install script

**Files:**

- Create: `scripts/build_appimage.sh`
- Create: `scripts/install_linux.sh`
- Create: `scripts/finacialsim.desktop`

- [ ] **Step 1: Write desktop entry**

`scripts/finacialsim.desktop`:

```ini
[Desktop Entry]
Name=FinacialSim
Comment=Simulador de financiamento de veiculos
Exec=FinacialSim
Icon=finacialsim
Terminal=false
Type=Application
Categories=Office;Finance;
```

- [ ] **Step 2: Write `build_appimage.sh`**

`scripts/build_appimage.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIST="$ROOT/dist"
APPDIR="$DIST/FinacialSim.AppDir"
APPIMAGE_TOOL="${APPIMAGE_TOOL:-appimagetool-x86_64.AppImage}"

# 1. Run PyInstaller first
python "$ROOT/scripts/build_exe.py"

# 2. Build AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST/FinacialSim/." "$APPDIR/usr/bin/"

# 3. Desktop + icon
cp "$ROOT/scripts/finacialsim.desktop" "$APPDIR/finacialsim.desktop"
cp "$ROOT/assets/icon.png" "$APPDIR/finacialsim.png"
cp "$ROOT/assets/icon.png" "$APPDIR/.DirIcon"

# 4. AppRun
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE=$(dirname $(readlink -f "$0"))
exec "$HERE/usr/bin/FinacialSim" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# 5. Build AppImage (requires appimagetool in PATH)
"$APPIMAGE_TOOL" "$APPDIR" "$DIST/FinacialSim-x86_64.AppImage"
echo "AppImage created at $DIST/FinacialSim-x86_64.AppImage"
```

- [ ] **Step 3: Make executable and run**

Run:

```bash
chmod +x scripts/build_appimage.sh
# Download appimagetool first if needed:
# wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
./scripts/build_appimage.sh
```

Expected: `dist/FinacialSim-x86_64.AppImage`.

- [ ] **Step 4: Write `install_linux.sh`**

`scripts/install_linux.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

APPIMAGE_URL="${1:-https://github.com/your-org/finacialsim/releases/latest/download/FinacialSim-x86_64.AppImage}"
INSTALL_DIR="/opt/finacialsim"
DESKTOP_FILE="$HOME/.local/share/applications/finacialsim.desktop"

sudo mkdir -p "$INSTALL_DIR"
sudo curl -L "$APPIMAGE_URL" -o "$INSTALL_DIR/FinacialSim.AppImage"
sudo chmod +x "$INSTALL_DIR/FinacialSim.AppImage"

mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=FinacialSim
Comment=Simulador de financiamento de veiculos
Exec=$INSTALL_DIR/FinacialSim.AppImage
Icon=$INSTALL_DIR/icon.png
Terminal=false
Type=Application
Categories=Office;Finance;
EOF

echo "FinacialSim instalado em $INSTALL_DIR"
echo "Inicie pelo menu de aplicativos ou via: $INSTALL_DIR/FinacialSim.AppImage"
```

- [ ] **Step 5: Test on a clean Ubuntu VM**

Verify: download, run, login, simulate, PDF.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_appimage.sh scripts/install_linux.sh scripts/finacialsim.desktop
git commit -m "feat(build): Linux AppImage builder + install script"
```

---

## Task 6: macOS .app bundle + DMG + install script

**Files:**

- Create: `scripts/build_macos.sh`
- Create: `scripts/install_macos.sh`

- [ ] **Step 1: Write `build_macos.sh`**

`scripts/build_macos.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIST="$ROOT/dist"
APP_NAME="FinacialSim.app"

# 1. PyInstaller produces a folder; we wrap it into .app
python "$ROOT/scripts/build_exe.py"

# 2. Create .app structure
APP="$DIST/$APP_NAME"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources"
cp -r "$DIST/FinacialSim/." "$APP/Contents/MacOS/"
cp "$ROOT/assets/icon.png" "$APP/Contents/Resources/icon.png"

# 3. Info.plist
cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>FinacialSim</string>
  <key>CFBundleDisplayName</key><string>FinacialSim</string>
  <key>CFBundleIdentifier</key><string>com.finacialsim.app</string>
  <key>CFBundleVersion</key><string>1.0.0</string>
  <key>CFBundleExecutable</key><string>FinacialSim</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
</dict>
</plist>
EOF

# 4. Ad-hoc sign (allows running locally without notarization)
codesign --deep --force --sign - "$APP"

# 5. DMG (requires create-dmg: brew install create-dmg)
create-dmg \
  --volname "FinacialSim Installer" \
  --window-size 600 400 \
  --app-drop-link 425 185 \
  --icon "$APP_NAME" 175 185 \
  "$DIST/FinacialSim-1.0.0.dmg" \
  "$APP"

echo "DMG at $DIST/FinacialSim-1.0.0.dmg"
```

- [ ] **Step 2: Write `install_macos.sh`**

`scripts/install_macos.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

DMG_URL="${1:-https://github.com/your-org/finacialsim/releases/latest/download/FinacialSim-1.0.0.dmg}"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew nao detectado. Instalando..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# WeasyPrint native deps
brew install pango gdk-pixbuf libffi

TMP=$(mktemp -d)
curl -L "$DMG_URL" -o "$TMP/finacialsim.dmg"
hdiutil attach "$TMP/finacialsim.dmg" -mountpoint /Volumes/FinacialSim
cp -R "/Volumes/FinacialSim/FinacialSim.app" /Applications/
hdiutil detach /Volumes/FinacialSim
rm -rf "$TMP"

echo "FinacialSim instalado em /Applications/FinacialSim.app"
```

- [ ] **Step 3: Make executables**

Run:

```bash
chmod +x scripts/build_macos.sh scripts/install_macos.sh
```

- [ ] **Step 4: Test on a macOS host (Apple Silicon and Intel if available)**

Build, mount DMG, drag to Applications, launch.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_macos.sh scripts/install_macos.sh
git commit -m "feat(build): macOS .app bundle + DMG + install script"
```

---

## Task 7: GitHub Actions release workflow

**Files:**

- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write workflow**

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags: ["v*.*.*"]

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .[dev]
      - run: pip install pyinstaller pillow
      - run: python scripts/build_exe.py
      - name: Install NSIS
        run: choco install nsis -y
      - run: makensis scripts/installer.nsi
      - uses: actions/upload-artifact@v4
        with:
          name: windows-installer
          path: dist/FinacialSim-Setup-*.exe

  build-linux:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: sudo apt-get update && sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info fuse libfuse2
      - run: pip install -e .[dev]
      - run: pip install pyinstaller pillow
      - run: |
          wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O appimagetool
          chmod +x appimagetool
          sudo mv appimagetool /usr/local/bin/
      - run: chmod +x scripts/build_appimage.sh && APPIMAGE_TOOL=/usr/local/bin/appimagetool scripts/build_appimage.sh
      - uses: actions/upload-artifact@v4
        with:
          name: linux-appimage
          path: dist/FinacialSim-x86_64.AppImage

  build-macos:
    runs-on: macos-13
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: brew install pango gdk-pixbuf libffi create-dmg
      - run: pip install -e .[dev]
      - run: pip install pyinstaller pillow
      - run: chmod +x scripts/build_macos.sh && scripts/build_macos.sh
      - uses: actions/upload-artifact@v4
        with:
          name: macos-dmg
          path: dist/FinacialSim-*.dmg

  publish:
    needs: [build-windows, build-linux, build-macos]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            windows-installer/*
            linux-appimage/*
            macos-dmg/*
```

- [ ] **Step 2: Commit (workflow runs only on tag push)**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): build Windows/Linux/macOS on tag and publish to GitHub Releases"
```

- [ ] **Step 3: Test the workflow**

Create a test tag:

```bash
git tag v0.0.1-test
git push origin v0.0.1-test
```

Watch Actions tab. After success, verify a draft release exists with all three artifacts.

---

## Task 8: End-user docs (`docs/INSTALACAO.md`, `docs/guia_usuario.md`, `docs/troubleshooting.md`, `docs/matematica_price.md`)

**Files:**

- Create: `docs/INSTALACAO.md`
- Create: `docs/guia_usuario.md`
- Create: `docs/troubleshooting.md`
- Create: `docs/matematica_price.md`
- Create: `docs/ARQUITETURA.md` (a slim version pointing to the spec)

- [ ] **Step 1: Write `docs/INSTALACAO.md`**

`docs/INSTALACAO.md`:

```markdown
# Instalacao do FinacialSim

## Windows 10+ (x64)

1. Baixe `FinacialSim-Setup-1.0.0.exe` na pagina de releases.
2. Execute o instalador. Aceite o UAC.
3. Escolha o diretorio de instalacao (default `C:\Program Files\FinacialSim`).
4. Aguarde a copia dos arquivos.
5. Ao terminar, abra pelo atalho no Desktop ou pelo menu Iniciar.
6. Primeiro login: usuario "Admin", PIN "123456" (sera solicitada a troca).

## Linux (Ubuntu/Debian/Fedora)

1. Baixe `FinacialSim-x86_64.AppImage`.
2. Torne-o executavel: `chmod +x FinacialSim-x86_64.AppImage`.
3. Execute: `./FinacialSim-x86_64.AppImage`.

Ou via script automatico:
```bash
curl -fsSL https://raw.githubusercontent.com/your-org/finacialsim/main/scripts/install_linux.sh | bash
```

## macOS 12+ (Monterey, Apple Silicon ou Intel)

1. Baixe `FinacialSim-1.0.0.dmg`.
2. Monte o DMG, arraste FinacialSim para Applications.
3. Na primeira execucao, va em System Settings > Privacy & Security se aparecer "App nao verificado" e clique em "Abrir mesmo assim".

Ou via script:

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/finacialsim/main/scripts/install_macos.sh | bash
```

## Pos-instalacao

- Dados ficam em:
  - Windows: `%APPDATA%\FinacialSim`
  - Linux: `~/.local/share/FinacialSim`
  - macOS: `~/Library/Application Support/FinacialSim`
- Backups automaticos rodam diariamente as 23:00.
- Atualizacoes de indicadores rodam diariamente as 09:00 (precisa de internet).

Consulte `troubleshooting.md` para problemas comuns.

```

- [ ] **Step 2: Write `docs/guia_usuario.md`** (high-level user manual)

`docs/guia_usuario.md`:
```markdown
# Guia do usuario

Este guia cobre os fluxos basicos do FinacialSim para vendedores.

## 1. Login

Selecione seu usuario e digite seu PIN. Caso erre 5 vezes, sua conta fica bloqueada por 5 minutos.

## 2. Cadastrar um cliente

1. Va em "Cadastro".
2. Escolha tipo (PF ou PJ).
3. Preencha nome, CPF/CNPJ (validado automaticamente), contato e endereco.
4. Salve.

## 3. Simular um financiamento

1. Va em "Simulacao".
2. Preencha valor do veiculo, entrada, prazo, taxa.
3. Defina data de liberacao e data do 1o vencimento.
4. (Opcional) Adicione "Custos adicionais mensais": plano de protecao, IPVA, emplacamento.
5. (Opcional) Desligue IOF se for cobrado fora.
6. Clique "Simular". Veja parcela, CET, cronograma e graficos.
7. Clique "Gerar PDF" para criar a proposta.

## 4. Comparar dois cenarios

1. Va em "Comparativo".
2. Selecione duas simulacoes ja salvas.
3. A tabela central mostra cada diferenca.

## 5. Amortizar antecipadamente

1. Va em "Amortizacao".
2. Selecione a simulacao base.
3. Informe data e valor do pagamento extra.
4. Escolha "reduzir parcela" ou "reduzir prazo".
5. Veja o novo cronograma.

## 6. Visualizar indicadores

A aba "Indicadores" mostra SELIC, CDI, IPCA e taxa BACEN de veiculos atualizados. Se algum indicador estiver desatualizado, peca ao gerente para atualizar.

## 7. Gerar PDF da proposta

Na simulacao, clique "Gerar PDF". O arquivo abre automaticamente no leitor padrao. O PDF inclui:
- Dados do cliente, veiculo, condicoes
- Bloco de custos adicionais (se houver)
- Resumo financeiro (parcela e total)
- Cronograma completo de amortizacao
- Espaco para assinatura
```

- [ ] **Step 3: Write `docs/troubleshooting.md`**

`docs/troubleshooting.md`:

```markdown
# Troubleshooting

## "App nao abre" (Windows)
- Verifique se o antivirus bloqueou o executavel. Adicione excecao para `C:\Program Files\FinacialSim\FinacialSim.exe`.
- Reinstale o app.

## "WeasyPrint error" / "libpango not found" (Linux)
Instale dependencias:
```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

## "App damaged" (macOS)

Va em System Settings > Privacy & Security > "Open Anyway". Necessario na primeira execucao por nao ser notarizado.

## Indicadores desatualizados

- Verifique conexao com internet.
- Va em "APIs" e clique "Atualizar indicadores agora".
- Se persistir, admin pode informar valores manuais em "Indicadores".

## FIPE nao retorna marcas

- Cache de listas dura 30 dias.
- Tente forcar atualizacao em "APIs".
- Use entrada manual caso ambas APIs falhem.

## Banco corrompido

- Backups automaticos diarios estao em `<data>/backups/`.
- Em Configuracoes > Backup, clique "Restaurar de arquivo..." e selecione o backup mais recente.

## CET nao bate com calculadora do banco

- Verifique se "Incluir IOF" esta ligado.
- Confira se valor do veiculo e entrada batem com o contrato.
- Lembre: custos adicionais (proteção, IPVA, emplacamento) NAO entram no CET por convencao BCB.

```

- [ ] **Step 4: Write `docs/matematica_price.md`** (math explainer)

`docs/matematica_price.md`:
```markdown
# Matematica financeira do FinacialSim

Este documento explica em detalhe as formulas usadas.

## Tabela Price com dias corridos

Seja:
- `PV` = valor financiado
- `i_m` = taxa mensal nominal (fracao decimal)
- `i_d` = (1 + i_m)^(1/30) - 1
- `d1` = dias entre liberacao e 1o vencimento
- `n` = numero de parcelas

A parcela fixa e calculada por:

```

PMT = PV *(1 + i_d)^d1* (i_m * (1 + i_m)^(n-1)) / ((1 + i_m)^n - 1)

```

Quando `d1 = 30`, esta formula reduz a Tabela Price classica:

```

PMT = PV *i_m* (1 + i_m)^n / ((1 + i_m)^n - 1)

```

## Cronograma

- Parcela 1: juros = `PV * ((1 + i_d)^d1 - 1)`, amortizacao = `PMT - juros`
- Parcelas 2..n-1: juros = `saldo * i_m`, amortizacao = `PMT - juros`
- Parcela n: amortizacao = saldo, ajuste de centavos vai em `ajuste_arredondamento`

## IOF

Decreto 6.306/2007:
- IOF fixo = 0,38% sobre o valor financiado
- IOF diario = sum(amortizacao_k * 0,0082% * min(dias_ate_venc_k, 365))

Quando incorporado ao principal, ha iteracao:
```

PV(0) = veiculo - entrada + tarifas
PV(n+1) = PV(0) + IOF(PV(n), schedule(PV(n)))
parar quando |PV(n+1) - PV(n)| < R$ 0,01

```
Convergencia em 2-3 iteracoes.

## CET

CET e a TIR (Taxa Interna de Retorno) mensal do fluxo de caixa:

```

valor_liberado = sum_k PMT / (1 + i_cet)^(meses_t_k)

```

Onde `meses_t_k = (d1 + 30*(k-1)) / 30`. Resolvido pelo metodo de Brent.

CET anual: `(1 + i_cet)^12 - 1`.

## Custos adicionais (extras)

Nao afetam PMT, IOF nem CET. Entram somente em `parcela_total = PMT + extras_total[k]`.

Modalidades:
- `mensal_continuo`: valor incide em todas as N parcelas
- `rateio_meses`: valor/duracao_meses incide nas D primeiras parcelas
- `unico_inicial`: valor incide apenas na 1a parcela
```

- [ ] **Step 5: Write slim `docs/ARQUITETURA.md`**

`docs/ARQUITETURA.md`:

```markdown
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
- `app/core/cet.py` — CET via TIR
- `app/services/simulation_service.py` — orquestracao da simulacao
- `app/reports/proposta.html` — template do PDF
- `scripts/build_exe.py` — empacotamento PyInstaller
```

- [ ] **Step 6: Commit**

```bash
git add docs/INSTALACAO.md docs/guia_usuario.md docs/troubleshooting.md docs/matematica_price.md docs/ARQUITETURA.md
git commit -m "docs: end-user manuals (instalacao, guia, troubleshooting, math, arquitetura)"
```

---

## Phase 6 — Definition of Done

- [ ] PDF generation works end-to-end (test passes; manual PDF visually correct)
- [ ] PyInstaller `--onedir` build runs on current platform
- [ ] Windows installer (.exe) builds and installs on a clean VM
- [ ] Linux AppImage builds and runs on Ubuntu 22.04
- [ ] macOS .app bundle + DMG build (when macOS host available)
- [ ] GitHub Actions release workflow runs successfully on a test tag and uploads 3 artifacts
- [ ] All 5 end-user docs written and committed
- [ ] App on a fresh install lets vendedor log in, run simulation, generate PDF without Python on host
- [ ] Acceptance criteria from spec §17 ALL passing on Windows 10, Ubuntu 22.04, and macOS 12

---

## MVP — Done

When this phase ends and all 17 acceptance criteria pass, the MVP is shipped.
