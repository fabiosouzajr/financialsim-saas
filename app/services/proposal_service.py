"""ProposalService - builds Proposal record + snapshot JSON + PDF rendering."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session
from weasyprint import CSS, HTML

from app.data.models import (
    AmortizationRow,
    BusinessRule,
    Client,
    Proposal,
    Simulation,
    SimulationExtra,
    SimulationFee,
    Vehicle,
)
from app.services.audit_service import AuditService
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


def _build_template_context(snap: dict, loja: dict, vendedor: dict, gerado_em: datetime, validade: int) -> dict:
    sim = snap["simulation"]
    rows = snap["cronograma"]
    extras = snap["extras"]
    cliente = snap["cliente"]
    veiculo = snap["veiculo"]

    parcela_total_1ano = rows[0]["parcela_total"] if rows else "0"
    last_idx = min(12, len(rows) - 1) if rows else 0
    parcela_total_apos = rows[last_idx]["parcela_total"] if rows else "0"

    def _D(s):
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
            **(cliente or {}),
            "cpf_cnpj_fmt": _format_cpf_cnpj(cliente["cpf_cnpj"], cliente["tipo"]) if cliente else "",
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


def _next_codigo(session: Session) -> str:
    year = date.today().year
    count = session.query(Proposal).filter(Proposal.codigo.like(f"PROP-{year}-%")).count()
    return f"PROP-{year}-{count + 1:05d}"


def _decimal_to_str(v: Decimal) -> str:
    return str(v)


class ProposalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def create(self, simulation_id: int, gerado_por: int, validade_dias: int = 7) -> Proposal:
        sim = self.session.get(Simulation, simulation_id)
        if sim is None:
            raise ValueError("simulation not found")

        cliente = self.session.get(Client, sim.cliente_id) if sim.cliente_id is not None else None
        veiculo = self.session.get(Vehicle, sim.veiculo_id)
        fees = self.session.query(SimulationFee).filter_by(simulation_id=sim.id).all()
        extras = self.session.query(SimulationExtra).filter_by(simulation_id=sim.id).order_by(SimulationExtra.ordem).all()
        rows = (
            self.session.query(AmortizationRow)
            .filter_by(simulation_id=sim.id)
            .order_by(AmortizationRow.numero_parcela)
            .all()
        )

        cliente_snap = None
        if cliente is not None:
            cliente_snap = {
                "nome": cliente.nome, "cpf_cnpj": cliente.cpf_cnpj, "tipo": cliente.tipo,
                "telefone": cliente.telefone, "email": cliente.email,
                "endereco_json": cliente.endereco_json,
            }

        snapshot = {
            "simulation": {
                "codigo": sim.codigo,
                "valor_veiculo": _decimal_to_str(sim.valor_veiculo),
                "valor_entrada": _decimal_to_str(sim.valor_entrada),
                "pct_entrada": _decimal_to_str(sim.pct_entrada),
                "prazo_meses": sim.prazo_meses,
                "taxa_juros_mes": _decimal_to_str(sim.taxa_juros_mes),
                "taxa_juros_ano": _decimal_to_str(sim.taxa_juros_ano),
                "data_liberacao": sim.data_liberacao.isoformat(),
                "data_primeiro_venc": sim.data_primeiro_venc.isoformat(),
                "incluir_iof": sim.incluir_iof,
                "iof_total": _decimal_to_str(sim.iof_total),
                "tarifas_total": _decimal_to_str(sim.tarifas_total),
                "extras_total_acumulado": _decimal_to_str(sim.extras_total_acumulado),
                "valor_financiado": _decimal_to_str(sim.valor_financiado),
                "valor_parcela": _decimal_to_str(sim.valor_parcela),
                "total_pago": _decimal_to_str(sim.total_pago),
                "total_juros": _decimal_to_str(sim.total_juros),
                "pct_juros": _decimal_to_str(sim.pct_juros),
                "cet_mes": _decimal_to_str(sim.cet_mes),
                "cet_ano": _decimal_to_str(sim.cet_ano),
            },
            "cliente": cliente_snap,
            "veiculo": {
                "marca": veiculo.marca, "modelo": veiculo.modelo,
                "ano_modelo": veiculo.ano_modelo, "combustivel": veiculo.combustivel,
                "placa": veiculo.placa,
                "codigo_fipe": veiculo.codigo_fipe,
                "valor_fipe": _decimal_to_str(veiculo.valor_fipe) if veiculo.valor_fipe else None,
                "mes_referencia_fipe": veiculo.mes_referencia_fipe,
            },
            "tarifas": [
                {"nome": f.nome, "valor": _decimal_to_str(f.valor),
                 "incluir_no_principal": f.incluir_no_principal}
                for f in fees
            ],
            "extras": [
                {"tipo": e.tipo, "nome": e.nome,
                 "valor_total": _decimal_to_str(e.valor_total),
                 "modalidade": e.modalidade, "duracao_meses": e.duracao_meses,
                 "valor_por_parcela": _decimal_to_str(e.valor_por_parcela)}
                for e in extras
            ],
            "cronograma": [
                {"numero": r.numero_parcela, "venc": r.data_vencimento.isoformat(),
                 "juros": _decimal_to_str(r.juros), "amortizacao": _decimal_to_str(r.amortizacao),
                 "parcela": _decimal_to_str(r.parcela), "extras": _decimal_to_str(r.extras_total),
                 "parcela_total": _decimal_to_str(r.parcela_total),
                 "saldo": _decimal_to_str(r.saldo_devedor)}
                for r in rows
            ],
        }

        proposal = Proposal(
            codigo=_next_codigo(self.session),
            simulation_id=sim.id,
            cliente_id=cliente.id if cliente else None,
            gerado_por=gerado_por,
            snapshot_json=json.dumps(snapshot),
            pdf_path=None,
            validade_dias=validade_dias,
        )
        self.session.add(proposal)
        self.session.commit()
        self.audit.log(
            "proposta_gerada",
            usuario_id=gerado_por,
            entidade="proposals",
            entidade_id=proposal.id,
        )
        return proposal

    def _get_loja(self) -> dict:
        def _raw(chave: str) -> str:
            row = self.session.query(BusinessRule).filter_by(chave=chave).first()
            return json.loads(row.valor_json) if row else ""
        return {
            "nome": _raw("nome_loja"),
            "cnpj": _raw("cnpj_loja"),
            "endereco": _raw("endereco_loja"),
            "telefone": _raw("telefone_loja"),
        }

    def render_pdf(self, proposal_id: int, output_path: Path,
                   loja: dict | None = None, vendedor: dict | None = None) -> Path:
        proposal = self.session.get(Proposal, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        snap = json.loads(proposal.snapshot_json)
        snap.setdefault("proposta", {})["codigo"] = proposal.codigo

        resolved_loja = loja if loja is not None else self._get_loja()
        ctx = _build_template_context(
            snap,
            loja=resolved_loja or {"nome": "Loja"},
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

    def generate_carne(self, proposal_id: int, output_dir: Path) -> Path:
        proposal = self.session.get(Proposal, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")

        snap = json.loads(proposal.snapshot_json)
        cliente = snap.get("cliente")
        veiculo = snap["veiculo"]
        rows = snap["cronograma"]
        total = len(rows)

        loja = self._get_loja()

        cliente_nome = cliente["nome"] if cliente else ""
        cliente_cpf = (
            _format_cpf_cnpj(cliente["cpf_cnpj"], cliente["tipo"]) if cliente else ""
        )
        descricao = f"{veiculo['marca']} {veiculo['modelo']} {veiculo['ano_modelo']}"
        placa = veiculo.get("placa")

        parcelas = [
            {
                "numero": r["numero"],
                "total": total,
                "vencimento_br": format_date_br(date.fromisoformat(r["venc"])),
                "valor_total_brl": format_brl(Decimal(r["parcela_total"])),
            }
            for r in rows
        ]

        ctx = {
            "loja": loja,
            "proposal": {"codigo": proposal.codigo},
            "cliente": {"nome": cliente_nome, "cpf_cnpj_fmt": cliente_cpf},
            "veiculo": {"descricao": descricao, "placa": placa},
            "parcelas": parcelas,
        }

        template = _jinja_env.get_template("carne.html")
        html_str = template.render(**ctx)
        css = CSS(filename=str(_REPORTS_DIR / "carne.css"))

        placa_clean = placa.replace("-", "").replace(" ", "") if placa else None
        filename = (
            f"CARNE-{placa_clean}-{proposal.codigo}.pdf"
            if placa_clean
            else f"CARNE-{proposal.codigo}.pdf"
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / filename
        HTML(string=html_str).write_pdf(str(out_path), stylesheets=[css])

        proposal.carne_path = str(out_path)
        self.session.commit()
        return out_path
