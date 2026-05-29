"""VehicleService — placa validation + create methods."""
from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import Simulation, Vehicle
from app.integrations.fipe.schema import VehicleQuote
from app.services.audit_service import AuditService

_PLACA_RE = re.compile(r"^[A-Z]{3}[0-9]{4}$|^[A-Z]{3}[0-9][A-Z][0-9]{2}$")


class VehicleServiceError(Exception):
    pass


def _normalize_placa(placa: str) -> str:
    return placa.upper().replace("-", "").replace(" ", "")


class VehicleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def _validate_placa(self, placa: str | None) -> str | None:
        if not placa or not placa.strip():
            return None
        normalized = _normalize_placa(placa)
        if not _PLACA_RE.match(normalized):
            raise VehicleServiceError(
                f"Placa '{placa}' inválida. Use ABC1234 (antigo) ou ABC1D23 (Mercosul)."
            )
        return normalized

    def _check_placa_unique(self, placa: str | None, exclude_id: int | None = None) -> None:
        if placa is None:
            return
        q = self.session.query(Vehicle).filter(
            Vehicle.placa == placa,
            Vehicle.status != "vendido",
        )
        if exclude_id is not None:
            q = q.filter(Vehicle.id != exclude_id)
        if q.first() is not None:
            raise VehicleServiceError(f"Placa '{placa}' já cadastrada em veículo ativo.")

    def create_from_fipe(
        self,
        quote: VehicleQuote,
        cor: str | None,
        placa: str | None,
        odometro_km: int | None,
        valor_referencia: Decimal,
        criado_por: int,
    ) -> Vehicle:
        placa = self._validate_placa(placa)
        self._check_placa_unique(placa)
        v = Vehicle(
            fonte=quote.fonte,
            tipo=quote.tipo,
            marca=quote.marca,
            modelo=quote.modelo,
            ano_modelo=quote.ano_modelo,
            combustivel=quote.combustivel,
            codigo_fipe=quote.codigo_fipe,
            valor_fipe=quote.valor,
            valor_referencia=valor_referencia,
            mes_referencia_fipe=quote.mes_referencia,
            cor=cor,
            placa=placa,
            odometro_km=odometro_km,
            status="disponivel",
            criado_por=criado_por,
        )
        self.session.add(v)
        self.session.commit()
        self.audit.log(
            usuario_id=criado_por, acao="veiculo_criado",
            entidade="vehicles", entidade_id=v.id,
        )
        return v

    def create_manual(
        self,
        tipo: str,
        marca: str,
        modelo: str,
        ano_modelo: int,
        combustivel: str,
        valor_referencia: Decimal,
        cor: str | None,
        placa: str | None,
        odometro_km: int | None,
        criado_por: int,
    ) -> Vehicle:
        placa = self._validate_placa(placa)
        self._check_placa_unique(placa)
        v = Vehicle(
            fonte="manual_cadastro",
            tipo=tipo,
            marca=marca,
            modelo=modelo,
            ano_modelo=ano_modelo,
            combustivel=combustivel,
            valor_referencia=valor_referencia,
            cor=cor,
            placa=placa,
            odometro_km=odometro_km,
            status="disponivel",
            criado_por=criado_por,
        )
        self.session.add(v)
        self.session.commit()
        self.audit.log(
            usuario_id=criado_por, acao="veiculo_criado",
            entidade="vehicles", entidade_id=v.id,
        )
        return v

    def set_status(self, vehicle_id: int, status: str, usuario_id: int | None = None) -> Vehicle:
        if status not in ("disponivel", "reservado", "vendido"):
            raise VehicleServiceError(f"Status '{status}' inválido.")
        v = self.session.get(Vehicle, vehicle_id)
        if v is None:
            raise VehicleServiceError(f"Veículo {vehicle_id} não encontrado.")
        v.status = status
        self.session.commit()
        self.audit.log(
            usuario_id=usuario_id, acao="veiculo_status",
            entidade="vehicles", entidade_id=vehicle_id,
        )
        return v

    def update(self, vehicle_id: int, fields: dict, usuario_id: int | None = None) -> Vehicle:
        v = self.session.get(Vehicle, vehicle_id)
        if v is None:
            raise VehicleServiceError(f"Veículo {vehicle_id} não encontrado.")
        allowed = {"cor", "placa", "odometro_km", "valor_referencia"}
        if "placa" in fields:
            fields["placa"] = self._validate_placa(fields["placa"])
            self._check_placa_unique(fields["placa"], exclude_id=vehicle_id)
        for k, val in fields.items():
            if k in allowed:
                setattr(v, k, val)
        self.session.commit()
        self.audit.log(
            usuario_id=usuario_id, acao="veiculo_editado",
            entidade="vehicles", entidade_id=vehicle_id,
        )
        return v

    def refresh_fipe(self, vehicle_id: int, quote: VehicleQuote, usuario_id: int | None = None) -> Vehicle:
        v = self.session.get(Vehicle, vehicle_id)
        if v is None:
            raise VehicleServiceError(f"Veículo {vehicle_id} não encontrado.")
        v.valor_fipe = quote.valor
        v.mes_referencia_fipe = quote.mes_referencia
        self.session.commit()
        self.audit.log(
            usuario_id=usuario_id, acao="veiculo_fipe_atualizado",
            entidade="vehicles", entidade_id=vehicle_id,
        )
        return v

    def list_active(self, search: str = "") -> list[Vehicle]:
        from sqlalchemy import or_
        q = self.session.query(Vehicle).filter(
            Vehicle.status.in_(["disponivel", "reservado"]),
            Vehicle.fonte != "manual",
        )
        if search:
            like = f"%{search}%"
            q = q.filter(or_(
                Vehicle.marca.ilike(like),
                Vehicle.modelo.ilike(like),
                Vehicle.placa.ilike(like),
                Vehicle.cor.ilike(like),
            ))
        return q.order_by(Vehicle.marca, Vehicle.modelo, Vehicle.ano_modelo).all()

    def list_all(self, status_filter: str | None = None, search: str = "") -> list[Vehicle]:
        from sqlalchemy import or_
        q = self.session.query(Vehicle).filter(Vehicle.fonte != "manual")
        if status_filter:
            q = q.filter(Vehicle.status == status_filter)
        if search:
            like = f"%{search}%"
            q = q.filter(or_(
                Vehicle.marca.ilike(like),
                Vehicle.modelo.ilike(like),
                Vehicle.placa.ilike(like),
                Vehicle.cor.ilike(like),
            ))
        return q.order_by(Vehicle.marca, Vehicle.modelo, Vehicle.ano_modelo).all()

    def get_simulations(self, vehicle_id: int) -> list[Simulation]:
        return (
            self.session.query(Simulation)
            .filter(Simulation.veiculo_id == vehicle_id)
            .order_by(Simulation.criado_em.desc())
            .all()
        )
