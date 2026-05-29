# Design Spec — Cadastro de Veículos

**Data:** 2026-05-26
**Status:** Aprovado (pós-grill)

---

## Contexto

O modelo `Vehicle` já existe no banco e é referenciado por `Simulation.veiculo_id`, mas a página `/fipe` é apenas uma consulta — não persiste registros. A página `/simulacao` cria um veículo descartável (`fonte="manual"`, `marca="Manual"`, `modelo="Veiculo"`) a cada simulação, sem qualquer dado útil.

Este spec define a criação de uma página `/veiculos` que transforma veículos em entidades de primeira classe com ciclo de vida, diferenciação física e vínculo rastreável com simulações.

---

## Objetivos

1. Manter um registro de estoque de veículos com dados FIPE + campos físicos (`cor`, `placa`, `odometro_km`).
2. Permitir diferenciar dois veículos do mesmo modelo/ano pela placa, cor e odômetro.
3. Vincular simulações a veículos cadastrados e exibir esse histórico na página de veículos.
4. Integrar a busca FIPE na simulação para auto-cadastrar veículos inline.
5. Remover a aba `/fipe` (consulta pura) substituída pela funcionalidade em `/veiculos`.

---

## Decisões de design

| Decisão | Escolha | Motivo |
|---|---|---|
| Layout `/veiculos` | Dois `ui.column` side-by-side — painel direito `.set_visibility()` | Sem conflito com `shell()`, sem animação complexa |
| Integração na simulação | Picker + busca FIPE inline + valor livre | Flexibilidade máxima sem quebrar fluxo atual |
| Status de placa | Único entre veículos ativos (`disponivel`/`reservado`) | Permite reutilizar placa após venda |
| Status automático | Manual — nenhuma automação | Sem acoplamento com proposta/simulação |
| Permissões | Todos os perfis criam, editam e mudam status | Loja pequena; sem hierarquia de estoque |
| Valor na simulação | Ambos (FIPE e referência) como chips + campo livre | Vendedor decide qual base usar |
| Placeholders históricos | Migração seta `status='vendido'` em `fonte='manual'` | Remove lixo do dropdown sem afetar integridade |
| Navegação simulation_id | `app.storage.user["open_simulation_id"]` | Já é o padrão de storage da app |
| VehicleRepository | Não criado — `VehicleService` acessa sessão diretamente | Consistente com `SimulationService` |
| `valor_referencia` default | Pré-preenchido com `valor_fipe` no mini-modal | Nenhum bloqueio para o vendedor |
| Link de simulação → /simulacao | Modo leitura + "Nova simulação com esses dados" | Preserva original, permite fork |
| "Nova simulação com esses dados" | Apenas preenche formulário — usuário clica "Simular" | Controle explícito ao vendedor |
| Validação de placa | Regex estrita: antigo (`ABC-1234`) + Mercosul (`ABC1D23`) | Normaliza maiúsculas, remove hífen antes de validar |
| Exclusão de veículo | Não existe — `vendido` é estado final imutável | Preserva auditabilidade das simulações históricas |
| Botão "Atualizar FIPE" | Entra no MVP — atualiza `valor_fipe` + `mes_referencia_fipe` + auditoria | Preço FIPE muda mensalmente |
| Campo `cor` | Texto livre `String(40)` | Cores especiais de fabricante não caberiam em lista |
| FIPE chain entre páginas | Instâncias separadas por página, cache via SQLite compartilhado | Padrão já usado em `build_fipe_page` e `build_simulacao_page` |

---

## Seção 1 — Modelo de dados

### Novos campos no model `Vehicle` (`app/data/models.py`)

```python
cor:           Mapped[str | None]  = mapped_column(String(40), nullable=True)
placa:         Mapped[str | None]  = mapped_column(String(10), nullable=True)
odometro_km:   Mapped[int | None]  = mapped_column(Integer, nullable=True)
status:        Mapped[str]         = mapped_column(String(20), nullable=False, default="disponivel")
atualizado_em: Mapped[datetime]    = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)
criado_por:    Mapped[int | None]  = mapped_column(ForeignKey("users.id"), nullable=True)
```

**Status permitidos:** `disponivel` · `reservado` · `vendido`

### Constraint de unicidade de placa

Índice parcial SQLite — placa única somente entre veículos ativos:

```sql
CREATE UNIQUE INDEX uq_vehicles_placa_ativa
ON vehicles (placa)
WHERE status != 'vendido' AND placa IS NOT NULL;
```

Validação duplicada no `VehicleService` para retornar mensagem amigável ao usuário antes de tentar persistir.

### Validação de formato de placa

Normalização antes de persistir e antes de checar unicidade:
```python
placa = placa.upper().replace("-", "").replace(" ", "")  # "abc-1234" → "ABC1234"
```

Regex de validação (após normalização):
```python
import re
PLACA_RE = re.compile(r'^[A-Z]{3}[0-9]{4}$|^[A-Z]{3}[0-9][A-Z][0-9]{2}$')
```

Rejeita qualquer formato fora do padrão com `VehicleServiceError`.

### Migração Alembic

Nova versão em `app/data/migrations/versions/` que:
1. Adiciona as 6 colunas via `ALTER TABLE vehicles ADD COLUMN ...`
2. Cria o índice parcial via `op.execute()`
3. Popula registros existentes:
   - `status = 'vendido'` onde `fonte = 'manual'` (placeholders descartáveis)
   - `status = 'disponivel'` nos demais
   - `atualizado_em = criado_em` em todos
   - `criado_por = 1` (admin seed) em todos — nullable, só para conformidade

`downgrade()` deve fazer `DROP INDEX uq_vehicles_placa_ativa` e dropar as colunas adicionadas.

---

## Seção 2 — VehicleService

**Arquivo:** `app/services/vehicle_service.py`

Acessa a sessão SQLAlchemy diretamente (sem VehicleRepository), consistente com `SimulationService`.

### Interface pública

```python
class VehicleServiceError(Exception): ...

class VehicleService:
    def __init__(self, session: Session) -> None: ...

    def create_from_fipe(
        self,
        quote: VehicleQuote,
        cor: str | None,
        placa: str | None,
        odometro_km: int | None,
        valor_referencia: Decimal,   # default: valor_fipe quando chamado da UI
        criado_por: int,
    ) -> Vehicle: ...

    def create_manual(
        self,
        tipo: str, marca: str, modelo: str, ano_modelo: int, combustivel: str,
        valor_referencia: Decimal,
        cor: str | None, placa: str | None, odometro_km: int | None,
        criado_por: int,
    ) -> Vehicle: ...

    def update(self, vehicle_id: int, fields: dict) -> Vehicle: ...
    # Campos editáveis: cor, placa, odometro_km, valor_referencia, status
    # Campos FIPE (marca, modelo, ano, combustivel, codigo_fipe, valor_fipe) NÃO editáveis via update()

    def refresh_fipe(self, vehicle_id: int, chain) -> Vehicle: ...
    # Re-consulta FIPE, atualiza valor_fipe + mes_referencia_fipe, registra auditoria

    def set_status(self, vehicle_id: int, status: str) -> Vehicle: ...

    def list_active(self, search: str = "") -> list[Vehicle]: ...
    # Retorna disponivel + reservado, fonte != 'manual'
    # Filtrável por marca/modelo/placa/cor (case-insensitive LIKE)

    def list_all(self, status_filter: str | None = None, search: str = "") -> list[Vehicle]: ...
    # Inclui vendidos; exclui fonte='manual'

    def get_simulations(self, vehicle_id: int) -> list[Simulation]: ...
    # Retorna simulações vinculadas, ordem desc por criado_em
    # Import: from app.data.models import Simulation
```

**Regras de negócio:**
- `create_from_fipe` e `create_manual` normalizam e validam placa via regex antes de persistir.
- Verificam unicidade de placa ativa na camada de serviço; lançam `VehicleServiceError` se duplicada.
- `set_status` valida que o status destino é `disponivel`, `reservado` ou `vendido`.
- Toda criação/edição/mudança de status/refresh chama `AuditService.log`.

---

## Seção 3 — Página `/veiculos`

**Arquivo:** `app/ui/pages/veiculos.py`

### Layout: dois ui.column side-by-side

```
┌─────────────────────────────────────────────────────────────┐
│  Veículos                              [+ Novo Veículo]      │
│  [busca texto___________] [status ▾]                         │
├─────────────────────────┬───────────────────────────────────┤
│  Tabela (58% largura)   │  Painel (42%) — set_visibility()  │
│                         │  Oculto até clicar linha/"Novo"   │
│  Modelo | Placa | Cor   │                                   │
│  Valor  | Status        │  [Marca Modelo Ano]  [Editar]     │
│  (linha selecionada     │  [Status ▾] [Atualizar FIPE]      │
│   destacada em azul)    │  FIPE / Referência / Cor / Placa  │
│                         │  Km / Mês ref. FIPE               │
│                         │                                   │
│                         │  ── Simulações vinculadas ──      │
│                         │  SIM-2026-XXXXX · valor · prazo   │
│                         │  (link → /simulacao via storage)  │
└─────────────────────────┴───────────────────────────────────┘
```

### Painel: modo criação

Ao clicar em "Novo Veículo", o painel torna-se visível em modo criação com duas abas (`ui.tabs`):
- **FIPE** — 4 dropdowns cascata (tipo → marca → modelo → ano). Ao atingir o preço, campos extras aparecem: `cor` (texto livre), `placa`, `odometro_km`, `valor_referencia` (default `valor_fipe`).
- **Manual** — formulário completo com todos os campos, sem busca FIPE.

Botão **Salvar** chama `VehicleService.create_from_fipe()` ou `create_manual()`, fecha o painel e atualiza a tabela.

### Painel: modo visualização/edição

Ao clicar numa linha da tabela, o painel torna-se visível em modo leitura. Botão ✏️ **Editar** alterna para modo edição onde somente campos físicos e `valor_referencia` ficam editáveis. Dados FIPE permanecem read-only.

Botão **Atualizar FIPE** chama `VehicleService.refresh_fipe()` e atualiza os valores exibidos.

### Links de simulações vinculadas

```python
def _open_simulation(sim_id: int) -> None:
    app.storage.user["open_simulation_id"] = sim_id
    ui.navigate.to("/simulacao")
```

Cada simulação exibe: `{sim.codigo} · {format_brl(sim.valor_veiculo)} · {sim.prazo_meses}x · {sim.criado_em.strftime("%d/%m/%Y")}`

### Cores de status

| Status | Fundo | Texto |
|---|---|---|
| `disponivel` | `#dcfce7` | `#166534` |
| `reservado` | `#fef9c3` | `#854d0e` |
| `vendido` | `#f1f5f9` | `#475569` (linha opaca na tabela) |

---

## Seção 4 — Página `/simulacao` — mudanças

**Arquivo:** `app/ui/pages/simulacao.py`

### Nova seção "Veículo" (acima do campo "Valor do veículo")

**Estado 1 — sem veículo selecionado (inicial):**
- `ui.select` filtrável listando `VehicleService.list_active()`: exibe `marca modelo ano · placa · cor`
- Link "🔍 Buscar na FIPE e cadastrar" abre Estado 3

**Estado 2 — veículo selecionado:**
- Picker mostra veículo com botão ✕ para limpar
- Dois chips: `FIPE R$ X` e `Ref. R$ Y` — clicar preenche `valor_veiculo`
- Campo `valor_veiculo` permanece editável (terceiro valor livre)

**Estado 3 — busca FIPE inline expandida:**
- 4 dropdowns cascata. Ao atingir preço, botão **"+ Cadastrar e usar"** abre `ui.dialog` com: `cor`, `placa`, `odometro_km`, `valor_referencia` (default `valor_fipe`)
- Confirmar chama `VehicleService.create_from_fipe()` → retorna ao Estado 2

**Modo leitura (carregar simulação existente):**
- Na abertura da página, se `app.storage.user.get("open_simulation_id")` estiver definido:
  - Carrega a `Simulation` do banco
  - Preenche todos os campos do formulário com os dados da simulação original
  - Carrega o `Vehicle` vinculado e posiciona a seção no Estado 2 com chips
  - Botão "Simular" é substituído por "Nova simulação com esses dados"
  - Clicar em "Nova simulação com esses dados" limpa `open_simulation_id` do storage, desbloqueia o formulário, restaura o botão "Simular" normal — usuário ajusta e simula normalmente
  - `open_simulation_id` é limpo do storage após leitura para evitar recarregamento acidental

**Sem veículo selecionado (compatibilidade retroativa):**
- Veículo placeholder `fonte='manual'` continua sendo criado em `simular()` se nenhum veículo for selecionado.

### Mudança no `simular()` (linhas 136–141 de `simulacao.py`)

```python
# Antes: cria placeholder incondicionalmente
v = Vehicle(fonte="manual", tipo="carro", marca="Manual", ...)

# Depois: usa veículo selecionado ou cria placeholder
if selected_vehicle_id["id"]:
    v = session.get(Vehicle, selected_vehicle_id["id"])
else:
    v = Vehicle(fonte="manual", tipo="carro", marca="Manual", ...)
    session.add(v)
    session.commit()
```

---

## Seção 5 — Navegação

**Arquivo:** `app/ui/layout.py`

- Remover entrada `/fipe` do `TABS`
- Adicionar `{"label": "Veículos", "route": "/veiculos", "icon": "directions_car", "allowed_roles": ["vendedor", "gerente", "admin"]}`
- Ordem: Dashboard → Simulação → Comparativo → **Veículos** → Cadastro → Indicadores → Amortização → Logs → Configurações

**Arquivos removidos:**
- `app/ui/pages/fipe.py`
- Import e chamada `build_fipe_page(engine)` em `app/main.py`

**Arquivos adicionados:**
- `app/ui/pages/veiculos.py`
- Import e chamada `build_veiculos_page(engine)` em `app/main.py`

---

## Seção 6 — Testes

### Novos arquivos de teste

**`tests/unit/services/test_vehicle_service.py`**
- `create_from_fipe` persiste todos os campos corretamente
- `create_manual` persiste todos os campos corretamente
- `set_status` atualiza e registra auditoria
- Placa duplicada em veículo ativo lança `VehicleServiceError`
- Mesma placa permitida após `set_status("vendido")` no veículo anterior
- Placa inválida lança `VehicleServiceError`
- Placa normalizada (minúsculas, hífen) é aceita e armazenada normalizada
- `list_active` exclui veículos `vendido` e `fonte='manual'`
- `get_simulations` retorna simulações vinculadas ordenadas por `criado_em` desc

**`tests/unit/data/test_models_vehicles.py`**
- Novos campos presentes após migração
- Default `status = "disponivel"` aplicado
- Registros `fonte='manual'` recebem `status='vendido'` pela migração

**`tests/integration/test_vehicle_simulation_flow.py`**
- Cadastrar veículo via FIPE → simular com vínculo → verificar `Simulation.veiculo_id` correto
- Simular sem veículo selecionado → placeholder criado, fluxo antigo mantido

---

## Arquivos afetados

| Arquivo | Ação |
|---|---|
| `app/data/models.py` | Adicionar 6 campos ao `Vehicle` |
| `app/data/migrations/versions/YYYYMMDD_*.py` | Nova migração (colunas + índice + seed) |
| `app/services/vehicle_service.py` | **Criar** |
| `app/ui/pages/veiculos.py` | **Criar** |
| `app/ui/pages/simulacao.py` | Nova seção Veículo + modo leitura + `simular()` |
| `app/ui/pages/fipe.py` | **Deletar** |
| `app/ui/layout.py` | Atualizar `TABS` |
| `app/main.py` | Remover `build_fipe_page`, adicionar `build_veiculos_page` |
| `tests/unit/services/test_vehicle_service.py` | **Criar** |
| `tests/unit/data/test_models_vehicles.py` | **Criar** |
| `tests/integration/test_vehicle_simulation_flow.py` | **Criar** |
