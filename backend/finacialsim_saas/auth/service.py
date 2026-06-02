from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import bcrypt
import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import (
    AuditLog, NotificationsOutbox, PasswordResetToken,
    RefreshToken, Role, User,
)
from finacialsim_saas.errors import AuthError, ConflictError
from finacialsim_saas.settings import Settings

if TYPE_CHECKING:
    from finacialsim_saas.auth.deps import RequestContext


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._s = session
        self._cfg = settings

    # ── internal helpers ──────────────────────────────────────────────────────

    def _hash_pw(self, pw: str) -> str:
        return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()

    def _check_pw(self, pw: str, hashed: str) -> bool:
        return bcrypt.checkpw(pw.encode(), hashed.encode())

    def _hash_token(self, raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def _make_access_jwt(self, user: User) -> str:
        now = datetime.now(timezone.utc)
        payload: dict = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(minutes=self._cfg.access_token_expire_minutes),
        }
        if user.client_id is not None:
            payload["client_id"] = str(user.client_id)
        return jwt.encode(payload, self._cfg.jwt_secret_key, algorithm="HS256")

    # ── public API ────────────────────────────────────────────────────────────

    async def register_user(
        self,
        *,
        tenant_id: uuid.UUID,
        email: str,
        password: str,
        name: str,
        role: Role,
        ctx: "RequestContext | None" = None,
    ) -> User:
        existing = await self._s.execute(
            select(User).where(User.email == email, User.role != Role.customer)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"Email {email!r} already registered")
        user = User(
            tenant_id=tenant_id, email=email, name=name,
            password_hash=self._hash_pw(password), role=role,
        )
        self._s.add(user)
        await self._s.flush()
        if ctx is not None:
            from finacialsim_saas.services.audit_service import AuditService
            audit = AuditService(self._s)
            await audit.log(
                "create", "user", user.id,
                {"before": None, "after": {"email": user.email, "name": user.name, "role": user.role.value}},
                ctx,
            )
        return user

    async def authenticate(self, email: str, password: str) -> User:
        # Search staff users first (globally unique email)
        result = await self._s.execute(
            select(User).where(User.email == email, User.role != Role.customer)
        )
        user = result.scalar_one_or_none()
        if user is None:
            # Try customer users (unique per tenant, first match wins)
            result = await self._s.execute(
                select(User).where(User.email == email, User.role == Role.customer)
            )
            user = result.scalars().first()
        if user is None or not self._check_pw(password, user.password_hash):
            raise AuthError("Invalid credentials")
        if not user.is_active:
            raise AuthError("Account disabled")
        return user

    async def issue_tokens(
        self, user: User, family_id: uuid.UUID | None = None
    ) -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        rt = RefreshToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=self._hash_token(raw),
            family_id=family_id or uuid.uuid4(),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=self._cfg.refresh_token_expire_days),
        )
        self._s.add(rt)
        return self._make_access_jwt(user), raw

    async def rotate_refresh(self, raw_token: str) -> tuple[User, str, str]:
        th = self._hash_token(raw_token)
        result = await self._s.execute(
            select(RefreshToken).where(RefreshToken.token_hash == th)
        )
        rt = result.scalar_one_or_none()
        if rt is None:
            raise AuthError("Invalid refresh token")

        now = datetime.now(timezone.utc)

        if rt.revoked_at is not None:
            await self._s.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == rt.family_id)
                .values(revoked_at=now)
            )
            raise AuthError("Refresh token reuse detected — session revoked")

        if rt.expires_at.replace(tzinfo=timezone.utc) < now:
            raise AuthError("Refresh token expired")

        user_result = await self._s.execute(select(User).where(User.id == rt.user_id))
        user = user_result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise AuthError("User not found or inactive")

        rt.revoked_at = now
        new_access, new_refresh = await self.issue_tokens(user, family_id=rt.family_id)
        return user, new_access, new_refresh

    async def revoke_all(self, user: User) -> None:
        user.tokens_revoked_at = datetime.now(timezone.utc)

    async def request_password_reset(self, email: str) -> None:
        result = await self._s.execute(
            select(User).where(User.email == email, User.role != Role.customer)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return  # silent — don't leak user existence

        now = datetime.now(timezone.utc)
        await self._s.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

        raw = secrets.token_urlsafe(32)
        prt = PasswordResetToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=self._hash_token(raw),
            expires_at=now + timedelta(minutes=30),
        )
        self._s.add(prt)

        reset_url = f"{self._cfg.frontend_base_url}/reset-password/{raw}"
        self._s.add(
            NotificationsOutbox(
                tenant_id=user.tenant_id,
                template_key="password_reset",
                target_email=user.email,
                payload_json={"reset_url": reset_url, "user_name": user.name},
            )
        )

    async def confirm_password_reset(self, raw_token: str, new_password: str) -> None:
        th = self._hash_token(raw_token)
        result = await self._s.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == th)
        )
        prt = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if prt is None or prt.used_at is not None:
            raise AuthError("Invalid or already-used reset token")
        if prt.expires_at.replace(tzinfo=timezone.utc) < now:
            raise AuthError("Reset token expired")

        user_result = await self._s.execute(select(User).where(User.id == prt.user_id))
        user = user_result.scalar_one()
        user.password_hash = self._hash_pw(new_password)
        user.tokens_revoked_at = now
        prt.used_at = now

    async def invite_customer(
        self,
        client_id: uuid.UUID,
        ctx: "RequestContext",
        *,
        proposal_id: uuid.UUID | None = None,
    ) -> User:
        from finacialsim_saas.data.models import Client
        from finacialsim_saas.errors import NotFoundError

        client = await self._s.get(Client, client_id)
        if client is None or client.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"client {client_id} not found")

        # Find or create customer user
        result = await self._s.execute(
            select(User).where(
                User.client_id == client_id,
                User.role == Role.customer,
                User.tenant_id == ctx.tenant_id,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            email = client.email or f"customer-{str(client_id)[:8]}@placeholder.invalid"
            user = User(
                tenant_id=ctx.tenant_id,
                email=email,
                name=client.nome,
                password_hash="!unusable",
                role=Role.customer,
                client_id=client_id,
                is_active=True,
            )
            self._s.add(user)
            await self._s.flush()

        # Invalidate any existing active reset tokens
        now = datetime.now(timezone.utc)
        await self._s.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

        # Issue new 72h token
        raw = secrets.token_urlsafe(32)
        prt = PasswordResetToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=self._hash_token(raw),
            expires_at=now + timedelta(hours=72),
        )
        self._s.add(prt)

        # Write outbox
        payload: dict = {"user_id": str(user.id)}
        if proposal_id is not None:
            payload["proposal_id"] = str(proposal_id)
        self._s.add(
            NotificationsOutbox(
                tenant_id=ctx.tenant_id,
                template_key="customer_invite",
                target_email=user.email,
                payload_json=payload,
            )
        )
        return user

    async def re_invite(self, client_id: uuid.UUID, ctx: "RequestContext") -> User:
        from finacialsim_saas.errors import NotFoundError

        result = await self._s.execute(
            select(User).where(
                User.client_id == client_id,
                User.role == Role.customer,
                User.tenant_id == ctx.tenant_id,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"no customer user for client {client_id}")
        return await self.invite_customer(client_id, ctx)

    async def write_audit(
        self,
        *,
        tenant_id: uuid.UUID,
        usuario_id: uuid.UUID | None,
        acao: str,
        entidade: str | None = None,
        entidade_id: uuid.UUID | None = None,
        diff_json: dict | None = None,
    ) -> None:
        self._s.add(
            AuditLog(
                tenant_id=tenant_id,
                usuario_id=usuario_id,
                acao=acao,
                entidade=entidade,
                entidade_id=entidade_id,
                diff_json=diff_json,
            )
        )
