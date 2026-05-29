from __future__ import annotations

from datetime import date as _date
from decimal import Decimal as _Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models import BusinessRule, Client, IndicatorHistory, Simulation, User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, nome: str, pin_hash: str, perfil: str) -> User:
        u = User(nome=nome, pin_hash=pin_hash, perfil=perfil)
        self.session.add(u)
        self.session.commit()
        self.session.refresh(u)
        return u

    def get(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def list_active(self) -> list[User]:
        stmt = select(User).where(User.ativo.is_(True)).order_by(User.nome)
        return list(self.session.scalars(stmt))

    def deactivate(self, user_id: int) -> None:
        u = self.session.get(User, user_id)
        if u is None:
            return
        u.ativo = False
        self.session.commit()


class ClientRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        nome: str,
        cpf_cnpj: str,
        tipo: str,
        criado_por: int,
        rg: str | None = None,
        data_nasc: _date | None = None,
        profissao: str | None = None,
        renda: _Decimal | None = None,
        telefone: str | None = None,
        email: str | None = None,
        endereco_json: str | None = None,
        observacoes: str | None = None,
    ) -> Client:
        c = Client(
            nome=nome, cpf_cnpj=cpf_cnpj, tipo=tipo, criado_por=criado_por,
            rg=rg, data_nasc=data_nasc, profissao=profissao, renda=renda,
            telefone=telefone, email=email, endereco_json=endereco_json,
            observacoes=observacoes,
        )
        self.session.add(c)
        self.session.commit()
        self.session.refresh(c)
        return c

    def find_by_cpf_cnpj(self, cpf_cnpj: str) -> Client | None:
        stmt = select(Client).where(Client.cpf_cnpj == cpf_cnpj)
        return self.session.scalars(stmt).first()

    def search(self, term: str) -> list[Client]:
        like = f"%{term}%"
        stmt = (
            select(Client)
            .where((Client.nome.ilike(like)) | (Client.cpf_cnpj.like(like)))
            .order_by(Client.nome)
            .limit(50)
        )
        return list(self.session.scalars(stmt))


class IndicatorRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        codigo: str,
        data_referencia: _date,
        valor: _Decimal,
        unidade: str,
        fonte: str,
        payload_json: str | None = None,
    ) -> IndicatorHistory:
        stmt = select(IndicatorHistory).where(
            IndicatorHistory.codigo == codigo,
            IndicatorHistory.data_referencia == data_referencia,
        )
        existing = self.session.scalars(stmt).first()
        if existing:
            existing.valor = valor
            existing.unidade = unidade
            existing.fonte = fonte
            existing.payload_json = payload_json
            self.session.commit()
            return existing
        new = IndicatorHistory(
            codigo=codigo, data_referencia=data_referencia, valor=valor,
            unidade=unidade, fonte=fonte, payload_json=payload_json,
        )
        self.session.add(new)
        self.session.commit()
        self.session.refresh(new)
        return new

    def get_latest(self, codigo: str) -> IndicatorHistory | None:
        stmt = (
            select(IndicatorHistory)
            .where(IndicatorHistory.codigo == codigo)
            .order_by(IndicatorHistory.data_referencia.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()


class BusinessRuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, chave: str) -> str | None:
        stmt = select(BusinessRule).where(BusinessRule.chave == chave)
        row = self.session.scalars(stmt).first()
        return row.valor_json if row else None

    def set(
        self,
        chave: str,
        valor_json: str,
        descricao: str | None = None,
        user_id: int | None = None,
    ) -> BusinessRule:
        stmt = select(BusinessRule).where(BusinessRule.chave == chave)
        existing = self.session.scalars(stmt).first()
        if existing:
            existing.valor_json = valor_json
            if descricao is not None:
                existing.descricao = descricao
            existing.atualizado_por = user_id
            self.session.commit()
            return existing
        new = BusinessRule(chave=chave, valor_json=valor_json, descricao=descricao,
                           atualizado_por=user_id)
        self.session.add(new)
        self.session.commit()
        self.session.refresh(new)
        return new


class SimulationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, sim: Simulation) -> Simulation:
        self.session.add(sim)
        self.session.commit()
        self.session.refresh(sim)
        return sim

    def get(self, simulation_id: int) -> Simulation | None:
        return self.session.get(Simulation, simulation_id)

    def list_by_client(self, client_id: int) -> list[Simulation]:
        stmt = (
            select(Simulation)
            .where(Simulation.cliente_id == client_id)
            .order_by(Simulation.criado_em.desc())
        )
        return list(self.session.scalars(stmt))
