"""Integration tests: every CUD operation produces a correct audit_log entry."""
import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import AuditLog, Role, Tenant, User
from finacialsim_saas.settings import get_settings


async def _make_tenant_admin(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    t = Tenant(name=f"BF-{uuid.uuid4().hex[:6]}", slug=f"bf-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, get_settings())
    user = await svc.register_user(
        tenant_id=t.id,
        email=f"adm-{uuid.uuid4().hex[:6]}@test.com",
        password="pw", name="Admin", role=Role.admin,
    )
    await session.flush()
    return t.id, user.id


async def test_register_user_creates_audit_entry(session: AsyncSession):
    from finacialsim_saas.auth.service import AuthService

    t = Tenant(name=f"Au-{uuid.uuid4().hex[:6]}", slug=f"au-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()

    creator_id = uuid.uuid4()
    ctx = RequestContext(user_id=creator_id, tenant_id=t.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())
    new_user = await svc.register_user(
        tenant_id=t.id,
        email=f"new-{uuid.uuid4().hex[:6]}@test.com",
        password="pw", name="New", role=Role.user,
        ctx=ctx,
    )
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog).where(
            AuditLog.tenant_id == t.id,
            AuditLog.acao == "create",
            AuditLog.entidade == "user",
        )
    )).all()
    assert len(logs) == 1
    assert logs[0].diff_json["after"]["email"] == new_user.email


async def test_client_create_update_deactivate_audit(session: AsyncSession):
    from finacialsim_saas.services.client_service import ClientService
    from finacialsim_saas.schemas.clients import ClientIn

    tenant_id, user_id = await _make_tenant_admin(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = ClientService(session)

    client = await svc.create(
        ClientIn(
            nome="João Silva",
            cpf_cnpj="529.982.247-25",
            tipo="pf",
        ),
        ctx,
    )
    await session.flush()

    await svc.update(client.id, ClientIn(nome="João S. Updated", cpf_cnpj="529.982.247-25", tipo="pf"), ctx)
    await session.flush()

    await svc.deactivate(client.id, ctx)
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.entidade == "client")
        .order_by(AuditLog.timestamp.asc())
    )).all()

    assert len(logs) == 3
    assert logs[0].acao == "create"
    assert logs[0].diff_json["before"] is None
    assert logs[1].acao == "update"
    assert logs[1].diff_json["before"] is not None
    assert logs[2].acao == "deactivate"


async def test_vehicle_create_update_status_audit(session: AsyncSession):
    from finacialsim_saas.services.vehicle_service import VehicleService
    from finacialsim_saas.schemas.vehicles import VehicleIn

    tenant_id, user_id = await _make_tenant_admin(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = VehicleService(session)

    vehicle = await svc.create(
        VehicleIn(
            fonte="manual",
            tipo="carro",
            marca="Toyota",
            modelo="Corolla",
            ano_modelo=2023,
            valor_referencia="120000.00",
        ),
        ctx,
    )
    await session.flush()

    await svc.set_status(vehicle.id, "reservado", ctx)
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.entidade == "vehicle")
        .order_by(AuditLog.timestamp.asc())
    )).all()

    assert len(logs) == 2
    assert logs[0].acao == "create"
    assert logs[0].diff_json["before"] is None
    assert logs[1].acao == "set_status"
    assert logs[1].diff_json["after"]["status"] == "reservado"


async def test_simulation_create_archive_audit(session: AsyncSession):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.cli.main import _seed_business_rules
    from finacialsim_saas.data.models import Client, ClientType, Vehicle, VehicleStatus
    from finacialsim_saas.schemas.simulations import SimulationCreate
    from finacialsim_saas.services.simulation_service import SimulationService

    t = Tenant(name=f"Sim-{uuid.uuid4().hex[:6]}", slug=f"sim-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()

    svc_auth = AuthService(session, get_settings())
    user = await svc_auth.register_user(
        tenant_id=t.id,
        email=f"u-{uuid.uuid4().hex[:6]}@test.com",
        password="pw", name="User", role=Role.user,
    )
    await session.flush()

    await _seed_business_rules(session, t.id)
    await session.flush()

    cl = Client(
        tenant_id=t.id, nome="Test", cpf_cnpj="52998224725",
        tipo=ClientType.pf, criado_por=user.id,
    )
    session.add(cl)
    v = Vehicle(
        tenant_id=t.id, fonte="fipe_parallelum", tipo="carro",
        marca="Toyota", modelo="Corolla", ano_modelo=2023,
        status=VehicleStatus.ativo, criado_por=user.id,
    )
    session.add(v)
    await session.flush()

    ctx = RequestContext(user_id=user.id, tenant_id=t.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)

    sim = await svc.create(
        SimulationCreate(
            client_id=cl.id,
            vehicle_id=v.id,
            valor_veiculo="50000.00",
            valor_entrada="10000.00",
            taxa_mensal="0.0199",
            prazo_meses=24,
            data_liberacao=date(2026, 6, 1),
            primeiro_vencimento=date(2026, 7, 1),
            incluir_iof=False,
        ),
        ctx,
    )
    await session.flush()

    await svc.archive(sim.id, ctx)
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == t.id, AuditLog.entidade == "simulation")
        .order_by(AuditLog.timestamp.asc())
    )).all()

    assert len(logs) == 2
    assert logs[0].acao == "create"
    assert logs[0].diff_json["before"] is None
    assert logs[0].diff_json["after"]["codigo"] == sim.codigo
    assert logs[1].acao == "archive"
    assert logs[1].diff_json["after"]["status"] == "arquivado"
