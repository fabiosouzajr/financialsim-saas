import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_all_phase1_models_importable_and_tables_exist(session):
    from finacialsim_saas.data.models import (
        AuditLog, NotificationsOutbox, PasswordResetToken,
        RefreshToken, Tenant, User,
    )
    for Model in (Tenant, User, PasswordResetToken, RefreshToken, AuditLog, NotificationsOutbox):
        result = await session.execute(select(Model))
        assert result.scalars().all() == []
