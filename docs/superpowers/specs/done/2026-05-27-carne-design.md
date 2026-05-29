# Design Spec — Geração de Carnê PDF

**Data:** 2026-05-27
**Status:** Aprovado

---

## Objetivo

Gerar um carnê PDF imprimível com os boletos de pagamento de cada parcela do financiamento, a partir de uma Proposta aprovada.

---

## Decisões de Design

| Decisão | Escolha |
|---|---|
| Boletos por página A4 | 4 |
| Conteúdo de cada boleto | Nome/CPF cliente, veículo + placa, parcela N/total, vencimento, valor total da parcela |
| Ponto de geração na UI | Tela de Proposta (não na simulação) |
| Entrega do PDF | `os.startfile()` — abre no viewer padrão do sistema |
| Arquitetura | `CarneService` independente, mesmo padrão de `ClientService`/`VehicleService` |
| Diretório de saída | `data/carnes/` |
| Nomeação do arquivo | `PROP-{proposal.codigo}.pdf` |

---

## Arquitetura

### Novos arquivos

- `app/services/carne_service.py` — `CarneService` com método `generate(proposal_id, session) -> Path`
- `app/reports/carne.html` — template Jinja2, 4 boletos por página com linha de corte
- `app/reports/carne.css` — estilos de impressão (margens A4, tipografia, linha de corte)
- `app/data/migrations/versions/YYYYMMDD_add_carne_path.py` — adiciona `carne_path` em `proposals`

### Arquivos modificados

- `app/data/models.py` — campo `carne_path: str | None` em `Proposal`
- `app/ui/pages/simulacao.py` — botão "Gerar Carnê" na seção de proposta

---

## CarneService

```python
class CarneService:
    def generate(self, proposal_id: int, session: Session) -> Path:
        # 1. Carrega Proposal + Client + Vehicle + Simulation + AmortizationRows
        # 2. Monta contexto Jinja2 com dados da loja (BusinessRule), cliente, veículo, parcelas
        # 3. Renderiza carne.html -> HTML string
        # 4. WeasyPrint -> PDF em data/carnes/PROP-{codigo}.pdf
        # 5. Persiste proposal.carne_path no banco
        # 6. Retorna Path
```

**Contexto Jinja2 passado ao template:**

| Variável | Fonte |
|---|---|
| `loja` | `BusinessRule` (nome, CNPJ, telefone) |
| `cliente.nome` | `Client.nome` |
| `cliente.cpf_cnpj_fmt` | `Client.cpf_cnpj` formatado |
| `veiculo.descricao` | `"{marca} {modelo} {ano_modelo}"` |
| `veiculo.placa` | `Vehicle.placa` (pode ser None) |
| `proposal.codigo` | `Proposal.codigo` |
| `parcelas` | lista de `AmortizationRow` com `parcela_total` em BRL, `data_vencimento` formatada |

---

## Template HTML

Estrutura por página A4:

```
[Cabeçalho: nome e CNPJ da loja]
[Boleto 1]
corte ─ ─ ─ ─ linha de corte ─ ─ ─ ─ corte
[Boleto 2]
corte ─ ─ ─ ─ linha de corte ─ ─ ─ ─ corte
[Boleto 3]
corte ─ ─ ─ ─ linha de corte ─ ─ ─ ─ corte
[Boleto 4]
```

Cada boleto contém:
- Canto esquerdo: label "Cliente", nome, CPF/CNPJ, veículo + placa (itálico)
- Canto direito: label "Parcela", número `NN / total`, código da simulação
- Linha inferior: "Vencimento" (data) e "Valor a pagar" (valor em destaque verde)

O CSS usa `@page { size: A4; margin: 15mm; }` e `page-break-after: always` a cada 4 boletos.

---

## Migration Alembic

```python
op.add_column("proposals", sa.Column("carne_path", sa.String(), nullable=True))
```

Nullable — sem batch operation, compatível com SQLite.

---

## UI (simulacao.py)

Na seção de proposta existente, adicionar:

```python
ui.button("Gerar Carne", on_click=handle_gerar_carne)

async def handle_gerar_carne():
    try:
        path = CarneService().generate(proposal_id, session)
        os.startfile(str(path))
        ui.notify("Carne gerado!", type="positive")
    except Exception as e:
        handle_unexpected(e, "gerar_carne")
```

O botão fica desabilitado se não houver proposta salva (`proposal_id is None`).

---

## Casos de Borda

| Situação | Comportamento |
|---|---|
| Veículo sem placa | Exibe só `"{marca} {modelo} {ano}"`, sem "placa" |
| `data/carnes/` não existe | `Path.mkdir(parents=True, exist_ok=True)` no `CarneService` |
| Carnê já gerado anteriormente | Sobrescreve o arquivo; atualiza `carne_path` |
| `BusinessRule` de loja não cadastrada | Usa string vazia; não lança excecao |
