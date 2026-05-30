from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_core.cet import compute_cet
from finacialsim_core.extras import Extra, ExtraModalidade, compute_extras_per_parcela
from finacialsim_core.iof import IofConfig, compute_financed_amount_with_iof
from finacialsim_core.money import quantize_brl
from finacialsim_core.price_table import build_schedule
from finacialsim_core.validators import SimulationInput, ValidationRules, validate_simulation

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AmortizationRow, Simulation, SimulationExtra, SimulationFee,
    SimulationStatus,
)
from finacialsim_saas.errors import AppError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.simulations import (
    AmortizationRowOut, ExtraIn, FeeIn, SimulationCreate, SimulationListItem,
    SimulationListPage, SimulationOut, SimulationPreviewRequest,
    SimulationPreviewResponse, SimulationSummary, ValidationIssueOut,
    FeeOut, ExtraOut,
)
from finacialsim_saas.services.rules_service import RulesService


def _iof_config_from_rules(rules: dict) -> IofConfig:
    return IofConfig(
        fixo_pct=Decimal(str(rules["iof_fixo_pct"])),
        diario_pct=Decimal(str(rules["iof_diario_pct"])),
        max_dias=int(rules["iof_diario_max_dias"]),
    )


def _validation_rules_from_rules(rules: dict) -> ValidationRules:
    return ValidationRules(
        entrada_minima_pct=Decimal(str(rules["entrada_minima_pct"])),
        prazo_minimo_meses=int(rules["prazo_minimo_meses"]),
        prazo_maximo_meses=int(rules["prazo_maximo_meses"]),
        taxa_minima_mes=Decimal(str(rules["taxa_minima_mes"])),
        taxa_maxima_mes=Decimal(str(rules["taxa_maxima_mes"])),
        dias_max_carencia=int(rules["dias_max_carencia"]),
        valor_minimo_financiado=Decimal(str(rules["valor_minimo_financiado"])),
    )


def _extras_from_input(extras_in: list[ExtraIn]) -> list[Extra]:
    return [
        Extra(
            tipo=e.tipo,
            nome=e.nome,
            valor_total=e.valor_total,
            modalidade=ExtraModalidade(e.modalidade),
            duracao_meses=e.duracao_meses,
            ordem=e.ordem,
        )
        for e in extras_in
    ]


@dataclass
class _ComputeResult:
    valor_financiado: Decimal
    iof_total: Decimal
    schedule_rows: list
    extras_per_parcela: list[Decimal]
    summary: SimulationSummary


def _compute(
    valor_veiculo: Decimal,
    valor_entrada: Decimal,
    taxa_mensal: Decimal,
    prazo_meses: int,
    data_liberacao: date,
    primeiro_vencimento: date,
    incluir_iof: bool,
    fees_in: list[FeeIn],
    extras_in: list[ExtraIn],
    rules: dict,
) -> _ComputeResult:
    d1 = (primeiro_vencimento - data_liberacao).days
    base_pv = valor_veiculo - valor_entrada
    base_pv += sum(
        (Decimal(str(f.valor)) for f in fees_in if f.incluir_no_principal),
        Decimal("0.00"),
    )

    iof_config = _iof_config_from_rules(rules)
    financed = compute_financed_amount_with_iof(
        pv_inicial=base_pv,
        taxa_mensal=taxa_mensal,
        n=prazo_meses,
        d1=d1,
        data_liberacao=data_liberacao,
        config=iof_config,
        incluir_iof=incluir_iof,
    )
    final_pv = financed.valor_financiado
    iof_total = financed.iof.total
    schedule = financed.schedule

    extras = _extras_from_input(extras_in)
    extras_per_parcela = compute_extras_per_parcela(extras, prazo_meses)

    total_pago = sum(
        (row.parcela + extras_per_parcela[i] for i, row in enumerate(schedule.rows)),
        Decimal("0.00"),
    )
    total_pago = quantize_brl(total_pago)

    parcela_total_apos_rateio = schedule.pmt

    cet = compute_cet(
        valor_liberado=valor_veiculo - valor_entrada,
        schedule=schedule,
        d1=d1,
    )

    summary = SimulationSummary(
        parcela_financiamento=schedule.pmt,
        parcela_total_primeiro_ano=quantize_brl(schedule.rows[0].parcela + extras_per_parcela[0]),
        parcela_total_apos_rateio=parcela_total_apos_rateio,
        valor_financiado=final_pv,
        total_pago=total_pago,
        total_juros=schedule.total_juros,
        pct_juros=quantize_brl(schedule.total_juros / final_pv * Decimal("100")),
        cet_mensal=cet.cet_mes,
        cet_anual=cet.cet_ano,
        total_pago_pelo_cliente=quantize_brl(total_pago + valor_entrada),
        iof_total=iof_total,
    )

    return _ComputeResult(
        valor_financiado=final_pv,
        iof_total=iof_total,
        schedule_rows=list(schedule.rows),
        extras_per_parcela=extras_per_parcela,
        summary=summary,
    )


def _rows_to_out(result: _ComputeResult) -> list[AmortizationRowOut]:
    out = []
    for i, row in enumerate(result.schedule_rows):
        extras_total = result.extras_per_parcela[i]
        out.append(AmortizationRowOut(
            numero_parcela=row.numero_parcela,
            data_vencimento=row.data_vencimento,
            dias_periodo=row.dias_periodo,
            saldo_anterior=row.saldo_anterior,
            juros=row.juros,
            amortizacao=row.amortizacao,
            parcela=row.parcela,
            saldo_devedor=row.saldo_devedor,
            extras_total=extras_total,
            parcela_total=quantize_brl(row.parcela + extras_total),
            ajuste_arredondamento=row.ajuste_arredondamento,
        ))
    return out


class SimulationService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._rules_svc = RulesService(session)

    async def preview(
        self, payload: SimulationPreviewRequest, ctx: RequestContext
    ) -> SimulationPreviewResponse:
        rules = await self._rules_svc.get_rules(ctx.tenant_id)
        result = _compute(
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            fees_in=payload.fees,
            extras_in=payload.extras,
            rules=rules,
        )
        return SimulationPreviewResponse(
            summary=result.summary,
            rows=_rows_to_out(result),
        )

    async def _generate_codigo(self, tenant_id: uuid.UUID) -> str:
        year = datetime.now(timezone.utc).year
        row = await self._s.execute(
            text(
                "INSERT INTO simulation_counters (tenant_id, year, next_val) "
                "VALUES (:tid, :yr, 2) "
                "ON CONFLICT (tenant_id, year) DO UPDATE "
                "SET next_val = simulation_counters.next_val + 1 "
                "RETURNING next_val - 1"
            ),
            {"tid": str(tenant_id), "yr": year},
        )
        n = row.scalar_one()
        return f"SIM-{year}-{n:05d}"

    async def create(
        self, payload: SimulationCreate, ctx: RequestContext
    ) -> SimulationOut:
        if payload.idempotency_key:
            existing = await self._s.execute(
                select(Simulation).where(
                    Simulation.idempotency_key == payload.idempotency_key,
                    Simulation.tenant_id == ctx.tenant_id,
                )
            )
            sim = existing.scalar_one_or_none()
            if sim is not None:
                return await self.get(sim.id, ctx)

        rules = await self._rules_svc.get_rules(ctx.tenant_id)

        v_rules = _validation_rules_from_rules(rules)
        d1 = (payload.primeiro_vencimento - payload.data_liberacao).days
        issues = validate_simulation(
            SimulationInput(
                valor_veiculo=payload.valor_veiculo,
                valor_entrada=payload.valor_entrada,
                prazo_meses=payload.prazo_meses,
                taxa_mensal=payload.taxa_mensal,
                dias_carencia=d1,
            ),
            v_rules,
        )
        errors = [i for i in issues if i.level == "error"]
        if errors:
            raise ValidationError(
                "Simulation validation failed",
                details=[{"field": i.field, "message": i.message, "level": i.level}
                         for i in errors],
            )

        result = _compute(
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            fees_in=payload.fees,
            extras_in=payload.extras,
            rules=rules,
        )

        from finacialsim_saas.data.models import Client, Vehicle
        client_row = await self._s.get(Client, payload.client_id)
        if client_row is None or client_row.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"Cliente {payload.client_id} não encontrado")
        vehicle_row = await self._s.get(Vehicle, payload.vehicle_id)
        if vehicle_row is None or vehicle_row.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"Veículo {payload.vehicle_id} não encontrado")
        cliente_nome = client_row.nome
        veiculo_descricao = f"{vehicle_row.marca} {vehicle_row.modelo} {vehicle_row.ano_modelo}"

        codigo = await self._generate_codigo(ctx.tenant_id)
        sim = Simulation(
            tenant_id=ctx.tenant_id,
            codigo=codigo,
            client_id=payload.client_id,
            vehicle_id=payload.vehicle_id,
            cliente_nome=cliente_nome,
            veiculo_descricao=veiculo_descricao,
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            valor_financiado=result.valor_financiado,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            iof_total=result.iof_total,
            parcela_financiamento=result.summary.parcela_financiamento,
            total_pago=result.summary.total_pago,
            total_juros=result.summary.total_juros,
            cet_mensal=result.summary.cet_mensal,
            cet_anual=result.summary.cet_anual,
            status=SimulationStatus.confirmado,
            rules_snapshot_json=rules,
            idempotency_key=payload.idempotency_key,
            criado_por=ctx.user_id,
        )
        self._s.add(sim)
        await self._s.flush()

        for fee in payload.fees:
            self._s.add(SimulationFee(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                nome=fee.nome, valor=fee.valor,
                incluir_no_principal=fee.incluir_no_principal,
            ))

        for extra in payload.extras:
            from finacialsim_core.extras import _valor_por_parcela
            core_extra = Extra(
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=ExtraModalidade(extra.modalidade),
                duracao_meses=extra.duracao_meses, ordem=extra.ordem,
            )
            vparcela = _valor_por_parcela(core_extra)
            self._s.add(SimulationExtra(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=extra.modalidade, duracao_meses=extra.duracao_meses,
                valor_por_parcela=vparcela, ordem=extra.ordem,
            ))

        for row_out in _rows_to_out(result):
            self._s.add(AmortizationRow(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                numero_parcela=row_out.numero_parcela,
                data_vencimento=row_out.data_vencimento,
                dias_periodo=row_out.dias_periodo,
                saldo_anterior=row_out.saldo_anterior,
                juros=row_out.juros,
                amortizacao=row_out.amortizacao,
                parcela=row_out.parcela,
                saldo_devedor=row_out.saldo_devedor,
                extras_total=row_out.extras_total,
                parcela_total=row_out.parcela_total,
                ajuste_arredondamento=row_out.ajuste_arredondamento,
            ))

        await self._s.flush()
        return await self.get(sim.id, ctx)

    async def get(self, sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut:
        result = await self._s.execute(
            select(Simulation).where(
                Simulation.id == sim_id,
                Simulation.tenant_id == ctx.tenant_id,
            )
        )
        sim = result.scalar_one_or_none()
        if sim is None:
            raise NotFoundError(f"Simulation {sim_id} not found")

        fees_r = await self._s.execute(
            select(SimulationFee).where(SimulationFee.simulation_id == sim_id)
        )
        extras_r = await self._s.execute(
            select(SimulationExtra).where(SimulationExtra.simulation_id == sim_id)
        )
        rows_r = await self._s.execute(
            select(AmortizationRow)
            .where(AmortizationRow.simulation_id == sim_id)
            .order_by(AmortizationRow.numero_parcela)
        )
        fees = fees_r.scalars().all()
        extras = extras_r.scalars().all()
        rows = rows_r.scalars().all()

        row_outs = [
            AmortizationRowOut(
                numero_parcela=r.numero_parcela,
                data_vencimento=r.data_vencimento,
                dias_periodo=r.dias_periodo,
                saldo_anterior=r.saldo_anterior,
                juros=r.juros,
                amortizacao=r.amortizacao,
                parcela=r.parcela,
                saldo_devedor=r.saldo_devedor,
                extras_total=r.extras_total,
                parcela_total=r.parcela_total,
                ajuste_arredondamento=r.ajuste_arredondamento,
            )
            for r in rows
        ]

        total_pago = sum((r.parcela_total for r in rows), Decimal("0.00"))
        summary = SimulationSummary(
            parcela_financiamento=sim.parcela_financiamento,
            parcela_total_primeiro_ano=row_outs[0].parcela_total if row_outs else Decimal("0"),
            parcela_total_apos_rateio=sim.parcela_financiamento,
            valor_financiado=sim.valor_financiado,
            total_pago=total_pago,
            total_juros=sim.total_juros,
            pct_juros=quantize_brl(sim.total_juros / sim.valor_financiado * Decimal("100")),
            cet_mensal=sim.cet_mensal,
            cet_anual=sim.cet_anual,
            total_pago_pelo_cliente=quantize_brl(total_pago + sim.valor_entrada),
            iof_total=sim.iof_total,
        )

        return SimulationOut(
            id=sim.id,
            tenant_id=sim.tenant_id,
            codigo=sim.codigo,
            client_id=sim.client_id,
            vehicle_id=sim.vehicle_id,
            cliente_nome=sim.cliente_nome,
            veiculo_descricao=sim.veiculo_descricao,
            valor_veiculo=sim.valor_veiculo,
            valor_entrada=sim.valor_entrada,
            valor_financiado=sim.valor_financiado,
            taxa_mensal=sim.taxa_mensal,
            prazo_meses=sim.prazo_meses,
            data_liberacao=sim.data_liberacao,
            primeiro_vencimento=sim.primeiro_vencimento,
            incluir_iof=sim.incluir_iof,
            iof_total=sim.iof_total,
            parcela_financiamento=sim.parcela_financiamento,
            total_pago=total_pago,
            total_juros=sim.total_juros,
            cet_mensal=sim.cet_mensal,
            cet_anual=sim.cet_anual,
            status=sim.status.value,
            criado_por=sim.criado_por,
            criado_em=sim.criado_em,
            atualizado_em=sim.atualizado_em,
            fees=[FeeOut(id=f.id, nome=f.nome, valor=f.valor,
                         incluir_no_principal=f.incluir_no_principal) for f in fees],
            extras=[ExtraOut(id=e.id, tipo=e.tipo, nome=e.nome, valor_total=e.valor_total,
                             modalidade=e.modalidade, duracao_meses=e.duracao_meses,
                             valor_por_parcela=e.valor_por_parcela, ordem=e.ordem) for e in extras],
            rows=row_outs,
            summary=summary,
        )

    async def list(
        self,
        ctx: RequestContext,
        status: str | None = None,
        cliente_nome: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> SimulationListPage:
        q = select(Simulation).where(Simulation.tenant_id == ctx.tenant_id)
        if status:
            q = q.where(Simulation.status == SimulationStatus(status))
        if cliente_nome:
            q = q.where(Simulation.cliente_nome.ilike(f"%{cliente_nome}%"))
        if date_from:
            q = q.where(Simulation.criado_em >= datetime(
                date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc
            ))
        if date_to:
            q = q.where(Simulation.criado_em < datetime(
                date_to.year, date_to.month, date_to.day + 1, tzinfo=timezone.utc
            ))
        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode()
                cur_ts, cur_id = decoded.rsplit(",", 1)
                q = q.where(
                    (Simulation.criado_em < cur_ts) |
                    ((Simulation.criado_em == cur_ts) & (Simulation.id < cur_id))
                )
            except Exception:
                pass

        q = q.order_by(Simulation.criado_em.desc(), Simulation.id.desc()).limit(limit + 1)
        result = await self._s.execute(q)
        rows = result.scalars().all()

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more:
            last = items[-1]
            raw = f"{last.criado_em.isoformat()},{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return SimulationListPage(
            items=[
                SimulationListItem(
                    id=s.id, codigo=s.codigo,
                    client_id=s.client_id, vehicle_id=s.vehicle_id,
                    cliente_nome=s.cliente_nome,
                    veiculo_descricao=s.veiculo_descricao, valor_veiculo=s.valor_veiculo,
                    valor_financiado=s.valor_financiado, prazo_meses=s.prazo_meses,
                    taxa_mensal=s.taxa_mensal, status=s.status.value, criado_em=s.criado_em,
                )
                for s in items
            ],
            next_cursor=next_cursor,
        )

    async def update(
        self, sim_id: uuid.UUID, payload: SimulationCreate, ctx: RequestContext
    ) -> SimulationOut:
        result = await self._s.execute(
            select(Simulation).where(
                Simulation.id == sim_id,
                Simulation.tenant_id == ctx.tenant_id,
            )
        )
        sim = result.scalar_one_or_none()
        if sim is None:
            raise NotFoundError(f"Simulation {sim_id} not found")
        if sim.status != SimulationStatus.rascunho:
            raise AppError("Only rascunho simulations can be updated", details=None)
        if str(sim.criado_por) != str(ctx.user_id) and ctx.role.value not in ("manager", "admin"):
            raise TenantAccessError("Cannot update another user's simulation")

        await self._s.execute(
            text("DELETE FROM simulation_fees WHERE simulation_id = :sid"),
            {"sid": str(sim_id)},
        )
        await self._s.execute(
            text("DELETE FROM simulation_extras WHERE simulation_id = :sid"),
            {"sid": str(sim_id)},
        )
        await self._s.execute(
            text("DELETE FROM amortization_rows WHERE simulation_id = :sid"),
            {"sid": str(sim_id)},
        )

        rules = await self._rules_svc.get_rules(ctx.tenant_id)
        v_rules = _validation_rules_from_rules(rules)
        d1 = (payload.primeiro_vencimento - payload.data_liberacao).days
        issues = validate_simulation(
            SimulationInput(
                valor_veiculo=payload.valor_veiculo,
                valor_entrada=payload.valor_entrada,
                prazo_meses=payload.prazo_meses,
                taxa_mensal=payload.taxa_mensal,
                dias_carencia=d1,
            ),
            v_rules,
        )
        errors = [i for i in issues if i.level == "error"]
        if errors:
            raise ValidationError(
                "Simulation validation failed",
                details=[{"field": i.field, "message": i.message, "level": i.level}
                         for i in errors],
            )

        result_c = _compute(
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            fees_in=payload.fees,
            extras_in=payload.extras,
            rules=rules,
        )

        sim.cliente_nome = payload.cliente_nome
        sim.veiculo_descricao = payload.veiculo_descricao
        sim.valor_veiculo = payload.valor_veiculo
        sim.valor_entrada = payload.valor_entrada
        sim.valor_financiado = result_c.valor_financiado
        sim.taxa_mensal = payload.taxa_mensal
        sim.prazo_meses = payload.prazo_meses
        sim.data_liberacao = payload.data_liberacao
        sim.primeiro_vencimento = payload.primeiro_vencimento
        sim.incluir_iof = payload.incluir_iof
        sim.iof_total = result_c.iof_total
        sim.parcela_financiamento = result_c.summary.parcela_financiamento
        sim.total_pago = result_c.summary.total_pago
        sim.total_juros = result_c.summary.total_juros
        sim.cet_mensal = result_c.summary.cet_mensal
        sim.cet_anual = result_c.summary.cet_anual
        sim.rules_snapshot_json = rules
        sim.atualizado_em = datetime.now(timezone.utc)

        for fee in payload.fees:
            self._s.add(SimulationFee(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                nome=fee.nome, valor=fee.valor,
                incluir_no_principal=fee.incluir_no_principal,
            ))
        for extra in payload.extras:
            from finacialsim_core.extras import _valor_por_parcela
            core_extra = Extra(
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=ExtraModalidade(extra.modalidade),
                duracao_meses=extra.duracao_meses, ordem=extra.ordem,
            )
            self._s.add(SimulationExtra(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=extra.modalidade, duracao_meses=extra.duracao_meses,
                valor_por_parcela=_valor_por_parcela(core_extra), ordem=extra.ordem,
            ))
        for row_out in _rows_to_out(result_c):
            self._s.add(AmortizationRow(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                numero_parcela=row_out.numero_parcela,
                data_vencimento=row_out.data_vencimento,
                dias_periodo=row_out.dias_periodo,
                saldo_anterior=row_out.saldo_anterior,
                juros=row_out.juros,
                amortizacao=row_out.amortizacao,
                parcela=row_out.parcela,
                saldo_devedor=row_out.saldo_devedor,
                extras_total=row_out.extras_total,
                parcela_total=row_out.parcela_total,
                ajuste_arredondamento=row_out.ajuste_arredondamento,
            ))

        await self._s.flush()
        return await self.get(sim.id, ctx)

    async def archive(self, sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut:
        result = await self._s.execute(
            select(Simulation).where(
                Simulation.id == sim_id,
                Simulation.tenant_id == ctx.tenant_id,
            )
        )
        sim = result.scalar_one_or_none()
        if sim is None:
            raise NotFoundError(f"Simulation {sim_id} not found")
        if str(sim.criado_por) != str(ctx.user_id) and ctx.role.value not in ("manager", "admin"):
            raise TenantAccessError("Cannot archive another user's simulation")
        sim.status = SimulationStatus.arquivado
        sim.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return await self.get(sim.id, ctx)

    async def clone(self, sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut:
        original = await self.get(sim_id, ctx)
        orm_r = await self._s.execute(
            select(Simulation).where(Simulation.id == sim_id)
        )
        orm_sim = orm_r.scalar_one()
        codigo = await self._generate_codigo(ctx.tenant_id)
        new_sim = Simulation(
            tenant_id=ctx.tenant_id,
            codigo=codigo,
            cliente_nome=original.cliente_nome,
            veiculo_descricao=original.veiculo_descricao,
            valor_veiculo=original.valor_veiculo,
            valor_entrada=original.valor_entrada,
            valor_financiado=original.valor_financiado,
            taxa_mensal=original.taxa_mensal,
            prazo_meses=original.prazo_meses,
            data_liberacao=original.data_liberacao,
            primeiro_vencimento=original.primeiro_vencimento,
            incluir_iof=original.incluir_iof,
            iof_total=original.iof_total,
            parcela_financiamento=original.parcela_financiamento,
            total_pago=original.total_pago,
            total_juros=original.total_juros,
            cet_mensal=original.cet_mensal,
            cet_anual=original.cet_anual,
            status=SimulationStatus.rascunho,
            rules_snapshot_json=orm_sim.rules_snapshot_json or {},
            idempotency_key=None,
            criado_por=ctx.user_id,
        )
        self._s.add(new_sim)
        await self._s.flush()

        for fee in original.fees:
            self._s.add(SimulationFee(
                simulation_id=new_sim.id, tenant_id=ctx.tenant_id,
                nome=fee.nome, valor=fee.valor,
                incluir_no_principal=fee.incluir_no_principal,
            ))
        for extra in original.extras:
            self._s.add(SimulationExtra(
                simulation_id=new_sim.id, tenant_id=ctx.tenant_id,
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=extra.modalidade, duracao_meses=extra.duracao_meses,
                valor_por_parcela=extra.valor_por_parcela, ordem=extra.ordem,
            ))
        for row in original.rows:
            self._s.add(AmortizationRow(
                simulation_id=new_sim.id, tenant_id=ctx.tenant_id,
                numero_parcela=row.numero_parcela,
                data_vencimento=row.data_vencimento,
                dias_periodo=row.dias_periodo,
                saldo_anterior=row.saldo_anterior,
                juros=row.juros,
                amortizacao=row.amortizacao,
                parcela=row.parcela,
                saldo_devedor=row.saldo_devedor,
                extras_total=row.extras_total,
                parcela_total=row.parcela_total,
                ajuste_arredondamento=row.ajuste_arredondamento,
            ))

        await self._s.flush()
        return await self.get(new_sim.id, ctx)
