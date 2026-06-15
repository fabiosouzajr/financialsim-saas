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
        [],
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
        ["Lucia", "pagamento", "500,00"],
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
