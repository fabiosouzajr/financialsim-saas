from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, ParcelaPayment, ParcelaPaymentStatus, PixCharge,
    PixChargeStatus, PixWebhookEvent, Proposal, Simulation,
)
from finacialsim_saas.errors import NotFoundError, ValidationError
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.storage import StorageBackend

UTC = timezone.utc


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

    async def create_charge_for_parcela(
        self, parcela_payment_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Idempotent. Returns (charge, signed_qr_url). TTL 30 min."""
        parcela = await self._s.get(ParcelaPayment, parcela_payment_id)
        if parcela is None or parcela.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        # Verify customer ownership
        if ctx.client_id is not None:
            proposal = await self._s.get(Proposal, parcela.proposal_id)
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if parcela.status not in (ParcelaPaymentStatus.open, ParcelaPaymentStatus.overdue):
            raise ValidationError("parcela must be open or overdue to pay")

        # Check for existing pending charge (lazy-flip expired first)
        if parcela.last_pix_charge_id is not None:
            existing = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if existing is not None:
                await self._lazy_flip_expired(existing)
                if existing.status == PixChargeStatus.pending:
                    await self._s.flush()
                    qr_url = await self._storage.signed_url(existing.qrcode_png_key, expires_in=1800)
                    return existing, qr_url

        # Create new charge
        charge_id = uuid.uuid4()
        txid = str(charge_id).replace("-", "")[:35]

        charge_data = await self._provider.create_charge(
            txid=txid,
            amount=parcela.valor_parcela,
            expires_in=1800,
            description=f"Parcela {parcela.parcela_num}",
            payer="",
        )

        qr_key = f"pix/{charge_id}/qr.png"
        await self._storage.put(qr_key, charge_data.qr_png_bytes, "image/png")

        now = datetime.now(UTC)
        charge = PixCharge(
            id=charge_id,
            tenant_id=ctx.tenant_id,
            parcela_payment_id=parcela_payment_id,
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

        qr_url = await self._storage.signed_url(qr_key, expires_in=1800)
        return charge, qr_url

    async def handle_webhook(self, headers: dict[str, str], body: bytes) -> None:
        """Logs every payload. Verifies HMAC. Processes paid events idempotently."""
        now = datetime.now(UTC)

        try:
            body_json: dict[str, Any] = json.loads(body)
        except Exception:
            body_json = {"_raw": body.decode("utf-8", errors="replace")[:500]}

        # Verify signature
        try:
            event = self._provider.verify_webhook(headers, body)
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
