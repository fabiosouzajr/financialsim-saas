from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, Client, ClientType, ParcelaPayment, ParcelaPaymentStatus, PixCharge,
    PixChargeStatus, PixWebhookEvent, Proposal, Role, Simulation, User,
)
from finacialsim_saas.errors import NotFoundError, ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixProvider
from finacialsim_saas.services.rules_service import RulesService
from finacialsim_saas.storage import StorageBackend

UTC = timezone.utc
_BRT = ZoneInfo("America/Sao_Paulo")


def _created_before_today_brt(charge: PixCharge) -> bool:
    """True if the charge was created on a previous BRT calendar day."""
    created_brt = charge.criado_em.astimezone(_BRT).date()
    today_brt = datetime.now(_BRT).date()
    return created_brt < today_brt


class PixService:
    def __init__(
        self,
        session: AsyncSession,
        provider: PixProvider,
        storage: StorageBackend,
    ) -> None:
        self._s = session
        self._provider = provider
        self._storage = storage

    async def _lazy_flip_expired(self, charge: PixCharge) -> None:
        if (
            charge.status == PixChargeStatus.pending
            and charge.expires_at.replace(tzinfo=UTC) < datetime.now(UTC)
        ):
            charge.status = PixChargeStatus.expired
            charge.atualizado_em = datetime.now(UTC)

    async def _ensure_charge(self, parcela: ParcelaPayment) -> tuple[PixCharge, bool]:
        """Idempotent CobV charge per parcela with daily regeneration for overdue.
        Returns (charge, created) — callers notify only when created=True."""
        rules = await RulesService(self._s).get_rules(parcela.tenant_id)
        validity_days = int(rules["pix_validade_apos_vencimento_dias"])
        multa_pct_raw = Decimal(str(rules.get("inadimplencia_multa_pct", "0.00")))
        juros_pct_raw = Decimal(str(rules.get("inadimplencia_juros_diario_pct", "0.00")))
        carencia_dias = int(rules.get("inadimplencia_carencia_dias", 0))

        today = date.today()
        dias_atraso = (today - parcela.vencimento).days if parcela.vencimento < today else 0
        rates_past_grace = (
            parcela.status == ParcelaPaymentStatus.overdue
            and dias_atraso > carencia_dias
            and (multa_pct_raw > 0 or juros_pct_raw > 0)
        )
        multa_pct = multa_pct_raw if rates_past_grace else Decimal("0.00")
        juros_diario_pct = juros_pct_raw if rates_past_grace else Decimal("0.00")

        if parcela.last_pix_charge_id is not None:
            existing = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if existing is not None:
                await self._lazy_flip_expired(existing)
                if existing.status == PixChargeStatus.pending:
                    needs_regeneration = rates_past_grace and _created_before_today_brt(existing)
                    if not needs_regeneration:
                        await self._s.flush()
                        return existing, False
                    # Cancel stale charge to regenerate with current interest
                    try:
                        await self._provider.cancel_charge(existing.txid)
                    except Exception:
                        pass
                    existing.status = PixChargeStatus.canceled
                    existing.atualizado_em = datetime.now(UTC)

        proposal = await self._s.get(Proposal, parcela.proposal_id)
        sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
        client = await self._s.get(Client, sim.client_id) if sim and sim.client_id else None
        if client is None:
            raise ValidationError("não é possível gerar Pix sem cliente vinculado à proposta")

        payer = PayerInfo(
            document="".join(ch for ch in client.cpf_cnpj if ch.isdigit()),
            document_type="cpf" if client.tipo == ClientType.pf else "cnpj",
            name=client.nome,
        )

        charge_id = uuid.uuid4()
        txid = str(charge_id).replace("-", "")[:35]

        charge_data = await self._provider.create_charge(
            txid=txid,
            amount=parcela.valor_parcela,
            due_date=parcela.vencimento,
            validity_days=validity_days,
            description=f"Parcela {parcela.parcela_num}",
            payer=payer,
            multa_pct=multa_pct,
            juros_diario_pct=juros_diario_pct,
            carencia_dias=carencia_dias,
        )

        qr_key = f"pix/{charge_id}/qr.png"
        await self._storage.put(qr_key, charge_data.qr_png_bytes, "image/png")

        now = datetime.now(UTC)
        charge = PixCharge(
            id=charge_id,
            tenant_id=parcela.tenant_id,
            parcela_payment_id=parcela.id,
            txid=txid,
            brcode=charge_data.brcode,
            qrcode_png_key=qr_key,
            amount=charge_data.amount,
            expires_at=charge_data.expires_at,
            status=PixChargeStatus.pending,
            provider_payload_json=charge_data.provider_payload,
            criado_em=now,
            atualizado_em=now,
        )
        self._s.add(charge)
        parcela.last_pix_charge_id = charge_id
        await self._s.commit()
        return charge, True

    async def create_charge_for_parcela(
        self, parcela_payment_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Customer/staff-facing entry point. Verifies ownership, delegates to
        _ensure_charge (idempotent), notifies only on fresh creation."""
        parcela = await self._s.get(ParcelaPayment, parcela_payment_id)
        if parcela is None or parcela.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if ctx.client_id is not None:
            proposal = await self._s.get(Proposal, parcela.proposal_id)
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if parcela.status not in (ParcelaPaymentStatus.open, ParcelaPaymentStatus.overdue):
            raise ValidationError("parcela must be open or overdue to pay")

        charge, created = await self._ensure_charge(parcela)
        qr_url = await self._storage.signed_url(charge.qrcode_png_key, expires_in=1800)

        if created:
            try:
                from finacialsim_saas.notifications.service import NotificationService
                proposal_obj = await self._s.get(Proposal, parcela.proposal_id)
                if proposal_obj is not None:
                    sim_obj = await self._s.get(Simulation, proposal_obj.simulation_id)
                    if sim_obj is not None and sim_obj.client_id is not None:
                        cu_result = await self._s.execute(
                            select(User).where(
                                User.client_id == sim_obj.client_id,
                                User.role == Role.customer,
                                User.is_active.is_(True),
                            )
                        )
                        customer = cu_result.scalar_one_or_none()
                        if customer and "@" in (customer.email or ""):
                            pix_url = await self._storage.signed_url(charge.qrcode_png_key, expires_in=1800)
                            await NotificationService(self._s).enqueue(
                                template_key="portal.pix_link",
                                payload={
                                    "user_name": customer.name,
                                    "valor_parcela": str(parcela.valor_parcela),
                                    "parcela_num": parcela.parcela_num,
                                    "pix_url": pix_url,
                                },
                                target_email=customer.email,
                                tenant_id=ctx.tenant_id,
                                idempotency_key=f"portal.pix_link:{parcela_payment_id}",
                            )
            except Exception as exc:
                logger.warning("pix_link notification failed", exc=str(exc))

        return charge, qr_url

    async def handle_webhook(self, headers: dict[str, str], query_params: dict, body: bytes) -> None:
        """Logs every payload. Verifies HMAC. Processes paid events idempotently."""
        now = datetime.now(UTC)

        try:
            body_json: dict[str, Any] = json.loads(body)
        except Exception:
            body_json = {"_raw": body.decode("utf-8", errors="replace")[:500]}

        # Verify signature
        try:
            event = self._provider.verify_webhook(headers, query_params, body)
            signature_valid = True
        except Exception as exc:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=False,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error=str(exc)[:200],
                )
            )
            await self._s.commit()
            return

        if event.status != "paid":
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error=f"unhandled status: {event.status}",
                )
            )
            await self._s.commit()
            return

        charge_result = await self._s.execute(
            select(PixCharge).where(PixCharge.txid == event.txid)
        )
        charge = charge_result.scalar_one_or_none()

        if charge is None:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error="charge not found",
                )
            )
            await self._s.commit()
            return

        # Idempotency: already processed?
        if charge.status == PixChargeStatus.paid:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error="already processed (replay)",
                )
            )
            await self._s.commit()
            return

        # Process payment
        charge.status = PixChargeStatus.paid
        charge.atualizado_em = now

        parcela = await self._s.get(ParcelaPayment, charge.parcela_payment_id)
        if parcela is not None:
            parcela.status = ParcelaPaymentStatus.paid
            parcela.paid_at = now
            parcela.paid_amount = event.paid_amount or charge.amount
            parcela.last_pix_charge_id = charge.id

        self._s.add(
            AuditLog(
                tenant_id=charge.tenant_id,
                acao="parcela_paga",
                entidade="parcela_payments",
                entidade_id=charge.parcela_payment_id,
                diff_json={
                    "txid": event.txid,
                    "amount": str(event.paid_amount or charge.amount),
                },
            )
        )
        self._s.add(
            PixWebhookEvent(
                received_at=now,
                signature_valid=True,
                headers_json=dict(headers),
                body_json=body_json,
                processed=True,
                processed_at=now,
            )
        )

        # Notify customer: payment confirmed
        if parcela is not None:
            try:
                from finacialsim_saas.notifications.service import NotificationService
                proposal_obj = await self._s.get(Proposal, parcela.proposal_id)
                if proposal_obj is not None:
                    sim_obj = await self._s.get(Simulation, proposal_obj.simulation_id)
                    if sim_obj is not None and sim_obj.client_id is not None:
                        cu_result = await self._s.execute(
                            select(User).where(
                                User.client_id == sim_obj.client_id,
                                User.role == Role.customer,
                            )
                        )
                        customer = cu_result.scalar_one_or_none()
                        if customer and "@" in (customer.email or ""):
                            await NotificationService(self._s).enqueue(
                                template_key="portal.parcela_paid",
                                payload={
                                    "user_name": customer.name,
                                    "valor_pago": str(parcela.paid_amount or charge.amount),
                                    "parcela_num": parcela.parcela_num,
                                },
                                target_email=customer.email,
                                tenant_id=parcela.tenant_id,
                                idempotency_key=f"portal.parcela_paid:{parcela.id}",
                            )
            except Exception as exc:
                logger.warning("parcela_paid notification failed", exc=str(exc))

        await self._s.commit()

    async def get_charge(
        self, charge_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Lazy-flips expiry, returns charge + signed QR URL."""
        charge = await self._s.get(PixCharge, charge_id)
        if charge is None or charge.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"pix charge {charge_id} not found")

        # Verify customer ownership if customer role
        if ctx.client_id is not None:
            parcela = await self._s.get(ParcelaPayment, charge.parcela_payment_id)
            proposal = await self._s.get(Proposal, parcela.proposal_id) if parcela else None
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"pix charge {charge_id} not found")

        await self._lazy_flip_expired(charge)
        if charge.status == PixChargeStatus.expired:
            await self._s.commit()

        qr_url = await self._storage.signed_url(charge.qrcode_png_key, expires_in=1800)
        return charge, qr_url

    async def cancel_charges_for_proposal(self, proposal_id: uuid.UUID) -> None:
        """Cancel all pending charges for all parcelas of a proposal."""
        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment).where(
                    ParcelaPayment.proposal_id == proposal_id,
                    ParcelaPayment.last_pix_charge_id.isnot(None),
                )
            )
        )
        now = datetime.now(UTC)
        for parcela in parcelas:
            charge = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if charge is not None and charge.status == PixChargeStatus.pending:
                try:
                    await self._provider.cancel_charge(charge.txid)
                except Exception:
                    pass
                charge.status = PixChargeStatus.canceled
                charge.atualizado_em = now
        await self._s.flush()
