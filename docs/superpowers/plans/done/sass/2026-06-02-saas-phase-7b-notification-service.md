# Phase 7B — Notification Service + Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `NotificationService` (outbox enqueue), `EmailChannel` (aiosmtplib SMTP delivery), and Jinja2 templates for all 7 template keys. Write split test modules.

**Architecture:** `notifications/service.py` has `NotificationService.enqueue()` which writes an outbox row in the caller's transaction. `notifications/channel.py` has `EmailChannel.send()` using `aiosmtplib`. Templates live at `notifications/templates/<namespace>/<action>/{subject.txt,body.html,body.txt}`. Template keys use dots (`auth.password_reset`) mapped to directory paths (`auth/password_reset/`).

**Tech Stack:** aiosmtplib, Jinja2 (already in dependencies), SQLAlchemy dialects.postgresql for `ON CONFLICT DO NOTHING`, Python 3.12

**Depends on:** Phase 7A (migration 008 applied, new NotificationsOutbox model)

---

## File Map

| Action | File |
|--------|------|
| Modify | `backend/pyproject.toml` — add `aiosmtplib` dependency |
| Modify | `backend/finacialsim_saas/settings.py` — add SMTP + notification settings |
| Create | `backend/finacialsim_saas/notifications/__init__.py` |
| Create | `backend/finacialsim_saas/notifications/service.py` |
| Create | `backend/finacialsim_saas/notifications/channel.py` |
| Create | `backend/finacialsim_saas/notifications/templates/auth/password_reset/{subject.txt,body.html,body.txt}` |
| Create | `backend/finacialsim_saas/notifications/templates/auth/user_invite/{subject.txt,body.html,body.txt}` |
| Create | `backend/finacialsim_saas/notifications/templates/portal/customer_invite/{subject.txt,body.html,body.txt}` |
| Create | `backend/finacialsim_saas/notifications/templates/portal/pix_link/{subject.txt,body.html,body.txt}` |
| Create | `backend/finacialsim_saas/notifications/templates/portal/parcela_due_soon/{subject.txt,body.html,body.txt}` |
| Create | `backend/finacialsim_saas/notifications/templates/portal/parcela_paid/{subject.txt,body.html,body.txt}` |
| Create | `backend/finacialsim_saas/notifications/templates/portal/parcela_overdue/{subject.txt,body.html,body.txt}` |
| Create | `backend/tests/test_notification_templates.py` |
| Create | `backend/tests/test_notification_service.py` |

---

### Task 1: Add aiosmtplib dependency and SMTP settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/finacialsim_saas/settings.py`

- [ ] **Step 1: Add aiosmtplib to pyproject.toml**

In `backend/pyproject.toml`, add to the `dependencies` list (after `jinja2`):

```toml
    "aiosmtplib>=3.0.0",
```

- [ ] **Step 2: Install**

```bash
cd backend && uv sync --extra dev
```

Expected: No errors. `aiosmtplib` appears in the lockfile.

- [ ] **Step 3: Add SMTP and notification settings to Settings**

In `backend/finacialsim_saas/settings.py`, add these fields to the `Settings` class (after `pix_webhook_secret`):

```python
    # Email delivery
    email_provider: str = "smtp"  # smtp | ses | resend
    smtp_host: str = "localhost"
    smtp_port: int = 1025          # Mailpit default
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False
    smtp_from: str = "noreply@finacialsim.local"

    max_emails_per_tenant_per_hour: int = 1000  # enforcement deferred to v2
```

- [ ] **Step 4: Verify settings load**

```bash
cd backend && uv run python -c "from finacialsim_saas.settings import get_settings; s = get_settings(); print(s.smtp_host)"
```

Expected: `localhost`

---

### Task 2: Write failing template tests

**Files:**
- Create: `backend/tests/test_notification_templates.py`

- [ ] **Step 1: Create test file**

```python
"""Tests that every template key renders without error and contains expected strings."""
import pytest
from pathlib import Path

TEMPLATES_DIR = (
    Path(__file__).parent.parent
    / "finacialsim_saas" / "notifications" / "templates"
)

TEMPLATE_CASES = [
    (
        "auth/password_reset",
        {"reset_url": "https://app.example.com/reset-password/abc123", "user_name": "João"},
        ["redefinição", "senha", "abc123"],
        ["João"],
    ),
    (
        "auth/user_invite",
        {"user_name": "Maria", "login_url": "https://app.example.com/login", "tenant_name": "Loja ABC"},
        ["bem-vindo", "Maria", "Loja ABC"],
        [],
    ),
    (
        "portal/customer_invite",
        {
            "user_name": "Carlos",
            "portal_url": "https://app.example.com/portal/login",
            "tenant_name": "Loja ABC",
        },
        ["Carlos", "portal"],
        [],
    ),
    (
        "portal/pix_link",
        {
            "user_name": "Ana",
            "valor_parcela": "R$ 1.234,56",
            "parcela_num": 3,
            "pix_url": "https://app.example.com/portal/financiamento/abc",
        },
        ["Ana", "Pix", "1.234,56"],
        [],
    ),
    (
        "portal/parcela_due_soon",
        {
            "user_name": "Pedro",
            "valor_parcela": "R$ 987,65",
            "parcela_num": 5,
            "vencimento": "2026-06-10",
        },
        ["Pedro", "vencimento", "987,65"],
        [],
    ),
    (
        "portal/parcela_paid",
        {
            "user_name": "Lucia",
            "valor_pago": "R$ 500,00",
            "parcela_num": 2,
        },
        ["Lucia", "pago", "500,00"],
        [],
    ),
    (
        "portal/parcela_overdue",
        {
            "user_name": "Roberto",
            "valor_parcela": "R$ 800,00",
            "parcela_num": 1,
            "dias_atraso": 5,
        },
        ["Roberto", "vencida", "800,00"],
        [],
    ),
]


@pytest.mark.parametrize("key_path,payload,body_contains,subject_contains", TEMPLATE_CASES)
def test_template_renders(key_path, payload, body_contains, subject_contains):
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    subject = env.get_template(f"{key_path}/subject.txt").render(**payload).strip()
    body_html = env.get_template(f"{key_path}/body.html").render(**payload)
    body_txt = env.get_template(f"{key_path}/body.txt").render(**payload)

    assert subject, f"subject.txt rendered empty for {key_path}"
    assert body_html, f"body.html rendered empty for {key_path}"
    assert body_txt, f"body.txt rendered empty for {key_path}"

    full_body = (body_html + body_txt).lower()
    for fragment in body_contains:
        assert fragment.lower() in full_body, (
            f"Expected {fragment!r} in body for {key_path}"
        )
    for fragment in subject_contains:
        assert fragment.lower() in subject.lower(), (
            f"Expected {fragment!r} in subject for {key_path}"
        )


def test_all_template_dirs_exist():
    expected = [
        "auth/password_reset",
        "auth/user_invite",
        "portal/customer_invite",
        "portal/pix_link",
        "portal/parcela_due_soon",
        "portal/parcela_paid",
        "portal/parcela_overdue",
    ]
    for key in expected:
        d = TEMPLATES_DIR / key
        assert d.is_dir(), f"Missing template directory: {d}"
        for fname in ("subject.txt", "body.html", "body.txt"):
            assert (d / fname).exists(), f"Missing {fname} in {d}"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_notification_templates.py -v
```

Expected: FAIL — template directories don't exist yet.

---

### Task 3: Create template files

**Files:** 21 new template files across 7 directories

- [ ] **Step 1: auth/password_reset templates**

`backend/finacialsim_saas/notifications/templates/auth/password_reset/subject.txt`:
```
Redefinição de senha — FinacialSim
```

`backend/finacialsim_saas/notifications/templates/auth/password_reset/body.txt`:
```
Olá {{ user_name }},

Você solicitou a redefinição da sua senha no FinacialSim.

Clique no link abaixo para criar uma nova senha:
{{ reset_url }}

O link é válido por 30 minutos. Se você não solicitou essa redefinição, ignore este e-mail.

Atenciosamente,
Equipe FinacialSim
```

`backend/finacialsim_saas/notifications/templates/auth/password_reset/body.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Redefinição de senha</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2>Redefinição de senha</h2>
  <p>Olá <strong>{{ user_name }}</strong>,</p>
  <p>Você solicitou a redefinição da sua senha no FinacialSim.</p>
  <p>
    <a href="{{ reset_url }}" style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px">
      Redefinir senha
    </a>
  </p>
  <p style="color:#6b7280;font-size:13px">Link válido por 30 minutos. Se você não solicitou essa redefinição, ignore este e-mail.</p>
</body>
</html>
```

- [ ] **Step 2: auth/user_invite templates**

`backend/finacialsim_saas/notifications/templates/auth/user_invite/subject.txt`:
```
Bem-vindo ao FinacialSim — {{ tenant_name }}
```

`backend/finacialsim_saas/notifications/templates/auth/user_invite/body.txt`:
```
Olá {{ user_name }},

Sua conta foi criada no FinacialSim para a loja {{ tenant_name }}.

Acesse o sistema em:
{{ login_url }}

Use as credenciais fornecidas pelo administrador para fazer seu primeiro acesso.

Atenciosamente,
Equipe FinacialSim
```

`backend/finacialsim_saas/notifications/templates/auth/user_invite/body.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Bem-vindo ao FinacialSim</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2>Bem-vindo ao FinacialSim</h2>
  <p>Olá <strong>{{ user_name }}</strong>,</p>
  <p>Sua conta foi criada no FinacialSim para a loja <strong>{{ tenant_name }}</strong>.</p>
  <p>
    <a href="{{ login_url }}" style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px">
      Acessar sistema
    </a>
  </p>
  <p style="color:#6b7280;font-size:13px">Use as credenciais fornecidas pelo administrador.</p>
</body>
</html>
```

- [ ] **Step 3: portal/customer_invite templates**

`backend/finacialsim_saas/notifications/templates/portal/customer_invite/subject.txt`:
```
Acesse seu portal de financiamento — {{ tenant_name }}
```

`backend/finacialsim_saas/notifications/templates/portal/customer_invite/body.txt`:
```
Olá {{ user_name }},

{{ tenant_name }} liberou seu portal de acompanhamento de financiamento.

Acesse em:
{{ portal_url }}

Pelo portal você pode consultar seu financiamento e efetuar pagamentos via Pix.

Atenciosamente,
{{ tenant_name }}
```

`backend/finacialsim_saas/notifications/templates/portal/customer_invite/body.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Portal de financiamento</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2>Portal de Financiamento</h2>
  <p>Olá <strong>{{ user_name }}</strong>,</p>
  <p><strong>{{ tenant_name }}</strong> liberou seu portal de acompanhamento de financiamento.</p>
  <p>
    <a href="{{ portal_url }}" style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px">
      Acessar portal
    </a>
  </p>
  <p style="color:#6b7280;font-size:13px">Consulte seu financiamento e pague parcelas via Pix.</p>
</body>
</html>
```

- [ ] **Step 4: portal/pix_link templates**

`backend/finacialsim_saas/notifications/templates/portal/pix_link/subject.txt`:
```
Pix gerado — Parcela {{ parcela_num }} disponível para pagamento
```

`backend/finacialsim_saas/notifications/templates/portal/pix_link/body.txt`:
```
Olá {{ user_name }},

Seu Pix para a Parcela {{ parcela_num }} ({{ valor_parcela }}) foi gerado e está disponível.

Acesse o portal para efetuar o pagamento:
{{ pix_url }}

O código Pix expira em 30 minutos.

Atenciosamente,
Equipe FinacialSim
```

`backend/finacialsim_saas/notifications/templates/portal/pix_link/body.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Pix disponível</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2>Pix disponível para pagamento</h2>
  <p>Olá <strong>{{ user_name }}</strong>,</p>
  <p>Seu Pix para a <strong>Parcela {{ parcela_num }}</strong> (<strong>{{ valor_parcela }}</strong>) está disponível.</p>
  <p>
    <a href="{{ pix_url }}" style="display:inline-block;padding:12px 24px;background:#16a34a;color:#fff;text-decoration:none;border-radius:6px">
      Pagar via Pix
    </a>
  </p>
  <p style="color:#6b7280;font-size:13px">O código Pix expira em 30 minutos.</p>
</body>
</html>
```

- [ ] **Step 5: portal/parcela_due_soon templates**

`backend/finacialsim_saas/notifications/templates/portal/parcela_due_soon/subject.txt`:
```
Lembrete: Parcela {{ parcela_num }} vence em 3 dias
```

`backend/finacialsim_saas/notifications/templates/portal/parcela_due_soon/body.txt`:
```
Olá {{ user_name }},

Sua Parcela {{ parcela_num }} ({{ valor_parcela }}) vence em {{ vencimento }}.

Acesse o portal para efetuar o pagamento com antecedência:
https://app.finacialsim.com.br/portal

Atenciosamente,
Equipe FinacialSim
```

`backend/finacialsim_saas/notifications/templates/portal/parcela_due_soon/body.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Parcela vence em breve</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2>Lembrete de vencimento</h2>
  <p>Olá <strong>{{ user_name }}</strong>,</p>
  <p>Sua <strong>Parcela {{ parcela_num }}</strong> (<strong>{{ valor_parcela }}</strong>) vence em <strong>{{ vencimento }}</strong>.</p>
  <p style="color:#6b7280;font-size:13px">Acesse o portal para efetuar o pagamento com antecedência.</p>
</body>
</html>
```

- [ ] **Step 6: portal/parcela_paid templates**

`backend/finacialsim_saas/notifications/templates/portal/parcela_paid/subject.txt`:
```
Pagamento confirmado — Parcela {{ parcela_num }}
```

`backend/finacialsim_saas/notifications/templates/portal/parcela_paid/body.txt`:
```
Olá {{ user_name }},

O pagamento da sua Parcela {{ parcela_num }} ({{ valor_pago }}) foi confirmado com sucesso.

Obrigado!

Equipe FinacialSim
```

`backend/finacialsim_saas/notifications/templates/portal/parcela_paid/body.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Pagamento confirmado</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2 style="color:#16a34a">✓ Pagamento confirmado</h2>
  <p>Olá <strong>{{ user_name }}</strong>,</p>
  <p>O pagamento da <strong>Parcela {{ parcela_num }}</strong> (<strong>{{ valor_pago }}</strong>) foi confirmado com sucesso.</p>
  <p style="color:#6b7280;font-size:13px">Obrigado por manter seus pagamentos em dia!</p>
</body>
</html>
```

- [ ] **Step 7: portal/parcela_overdue templates**

`backend/finacialsim_saas/notifications/templates/portal/parcela_overdue/subject.txt`:
```
Parcela {{ parcela_num }} está vencida — regularize sua situação
```

`backend/finacialsim_saas/notifications/templates/portal/parcela_overdue/body.txt`:
```
Olá {{ user_name }},

Sua Parcela {{ parcela_num }} ({{ valor_parcela }}) está vencida há {{ dias_atraso }} dias.

Acesse o portal para regularizar sua situação:
https://app.finacialsim.com.br/portal

Entre em contato com a loja caso precise de auxílio.

Equipe FinacialSim
```

`backend/finacialsim_saas/notifications/templates/portal/parcela_overdue/body.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Parcela vencida</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2 style="color:#dc2626">Parcela vencida</h2>
  <p>Olá <strong>{{ user_name }}</strong>,</p>
  <p>Sua <strong>Parcela {{ parcela_num }}</strong> (<strong>{{ valor_parcela }}</strong>) está vencida há <strong>{{ dias_atraso }} dias</strong>.</p>
  <p>Acesse o portal para regularizar sua situação ou entre em contato com a loja.</p>
</body>
</html>
```

- [ ] **Step 8: Run template tests**

```bash
cd backend && uv run pytest tests/test_notification_templates.py -v
```

Expected: All 8 tests pass (`test_all_template_dirs_exist` + 7 parametrized `test_template_renders`).

---

### Task 4: Create EmailChannel

**Files:**
- Create: `backend/finacialsim_saas/notifications/__init__.py`
- Create: `backend/finacialsim_saas/notifications/channel.py`

- [ ] **Step 1: Create `__init__.py`**

```python
# backend/finacialsim_saas/notifications/__init__.py
```

(empty file)

- [ ] **Step 2: Create EmailChannel**

`backend/finacialsim_saas/notifications/channel.py`:

```python
from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from finacialsim_saas.settings import Settings


class EmailChannel:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def send(self, *, to: str, subject: str, body_html: str, body_txt: str) -> None:
        """Send a multipart email via SMTP. Raises on any delivery failure."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._s.smtp_from
        msg["To"] = to
        msg.attach(MIMEText(body_txt, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=self._s.smtp_host,
            port=self._s.smtp_port,
            username=self._s.smtp_user or None,
            password=self._s.smtp_password or None,
            use_tls=self._s.smtp_tls,
        )
```

---

### Task 5: Create NotificationService

**Files:**
- Create: `backend/finacialsim_saas/notifications/service.py`

- [ ] **Step 1: Write failing test for service**

Add to `backend/tests/test_notification_service.py` (create new file):

```python
"""Integration tests for NotificationService.enqueue() — DB only, no SMTP."""
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from finacialsim_saas.data.models import NotificationsOutbox
from finacialsim_saas.notifications.service import NotificationService


@pytest.fixture
async def tenant_id():
    return uuid.uuid4()


async def test_enqueue_writes_pending_row(db_session, tenant_id):
    svc = NotificationService(db_session)
    await svc.enqueue(
        template_key="auth.password_reset",
        payload={"reset_url": "https://example.com/reset/abc", "user_name": "Test"},
        target_email="test@example.com",
        tenant_id=tenant_id,
    )
    await db_session.flush()

    result = await db_session.execute(
        select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
    )
    row = result.scalar_one()
    assert row.status == "pending"
    assert row.template_key == "auth.password_reset"
    assert row.target_email == "test@example.com"
    assert row.channel == "email"
    assert row.attempts == 0
    assert row.payload_json["reset_url"] == "https://example.com/reset/abc"


async def test_enqueue_with_idempotency_key_deduplicates(db_session, tenant_id):
    svc = NotificationService(db_session)
    idem_key = f"test:{uuid.uuid4()}"

    await svc.enqueue(
        template_key="portal.parcela_due_soon",
        payload={"parcela_num": 1, "valor_parcela": "R$ 100,00", "vencimento": "2026-06-10"},
        target_email="user@example.com",
        tenant_id=tenant_id,
        idempotency_key=idem_key,
    )
    await db_session.flush()

    # Second call with same key — ON CONFLICT DO NOTHING
    await svc.enqueue(
        template_key="portal.parcela_due_soon",
        payload={"parcela_num": 1, "valor_parcela": "R$ 100,00", "vencimento": "2026-06-10"},
        target_email="user@example.com",
        tenant_id=tenant_id,
        idempotency_key=idem_key,
    )
    await db_session.flush()

    result = await db_session.execute(
        select(NotificationsOutbox).where(NotificationsOutbox.idempotency_key == idem_key)
    )
    rows = result.scalars().all()
    assert len(rows) == 1, "idempotency_key should deduplicate enqueue calls"


async def test_enqueue_scheduled_for_future(db_session, tenant_id):
    from datetime import timedelta
    future = datetime.now(timezone.utc) + timedelta(hours=2)

    svc = NotificationService(db_session)
    await svc.enqueue(
        template_key="auth.password_reset",
        payload={"reset_url": "x", "user_name": "y"},
        target_email="future@example.com",
        tenant_id=tenant_id,
        scheduled_for=future,
    )
    await db_session.flush()

    result = await db_session.execute(
        select(NotificationsOutbox).where(NotificationsOutbox.target_email == "future@example.com")
    )
    row = result.scalar_one()
    assert row.scheduled_for.replace(tzinfo=timezone.utc) >= future - timedelta(seconds=1)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_notification_service.py -v
```

Expected: FAIL — `NotificationService` doesn't exist yet.

- [ ] **Step 3: Implement NotificationService**

`backend/finacialsim_saas/notifications/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import NotificationsOutbox

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def render_template(template_key: str, payload: dict[str, Any]) -> tuple[str, str, str]:
    """Render a template. Returns (subject, body_html, body_txt).

    template_key uses dots: "auth.password_reset" → looks in templates/auth/password_reset/
    """
    key_path = template_key.replace(".", "/")
    env = _jinja_env()
    subject = env.get_template(f"{key_path}/subject.txt").render(**payload).strip()
    body_html = env.get_template(f"{key_path}/body.html").render(**payload)
    body_txt = env.get_template(f"{key_path}/body.txt").render(**payload)
    return subject, body_html, body_txt


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def enqueue(
        self,
        template_key: str,
        payload: dict[str, Any],
        target_email: str | None,
        *,
        tenant_id: uuid.UUID,
        channel: str = "email",
        target_phone: str | None = None,
        scheduled_for: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """Write an outbox row in the caller's open transaction.

        If idempotency_key is provided, uses INSERT ... ON CONFLICT DO NOTHING
        so duplicate calls (e.g. cron re-run) are safe.
        """
        now = datetime.now(timezone.utc)
        values: dict[str, Any] = {
            "tenant_id": tenant_id,
            "channel": channel,
            "template_key": template_key,
            "payload_json": payload,
            "target_email": target_email,
            "target_phone": target_phone,
            "scheduled_for": scheduled_for or now,
            "status": "pending",
            "attempts": 0,
            "idempotency_key": idempotency_key,
            "updated_at": now,
            "criado_em": now,
        }
        if idempotency_key is not None:
            stmt = (
                pg_insert(NotificationsOutbox)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            await self._s.execute(stmt)
        else:
            self._s.add(NotificationsOutbox(**values))
```

- [ ] **Step 4: Run service tests**

```bash
cd backend && uv run pytest tests/test_notification_service.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml \
        backend/finacialsim_saas/settings.py \
        backend/finacialsim_saas/notifications/ \
        backend/tests/test_notification_templates.py \
        backend/tests/test_notification_service.py
git commit -m "feat(phase7b): add NotificationService, EmailChannel, Jinja2 templates, SMTP settings"
```
