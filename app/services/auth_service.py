"""AuthService - PIN-based authentication with bcrypt and lockout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy.orm import Session

from app.data.models import User
from app.data.repositories import UserRepository
from app.services.audit_service import AuditService


class AuthError(Exception):
    """Raised on login failure or PIN-related issues."""


_LOCKOUT_ATTEMPTS = 5
_LOCKOUT_MINUTES = 5

# In-memory failed-attempts tracker (process-local).
# Resets on restart — acceptable for single-PC kiosk threat model.
_failed: dict[int, list[datetime]] = {}


def hash_pin(pin: str) -> str:
    if not (4 <= len(pin) <= 6) or not pin.isdigit():
        raise AuthError("PIN must be 4 to 6 digits")
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


def _check_lockout(user_id: int) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    recent = [t for t in _failed.get(user_id, []) if t > now - timedelta(minutes=_LOCKOUT_MINUTES)]
    _failed[user_id] = recent
    if len(recent) >= _LOCKOUT_ATTEMPTS:
        raise AuthError(f"Conta bloqueada por {_LOCKOUT_MINUTES} minutos apos falhas consecutivas")


def _record_failure(user_id: int) -> None:
    _failed.setdefault(user_id, []).append(datetime.now(UTC).replace(tzinfo=None))


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    def list_users(self) -> list[User]:
        return self.users.list_active()

    def create_user(self, nome: str, pin: str, perfil: str) -> User:
        if perfil not in {"vendedor", "gerente", "admin"}:
            raise AuthError(f"Perfil invalido: {perfil}")
        u = self.users.create(nome=nome, pin_hash=hash_pin(pin), perfil=perfil)
        self.audit.log(usuario_id=u.id, acao="usuario_criado", entidade="users", entidade_id=u.id)
        return u

    def login(self, user_id: int, pin: str) -> User:
        _check_lockout(user_id)
        u = self.users.get(user_id)
        if u is None or not u.ativo:
            _record_failure(user_id)
            raise AuthError("Usuario nao encontrado ou inativo")
        if not verify_pin(pin, u.pin_hash):
            _record_failure(user_id)
            raise AuthError("PIN incorreto")
        u.ultimo_login = datetime.now(UTC).replace(tzinfo=None)
        self.session.commit()
        _failed.pop(user_id, None)
        self.audit.log(usuario_id=u.id, acao="login")
        return u

    def change_pin(self, user_id: int, old_pin: str, new_pin: str) -> None:
        u = self.users.get(user_id)
        if u is None:
            raise AuthError("Usuario nao encontrado")
        if not verify_pin(old_pin, u.pin_hash):
            raise AuthError("PIN atual incorreto")
        u.pin_hash = hash_pin(new_pin)
        self.session.commit()
        self.audit.log(usuario_id=u.id, acao="pin_alterado")
