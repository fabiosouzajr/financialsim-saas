# Efí Pix Provider — Part 4: Wiring + Runbook (Tasks 10–13)

> Part of the [Phase 1 plan](2026-06-07-efi-pix-provider.md). Tasks 10–13: `deps.py` wiring, `main.py` fail-fast, CLI `register-webhook`, setup runbook. Self-review at end.

---

### Task 10: `pix/deps.py` — wire `efi`, cached singleton, startup guards; remove stub

**Files:**

- Modify: `backend/finacialsim_saas/pix/deps.py`
- Modify: `backend/finacialsim_saas/api/pix_admin.py:41`
- Delete: `backend/finacialsim_saas/pix/stub.py`
- Test: Create `backend/tests/test_pix_deps.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pix_deps.py`:

```python
from __future__ import annotations

import pytest

from finacialsim_saas.pix import deps as pix_deps
from finacialsim_saas.settings import Settings


def _settings(**overrides) -> Settings:
    base: dict = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="fake",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _reset_efi_singleton(monkeypatch):
    monkeypatch.setattr(pix_deps, "_efi_provider", None)


def test_external_provider_value_no_longer_supported():
    """Selector rename fake|external → fake|efi (spec §5) — "external" must now raise."""
    with pytest.raises(ValueError, match="Unknown PIX_PROVIDER"):
        pix_deps.get_pix_provider(_settings(pix_provider="external"))


def test_efi_provider_requires_settings_to_be_set():
    settings = _settings(
        pix_provider="efi",
        efi_client_id="", efi_client_secret="x", efi_certificate_path="/no/file", efi_pix_key="key",
    )
    with pytest.raises(ValueError, match="EFI_CLIENT_ID"):
        pix_deps.get_pix_provider(settings)


def test_efi_provider_requires_certificate_file_to_exist():
    settings = _settings(
        pix_provider="efi",
        efi_client_id="id", efi_client_secret="secret",
        efi_certificate_path="/no/such/file.pem", efi_pix_key="key",
    )
    with pytest.raises(ValueError, match="does not exist"):
        pix_deps.get_pix_provider(settings)


def test_efi_provider_is_cached_as_singleton(monkeypatch, tmp_path):
    cert = tmp_path / "efi.pem"
    cert.write_text("cert")
    settings = _settings(
        pix_provider="efi",
        efi_client_id="id", efi_client_secret="secret",
        efi_certificate_path=str(cert), efi_pix_key="key",
    )

    constructed = []

    class _FakeEfiProvider:
        name = "efi"

        def __init__(self, settings):
            constructed.append(settings)

    monkeypatch.setattr(pix_deps, "EfiPixProvider", _FakeEfiProvider)

    first = pix_deps.get_pix_provider(settings)
    second = pix_deps.get_pix_provider(settings)

    assert first is second
    assert len(constructed) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pix_deps.py -v`
Expected: FAIL —
- `test_external_provider_value_no_longer_supported`: `Failed: DID NOT RAISE` (still returns `StubExternalPixProvider`)
- `test_efi_provider_requires_*`: `ValueError: Unknown PIX_PROVIDER: 'efi'` (wrong — `efi` not wired yet)
- `test_efi_provider_is_cached_as_singleton`: `AttributeError: module has no attribute 'EfiPixProvider'`

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `backend/finacialsim_saas/pix/deps.py`:

```python
from __future__ import annotations

from pathlib import Path

from finacialsim_saas.pix.efi import EfiPixProvider
from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.settings import Settings

# Cached singleton for the `efi` branch — EfiPixProvider.__init__ authenticates with Efí's
# OAuth2 token endpoint on construction; constructing per-request would multiply auth calls.
# Not lru_cache on get_pix_provider itself — that would wrongly cache fake across test settings.
_efi_provider: EfiPixProvider | None = None


def _validate_efi_settings(settings: Settings) -> None:
    missing = [
        name for name, value in (
            ("EFI_CLIENT_ID", settings.efi_client_id),
            ("EFI_CLIENT_SECRET", settings.efi_client_secret),
            ("EFI_CERTIFICATE_PATH", settings.efi_certificate_path),
            ("EFI_PIX_KEY", settings.efi_pix_key),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"PIX_PROVIDER=efi requires {', '.join(missing)} to be set")
    if not Path(settings.efi_certificate_path).exists():
        raise ValueError(f"EFI_CERTIFICATE_PATH does not exist: {settings.efi_certificate_path}")


def get_pix_provider(settings: Settings) -> PixProvider:
    global _efi_provider
    if settings.pix_provider == "fake":
        return InMemoryFakePixProvider(secret=settings.pix_webhook_secret)
    if settings.pix_provider == "efi":
        if _efi_provider is None:
            _validate_efi_settings(settings)
            _efi_provider = EfiPixProvider(settings)
        return _efi_provider
    raise ValueError(f"Unknown PIX_PROVIDER: {settings.pix_provider!r}")
```

Delete the now-superseded stub:

```bash
git rm backend/finacialsim_saas/pix/stub.py
```

In `backend/finacialsim_saas/api/pix_admin.py`, change line 41 from:

```python
    if settings.pix_provider == "external":
```

to:

```python
    if settings.pix_provider != "fake":
```

(Stays correct if a third provider is ever added — "block the demo button whenever a real provider is active".)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pix_deps.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/deps.py backend/finacialsim_saas/api/pix_admin.py backend/tests/test_pix_deps.py
git commit -m "feat: wire EfiPixProvider into get_pix_provider with cached singleton and startup validation"
```

---

### Task 11: `main.py` lifespan — fail-fast Pix validation + sandbox-in-production warning

**Files:**

- Modify: `backend/finacialsim_saas/main.py` (after line 19; replace lines 31-33)
- Test: Create `backend/tests/test_main_pix_startup.py`

**Corrected line numbers (verified 2026-06-08):** `app_state: dict[str, Any] = {}` is line 19; the `app.state.arq = ...` / `logger.info("startup"...)` / `yield` block is lines 31–33.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_main_pix_startup.py`:

```python
from __future__ import annotations

from finacialsim_saas.settings import Settings


def _settings(**overrides) -> Settings:
    base: dict = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="efi", app_env="production", efi_sandbox=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_pix_sandbox_warning_fires_for_efi_sandbox_in_production():
    from finacialsim_saas.main import _pix_sandbox_warning

    warning = _pix_sandbox_warning(_settings())
    assert warning is not None
    assert "sandbox" in warning.lower()


def test_pix_sandbox_warning_silent_outside_efi_sandbox_production_combo():
    from finacialsim_saas.main import _pix_sandbox_warning

    assert _pix_sandbox_warning(_settings(app_env="development")) is None
    assert _pix_sandbox_warning(_settings(efi_sandbox=False)) is None
    assert _pix_sandbox_warning(_settings(pix_provider="fake")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_main_pix_startup.py -v`
Expected: FAIL — `ImportError: cannot import name '_pix_sandbox_warning' from 'finacialsim_saas.main'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/main.py`, add this function after the `app_state` declaration (after line 19):

```python
def _pix_sandbox_warning(settings) -> str | None:
    """A real-PSP-in-sandbox-in-production combo silently lands charges in Efí's sandbox —
    customers think they paid, nothing shows up in the real account. Loud warning, not a
    hard stop (a legitimate staged-rollout could legitimately hit this combination)."""
    if settings.pix_provider == "efi" and settings.app_env == "production" and settings.efi_sandbox:
        return (
            "PIX_PROVIDER=efi with EFI_SANDBOX=true in production — Pix charges will land "
            "in Efí's sandbox; customers will think they paid and nothing will show up in "
            "the real account. This is almost certainly a misconfiguration."
        )
    return None
```

In the `lifespan` function, replace lines 31-33:

```python
    app.state.arq = await create_pool(ArqRedisSettings.from_dsn(str(settings.redis_url)))
    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
```

with:

```python
    app.state.arq = await create_pool(ArqRedisSettings.from_dsn(str(settings.redis_url)))

    from finacialsim_saas.pix.deps import get_pix_provider
    get_pix_provider(settings)  # fail fast on efi misconfiguration — not on the first charge
    sandbox_warning = _pix_sandbox_warning(settings)
    if sandbox_warning:
        logger.warning(sandbox_warning)

    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_main_pix_startup.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/main.py backend/tests/test_main_pix_startup.py
git commit -m "feat: validate Pix provider at startup and warn on efi sandbox-in-production"
```

---

### Task 12: CLI `pix register-webhook` + `EfiPixProvider.register_webhook`

**Files:**

- Create: `backend/finacialsim_saas/cli/pix_cli.py`
- Modify: `backend/finacialsim_saas/cli/main.py:32-36`
- Modify: `backend/finacialsim_saas/pix/efi.py`
- Test: extend `backend/tests/test_cli.py` and `backend/tests/test_efi_pix_provider.py`

**Corrected line numbers (verified 2026-06-08):** `cli/main.py` lines 32-36 are:
```
32: from finacialsim_saas.cli.db import db_app
33: from finacialsim_saas.cli.notifications_cli import notifications_app
34: (blank)
35: app.add_typer(db_app, name="db")
36: app.add_typer(notifications_app, name="notifications")
```

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_efi_pix_provider.py`:

```python
@pytest.mark.asyncio
async def test_register_webhook_sends_url_with_skip_mtls_header():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_config_webhook.return_value = {
        "webhookUrl": "https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar="
    }
    provider = EfiPixProvider(_settings(), client=client)

    await provider.register_webhook("https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar=")

    client.pix_config_webhook.assert_called_once_with(
        params={"chave": "11111111-2222-3333-4444-555555555555"},
        body={"webhookUrl": "https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar="},
        headers={"x-skip-mtls-checking": "true"},
    )
```

Append to `backend/tests/test_cli.py`:

```python
def test_pix_register_webhook_builds_url_and_calls_provider(runner, monkeypatch):
    from finacialsim_saas.cli import pix_cli
    from finacialsim_saas.settings import Settings

    test_settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="efi", pix_webhook_secret="test-secret",
        frontend_base_url="https://app.test",
    )
    monkeypatch.setattr(pix_cli, "get_settings", lambda: test_settings)

    registered = {}

    class _FakeProvider:
        def __init__(self, settings):
            pass

        async def register_webhook(self, url):
            registered["url"] = url

    monkeypatch.setattr(pix_cli, "EfiPixProvider", _FakeProvider)

    from finacialsim_saas.cli.main import app
    result = runner.invoke(app, ["pix", "register-webhook"])

    assert result.exit_code == 0, result.output
    assert registered["url"] == "https://app.test/api/v1/webhooks/pix?hmac=test-secret&ignorar="
    assert "Webhook registered" in result.output


def test_pix_register_webhook_rejects_non_efi_provider(runner, monkeypatch):
    from finacialsim_saas.cli import pix_cli
    from finacialsim_saas.settings import Settings

    test_settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="fake",
    )
    monkeypatch.setattr(pix_cli, "get_settings", lambda: test_settings)

    from finacialsim_saas.cli.main import app
    result = runner.invoke(app, ["pix", "register-webhook"])

    assert result.exit_code != 0
    assert "PIX_PROVIDER is not 'efi'" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py::test_register_webhook_sends_url_with_skip_mtls_header tests/test_cli.py -k pix_register -v`
Expected: FAIL —
- `test_register_webhook_sends_url_with_skip_mtls_header`: `AttributeError: 'EfiPixProvider' object has no attribute 'register_webhook'`
- both CLI tests: `ModuleNotFoundError: No module named 'finacialsim_saas.cli.pix_cli'`

- [ ] **Step 3: Write minimal implementation**

Add to `EfiPixProvider` in `backend/finacialsim_saas/pix/efi.py` (after `verify_webhook`):

```python
    async def register_webhook(self, url: str) -> None:
        """PUT /v2/webhook/:chave — idempotent. `x-skip-mtls-checking: true` required
        on registration, or Efí defaults to mTLS validation the Caddy proxy can't satisfy."""
        await asyncio.to_thread(
            self._client.pix_config_webhook,
            params={"chave": self._pix_key},
            body={"webhookUrl": url},
            headers={"x-skip-mtls-checking": "true"},
        )
```

Create `backend/finacialsim_saas/cli/pix_cli.py`:

```python
from __future__ import annotations

import asyncio

import typer

from finacialsim_saas.pix.efi import EfiPixProvider
from finacialsim_saas.settings import get_settings

pix_app = typer.Typer(help="Pix PSP management commands")


@pix_app.command("register-webhook")
def pix_register_webhook():
    """Registers (or re-registers) the Pix webhook callback URL with Efí. Idempotent (PUT)."""
    settings = get_settings()
    if settings.pix_provider != "efi":
        typer.echo("Error: PIX_PROVIDER is not 'efi'.", err=True)
        raise typer.Exit(1)

    url = (
        f"{settings.frontend_base_url}/api/v1/webhooks/pix"
        f"?hmac={settings.pix_webhook_secret}&ignorar="
    )

    async def _register():
        provider = EfiPixProvider(settings)
        await provider.register_webhook(url)

    asyncio.run(_register())
    typer.echo(f"Webhook registered: {url}")
```

In `backend/finacialsim_saas/cli/main.py`, replace lines 32-36:

```python
from finacialsim_saas.cli.db import db_app
from finacialsim_saas.cli.notifications_cli import notifications_app

app.add_typer(db_app, name="db")
app.add_typer(notifications_app, name="notifications")
```

with:

```python
from finacialsim_saas.cli.db import db_app
from finacialsim_saas.cli.notifications_cli import notifications_app
from finacialsim_saas.cli.pix_cli import pix_app

app.add_typer(db_app, name="db")
app.add_typer(notifications_app, name="notifications")
app.add_typer(pix_app, name="pix")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py::test_register_webhook_sends_url_with_skip_mtls_header tests/test_cli.py -k pix_register -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/finacialsim_saas/cli/pix_cli.py \
        backend/finacialsim_saas/cli/main.py backend/tests/test_efi_pix_provider.py \
        backend/tests/test_cli.py
git commit -m "feat: add pix register-webhook CLI command and EfiPixProvider.register_webhook"
```

---

### Task 13: Setup runbook doc

**Files:**

- Create: `docs/agents/efi-pix-setup.md`

- [ ] **Step 1: Write the runbook**

Create `docs/agents/efi-pix-setup.md`:

```markdown
# Efí Pix provider setup

One-time runbook — sandbox account through go-live verification. Re-run `pix register-webhook`
(step 5) whenever the domain or `PIX_WEBHOOK_SECRET` changes — it's idempotent (`PUT`).

## 1. Create an Efí sandbox account

Sign up for Efí's "homologação" (sandbox) environment via their developer portal and register
a Pix key (`chave Pix`) for the recipient account. This becomes `EFI_PIX_KEY`.

## 2. Generate and convert the mTLS certificate

Download the `.p12` certificate from Efí's dashboard and convert it to `.pem` (the `efipay`
SDK expects `.pem`; exact command confirmed from Efí's own docs):

```bash
openssl pkcs12 -in certificado.p12 -out certificado.pem -nodes -password pass:""
```

## 3. Mount the certificate into the container

`EFI_CERTIFICATE_PATH` is an in-container path — the file must be bind-mounted there.
`ops/docker-compose.yml` already follows this pattern for `PDF_OUTPUT_DIR` (the `worker`/`api`
services pair an env var pointing at `/var/lib/finacialsim/pdfs` with a named volume). Mirror
it for the cert on **both** `api` and `worker` (both construct `EfiPixProvider` on startup):

```yaml
environment:
  EFI_CERTIFICATE_PATH: /var/lib/finacialsim/certs/efi.pem
volumes:
  - ./certs/efi.pem:/var/lib/finacialsim/certs/efi.pem:ro
```

## 4. Populate `.env`

```env
EFI_CLIENT_ID=...
EFI_CLIENT_SECRET=...
EFI_CERTIFICATE_PATH=/var/lib/finacialsim/certs/efi.pem
EFI_PIX_KEY=11111111-2222-3333-4444-555555555555
EFI_SANDBOX=true
PIX_PROVIDER=efi
```

The app refuses to boot with `PIX_PROVIDER=efi` if any `EFI_*` setting is empty or the
certificate file doesn't exist — fix `.env` and restart rather than chasing a runtime 500 on
the first customer's "Pagar com Pix" click.

## 5. Register the webhook

```bash
uv run finacialsim-saas pix register-webhook
```

Registers `PUT /v2/webhook/:chave` with
`webhookUrl: "<frontend_base_url>/api/v1/webhooks/pix?hmac=<PIX_WEBHOOK_SECRET>&ignorar="`
and header `x-skip-mtls-checking: true` (required — omitting it causes Efí to default to mTLS
validation, which the Caddy proxy can't satisfy, silently breaking webhook delivery).

## 6. Verify webhook delivery — don't skip this

The `?hmac=...&ignorar=` URL mechanism (prevents Efí from appending `/pix` to the registered
URL) is sourced from a community forum post, not Efí's official docs. If it behaves differently,
the webhook silently 404s — Efí retries up to 9 times then gives up, and "payment confirmation
just doesn't happen" is brutal to debug post-launch.

After registering, Efí sends an automatic test notification. Check **Efí's dashboard delivery
log** for the actual URL/path it called. If it doesn't match `/api/v1/webhooks/pix`, adjust the
registered URL (with/without `/pix`, with/without `?ignorar=`) and re-run step 5.

## 7. Manual smoke test (CobV-shaped)

1. Create a sandbox CobV charge via "Pagar com Pix" on a proposal with a linked client
   (clientless proposals are blocked by design — spec §2b).

2. Confirm the **same `brcode`/QR is payable at three points**: a few days before `vencimento`,
   on `vencimento`, and a few days after — the long-lived single-charge model means all three
   matter, not just "does it work once."

3. Pay via Efí's sandbox simulator. **Explicitly test a value above R$10** to verify/refute
   the "R$0.01–10.00 only" sandbox auto-confirm claim (spec §1 Known Unknown — must be
   confirmed before production confidence). Sandbox charges ≤ R$10.01 auto-confirm without
   a manual simulator step (useful first pass only).

4. Confirm the webhook fires: `parcela` flips to `paid`, `pix_webhook_events`/`audit_logs`
   rows created (check admin UI or query tables directly).

## Hardening deferred to a later phase

Phase 1 ships skip-mTLS + hmac-token validation only — no IP allowlist, no mTLS handshake.
Both depend on reverse-proxy/cert-handling infrastructure not yet configured. Revisit when
Caddy exposes a trustworthy `X-Forwarded-For` or client cert.
```

- [ ] **Step 2: Review against the design spec checklist**

Confirm the doc covers all 7 points from `docs/superpowers/specs/2026-06-07-efi-pix-provider-design.md` §7:
sandbox account + Pix key (1), `.p12`→`.pem` conversion (2), Docker volume mount (3),
`.env` population (4), `pix register-webhook` (5), webhook delivery verification (6),
CobV-shaped manual smoke test including above-R$10 webhook check (7).

- [ ] **Step 3: Commit**

```bash
git add docs/agents/efi-pix-setup.md
git commit -m "docs: add Efí Pix provider setup runbook (CobV-shaped)"
```

---

## Self-Review

**1. Spec coverage** — every in-scope section maps to a task:

- §1 `EfiPixProvider` CobV `create_charge`/`cancel_charge` → Tasks 7, 8
- §1b explicit-zero `juros`/`multa` → Task 7
- §1c error translation → Task 7
- §2 `PayerInfo` + Protocol CobV signature + `query_params` → Tasks 2, 3, 6
- §2b clientless-proposal guard → Task 5 (`_ensure_charge`)
- §3 shared idempotent `_ensure_charge` core (returns `(charge, created)`) → Task 5
- §3b BRT expiry formula (`due_date + validity_days @ 23:59:59 BRT → UTC`) → Tasks 3, 7
- §4 skip-mTLS `verify_webhook` (hmac query token) → Task 9
- §5 `efi_*` settings, selector rename `fake|external`→`fake|efi`, cached singleton, startup guards, `pix_admin.py` gate → Tasks 1, 10, 11
- §6 `pix register-webhook` CLI + `register_webhook` → Task 12
- §7 setup runbook (CobV-shaped smoke test, above-R$10 check) → Task 13
- `pix_validade_apos_vencimento_dias` rule (feeds `_ensure_charge`) → Task 4
- Tests checklist → Tasks 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12

**2. Placeholder scan** — every code block is complete; no `TBD`/`...`/"similar to Task N". Two deliberate "verify first" instructions (Tasks 7 §1 and 8 §1) name the exact SDK example files to read and give specific correction instructions if the values differ — they are verification steps, not placeholders.

**3. Type/signature consistency:**

- `PayerInfo(document, document_type, name)` — defined Task 2, constructed identically in Task 5 (`_ensure_charge`) and Task 7 test fixtures, consumed identically in Task 7 (`EfiPixProvider.create_charge`'s `devedor` mapping)
- `create_charge(*, txid, amount, due_date: date, validity_days: int, description, payer: PayerInfo | None)` — Protocol (Task 2), `fake` (Task 3), `_ensure_charge` call site (Task 5), `EfiPixProvider` (Task 7) all match; `expires_in` gone from all four
- `verify_webhook(headers, query_params, body)` — Protocol (Task 2), `fake` (Task 3), `service.py` (Task 6), `EfiPixProvider` (Task 9) all match
- `_ensure_charge` returns `tuple[PixCharge, bool]` — used consistently in Task 5 (`create_charge_for_parcela` branches on `created`) and tested in `test_ensure_charge_reuses_*`
- `EfiPixProvider(settings, client=None)` constructor-injection shape used consistently across Tasks 7–12
- `_efi_provider`/`_validate_efi_settings`/`get_pix_provider` names in Task 10 match assertions in `test_pix_deps.py`
- `_pix_sandbox_warning` name/signature in Task 11 matches its test
- `pix_app`/`pix_register_webhook` names in Task 12 match `main.py`'s `add_typer` and `runner.invoke(app, ["pix", "register-webhook"])`
- `RulesService(self._s).get_rules(parcela.tenant_id)` in Task 5 — `RulesService` imported in Task 5's import block; `pix_validade_apos_vencimento_dias` key added in Task 4

No gaps found.
