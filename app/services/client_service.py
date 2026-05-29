"""ClientService - validated client CRUD."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import Client
from app.data.repositories import ClientRepository
from app.services.audit_service import AuditService
from app.utils.document_validation import is_valid_cnpj, is_valid_cpf


class ClientServiceError(Exception):
    pass


def _only_digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


class ClientService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ClientRepository(session)
        self.audit = AuditService(session)

    def create_pf(
        self,
        nome: str,
        cpf: str,
        criado_por: int,
        rg: str | None = None,
        data_nasc: date | None = None,
        profissao: str | None = None,
        renda: Decimal | None = None,
        telefone: str | None = None,
        email: str | None = None,
        endereco_json: str | None = None,
        observacoes: str | None = None,
    ) -> Client:
        cpf_d = _only_digits(cpf)
        if not is_valid_cpf(cpf_d):
            raise ClientServiceError(f"CPF invalido: {cpf}")
        if self.repo.find_by_cpf_cnpj(cpf_d):
            raise ClientServiceError(f"CPF ja cadastrado: {cpf}")
        c = self.repo.create(
            nome=nome, cpf_cnpj=cpf_d, tipo="PF", criado_por=criado_por,
            rg=rg, data_nasc=data_nasc, profissao=profissao, renda=renda,
            telefone=telefone, email=email, endereco_json=endereco_json,
            observacoes=observacoes,
        )
        self.audit.log(usuario_id=criado_por, acao="client_created",
                       entidade="clients", entidade_id=c.id)
        return c

    def create_pj(
        self,
        razao_social: str,
        cnpj: str,
        criado_por: int,
        telefone: str | None = None,
        email: str | None = None,
        endereco_json: str | None = None,
        observacoes: str | None = None,
    ) -> Client:
        cnpj_d = _only_digits(cnpj)
        if not is_valid_cnpj(cnpj_d):
            raise ClientServiceError(f"CNPJ invalido: {cnpj}")
        if self.repo.find_by_cpf_cnpj(cnpj_d):
            raise ClientServiceError(f"CNPJ ja cadastrado: {cnpj}")
        c = self.repo.create(
            nome=razao_social, cpf_cnpj=cnpj_d, tipo="PJ", criado_por=criado_por,
            telefone=telefone, email=email, endereco_json=endereco_json,
            observacoes=observacoes,
        )
        self.audit.log(usuario_id=criado_por, acao="client_created",
                       entidade="clients", entidade_id=c.id)
        return c

    def find(self, query: str) -> list[Client]:
        return self.repo.search(query)
