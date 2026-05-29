# FinacialSim — Design Spec

> Sistema interno de simulação de financiamento de veículos para uso em loja de carros no Brasil.
> Cálculo financeiro nível banco real (Tabela Price com dias corridos, IOF, CET via TIR).
>
> **Data:** 2026-05-23
> **Atualizado:** 2026-05-28
> **Status:** Implementado (MVP scaffolding completo — core, data, integrations, services, UI, testes)
> **Idioma do produto:** PT-BR (R$, dd/mm/yyyy, separador decimal vírgula)
> **Plataformas:** Windows 10+ e Linux (Ubuntu/Debian/Fedora) e macOS 12+ (Monterey+) — instalação local

---

## 1. Objetivos e capacidades

FinacialSim é um aplicativo desktop multi-perfil para uma loja brasileira, com cálculo financeiro fiel ao praticado por bancos e financeiras brasileiras para CCB de veículos. Os objetivos primários são:

1. Permitir a vendedores leigos simular financiamentos com precisão bancária, em poucos cliques.
2. Vincular simulações a clientes cadastrados e gerar propostas em PDF profissionais.
3. Manter taxas e indicadores econômicos sempre atualizados, com fallback robusto a falhas de rede.
4. Comparar cenários e simular amortizações extraordinárias (parcial, total, reduzir prazo, reduzir parcela).
5. Manter histórico auditável e reproduzível (uma proposta de 2026 deve poder ser regerada em 2027, idêntica).
6. Servir de base modular para futuras integrações (CRM, WhatsApp, geração de carnê, APIs bancárias).

Capacidades resumidas:

- Cadastro de clientes (PF/PJ) com validação de CPF/CNPJ.
- Consulta FIPE com filtros encadeados (tipo → marca → modelo → ano).
- Atualização automática de SELIC, CDI, IPCA, taxa BACEN de veículos, IOF.
- Simulação Tabela Price com dias corridos e primeiro vencimento variável.
- **IOF opcional por simulação** (default ligado): quando ativo, 0,38% fixo + 0,0082%/dia (teto 365 dias) iterado para convergência ao ser incorporado ao principal.
- **Custos adicionais mensais acrescidos à parcela**: plano de proteção veicular (mensal contínuo), IPVA anual com rateio em N meses (default 12), emplacamento + licenciamento com rateio em N meses (default 12), e itens personalizados (rastreador, garantia, etc.).
- CET via TIR exata (Brent) — calculado apenas sobre o fluxo do financiamento (convenção BCB; extras não compõem o CET).
- Cronograma de amortização completo (com colunas de extras e parcela total), com gráficos interativos.
- Comparação lado-a-lado de dois cenários.
- Amortização extraordinária com escolha de modo (parcela ou prazo).
- Geração de PDF de proposta com snapshot reproduzível.
- Backup automático e restauração do banco.
- Logs de execução (técnico) e audit log (negócio).
- Três perfis: vendedor / gerente / administrador.

---

## 2. Decisões arquiteturais aprovadas

| Decisão | Escolha | Justificativa |
| --- | --- | --- |
| Modelo de uso | 1 PC compartilhado pela equipe, SQLite local | Atende a maioria das lojas pequenas/médias |
| Stack de UI | **NiceGUI** (Quasar/Vue) em janela nativa via pywebview | Visual profissional, multiplataforma (Win/Linux/macOS), alto reuso de componentes |
| Precisão financeira | IOF + tarifas + CET via TIR, modo "banco real" | Requisito explícito do cliente |
| Autenticação | PIN numérico 4–6 dígitos por usuário (bcrypt) | Rápido para vendedor, ainda rastreável |
| Arquitetura interna | Monolito modular em camadas (`core` / `data` / `integrations` / `services` / `ui`) | Permite trocar UI ou expor API REST no futuro sem reescrever o core |
| Banco | SQLite + WAL + Alembic migrations | Simples, embutido, evoluível |
| Aritmética | `decimal.Decimal` com `ROUND_HALF_UP`, contexto 28 dígitos | Sem `float` em qualquer ponto financeiro |
| PDF | WeasyPrint (HTML/CSS → PDF) | Templates ricos, reaproveita CSS da UI |
| Empacotamento | PyInstaller `--onedir` + NSIS (Win) / AppImage (Linux) | Instalação fácil sem Python no host |

---

## 3. Stack tecnológica

| Função | Biblioteca | Notas |
|---|---|---|
| UI | NiceGUI + pywebview | Janela nativa ou navegador |
| Gráficos | Plotly + ECharts (embutidos via NiceGUI) | Interativos, exportáveis |
| ORM + migrations | SQLAlchemy 2.x + Alembic | `NUMERIC(18,4)` para campos financeiros |
| Banco | SQLite (WAL) | Embutido |
| Cálculo financeiro | `decimal.Decimal` + bisseção pure-Python 200 iter (TIR) | sem scipy/numpy — decisão intencional (§6.4) |
| HTTP | httpx (async) + tenacity (retry) | Timeout 8s, retry exponencial 3× |
| Validação | Pydantic v2 | Schemas para forms, configs, providers |
| PDF | WeasyPrint + Jinja2 | Template HTML/CSS |
| Localização | Babel + helpers próprios | R$, %, dd/mm/yyyy |
| Auth | bcrypt | PIN hashado |
| Logs | loguru | Rotação diária, gzip após 7 dias |
| Empacotamento | PyInstaller | `--onedir`; NSIS (Win), AppImage (Linux) |
| Agendador | APScheduler (`services/scheduler.py`) | Updates de indicadores, backup, health-check |
| Testes | pytest + hypothesis | Property tests para o core financeiro |

---

## 4. Estrutura de diretórios

```
finacialsim/
├── app/
│   ├── __init__.py
│   ├── main.py                    # ponto de entrada; inicia NiceGUI + pywebview
│   │                              # NOTE: app/config/ (settings.py + rules.py) não implementado;
│   │                              #       regras de negócio vivem em BusinessRule + rules_service.py
│   │
│   ├── core/                      # DOMÍNIO PURO — sem dependência de UI/DB
│   │   ├── money.py               # Decimal + arredondamento bancário
│   │   ├── price_table.py         # Tabela Price exata + dias corridos
│   │   ├── iof.py                 # IOF veículo (0,38% + 0,0082%/dia)
│   │   ├── cet.py                 # CET via bisseção pure-Python (sem scipy)
│   │   ├── amortization.py        # cronograma + amortização extraordinária
│   │   ├── extras.py              # custos adicionais mensais (§6.5)
│   │   ├── rate_suggestions.py    # taxa sugerida por prazo
│   │   └── validators.py          # entrada mínima, prazos válidos
│   │
│   ├── data/                      # PERSISTÊNCIA
│   │   ├── database.py            # engine + Base + get_session_factory
│   │   ├── models.py              # ORM SQLAlchemy
│   │   ├── repositories.py        # CRUD tipado por entidade
│   │   ├── migrations/            # Alembic
│   │   └── backup.py              # backup automático SQLite (primitivas)
│   │
│   ├── integrations/              # APIs EXTERNAS — chain de fallback
│   │   ├── base.py                # Protocol Provider + ProviderChain + Ok/Err
│   │   ├── http.py                # shared httpx helper (timeout 8s, User-Agent)
│   │   ├── factory.py             # build_fipe_chain / build_bacen_chain
│   │   ├── fipe/
│   │   │   ├── schema.py          # VehicleQuote dataclass normalizado
│   │   │   ├── parallelum.py      # primário
│   │   │   ├── brasilapi.py       # fallback
│   │   │   ├── cache.py           # decorator com TTL sobre fipe_cache (era cached.py no spec)
│   │   │   └── manual.py          # entrada manual
│   │   └── bacen/
│   │       ├── schema.py          # IndicatorPoint dataclass + conversions
│   │       ├── sgs.py             # SELIC/CDI/IPCA via api.bcb.gov.br
│   │       ├── brasilapi.py       # fallback
│   │       ├── cached.py          # cache em disco
│   │       └── conversions.py     # conversões entre unidades (mensal↔anual↔diária)
│   │
│   ├── services/                  # ORQUESTRAÇÃO (caso-de-uso)
│   │   ├── simulation_service.py
│   │   ├── comparison_service.py
│   │   ├── amortization_service.py
│   │   ├── proposal_service.py    # gera PDF
│   │   ├── client_service.py
│   │   ├── auth_service.py
│   │   ├── indicators_service.py
│   │   ├── audit_service.py
│   │   ├── backup_service.py      # facade sobre data/backup.py para UI/scheduler
│   │   ├── rules_service.py       # CRUD de business_rules (foi app/config/rules.py no spec)
│   │   └── scheduler.py           # APScheduler (movido de utils/ para services/)
│   │
│   ├── ui/                        # NiceGUI — só apresentação
│   │   ├── theme.py
│   │   ├── layout.py              # shell() + TABS com guards por perfil
│   │   ├── router.py              # helpers de navegação + get_logged_perfil
│   │   ├── components/
│   │   │   ├── currency_input.py
│   │   │   ├── percent_input.py
│   │   │   ├── kpi_card.py
│   │   │   ├── amortization_table.py
│   │   │   └── charts.py
│   │   └── pages/
│   │       ├── login.py
│   │       ├── cadastro.py
│   │       ├── dashboard.py
│   │       ├── simulacao.py
│   │       ├── comparativo.py
│   │       ├── amortizacao.py
│   │       ├── indicadores.py
│   │       ├── veiculos.py        # inventário de estoque — FIPE picker + gestão de veículos (nova, não estava no spec original)
│   │       ├── configuracoes.py
│   │       ├── apis.py            # existe mas NÃO está registrado em main.py (pendente)
│   │       ├── logs.py
│   │       ├── docs.py
│   │       └── _proposal_helper.py  # helpers para geração de proposta
│   │
│   ├── reports/
│   │   ├── proposta.html          # template Jinja2 → WeasyPrint (proposta em PDF)
│   │   ├── proposta.css           # estilos do PDF
│   │   ├── carne.html             # template Jinja2 → WeasyPrint (carnê de pagamento) [IMPLEMENTADO]
│   │   └── carne.css              # estilos do carnê
│   │
│   └── utils/
│       ├── br_format.py
│       ├── document_validation.py # validação CPF/CNPJ (era parte de core/validators no spec)
│       └── logger.py
│
├── tests/
│   ├── unit/core/                 # bateria pesada de cálculo
│   ├── unit/services/
│   └── integration/
│
├── scripts/
│   ├── install_windows.ps1
│   ├── install_linux.sh
│   ├── install_macos.sh
│   ├── build_exe.py
│   └── seed_demo.py
│
├── docs/
│   ├── ARQUITETURA.md
│   ├── DOCUMENTACAO.md
│   ├── guia_usuario.md
│   ├── matematica_price.md
│   └── troubleshooting.md
│
├── data/                          # banco + backups (gerado em runtime)
├── logs/
├── pyproject.toml
├── alembic.ini
└── README.md
```

### Princípios de camadas

- `core/` **não importa** de `ui/`, `data/`, `integrations/` ou `services/`. É puro, testável e reaproveitável.
- `services/` é a única camada que orquestra `core/` + `data/` + `integrations/`.
- `ui/` jamais toca repositórios ou providers diretamente — sempre via `services/`.
- `integrations/` segue `ProviderChain` (primário → secundário → manual), isolando fragilidade.

---

## 5. Modelo de dados (SQLite + SQLAlchemy)

Todas as colunas financeiras são `NUMERIC(18,4)` (Decimal no ORM). Datas usam tipos SQLAlchemy `Date`/`DateTime` (ISO-8601 no SQLite).

### 5.1 Usuários e clientes

**`users`**

- `id` PK
- `nome` TEXT NOT NULL
- `pin_hash` TEXT NOT NULL (bcrypt)
- `perfil` TEXT NOT NULL — `vendedor` | `gerente` | `admin`
- `ativo` BOOLEAN DEFAULT 1
- `criado_em`, `atualizado_em`, `ultimo_login` DATETIME

**`clients`**

- `id` PK
- `nome` TEXT NOT NULL
- `cpf_cnpj` TEXT UNIQUE — validado mod-11
- `tipo` TEXT — `PF` | `PJ`
- `rg`, `data_nasc`, `profissao`, `renda` (NUMERIC 18,2)
- `telefone`, `email`
- `endereco_json` TEXT — logradouro, número, complemento, bairro, cidade, UF, CEP
- `observacoes` TEXT
- `criado_por` FK→`users.id`
- `criado_em`, `atualizado_em`

### 5.2 Veículos e simulações

**`vehicles`** (inventário de estoque — não é mais snapshot por simulação)

- `id` PK
- `fonte` TEXT — `fipe_parallelum` | `fipe_brasilapi` | `manual`
- `tipo`, `marca`, `modelo`, `ano_modelo` INTEGER, `combustivel`
- `codigo_fipe` TEXT
- `valor_fipe` NUMERIC(18,2)
- `valor_referencia` NUMERIC(18,2) — valor real de venda (ajustável independente do FIPE)
- `mes_referencia_fipe` TEXT
- `cor` TEXT
- `placa` TEXT UNIQUE — formato antigo (ABC1234) ou Mercosul (ABC1D23); nullable para veículos sem placa ainda
- `odometro_km` INTEGER
- `status` TEXT DEFAULT 'disponivel' — `disponivel` | `reservado` | `vendido`
- `snapshot_json` TEXT — payload bruto da API (auditável)
- `criado_por` FK→`users.id`
- `criado_em`, `atualizado_em`

**`simulations`**

- `id` PK
- `codigo` TEXT UNIQUE — `SIM-2026-00123`
- `cliente_id` FK→`clients.id` NULLABLE
- `veiculo_id` FK→`vehicles.id`
- `criado_por` FK→`users.id`
- `valor_veiculo`, `valor_entrada` NUMERIC(18,2)
- `pct_entrada` NUMERIC(7,4)
- `prazo_meses` INTEGER
- `taxa_juros_mes` NUMERIC(10,8) — fração (0.01650000 = 1,65% a.m.)
- `taxa_juros_ano` NUMERIC(10,8) — equivalente anual
- `data_liberacao`, `data_primeiro_venc` DATE
- `dias_carencia` INTEGER — derivado
- `incluir_iof` BOOLEAN DEFAULT TRUE — toggle por simulação (§6.3)
- `iof_total`, `tarifas_total`, `extras_total_acumulado`, `valor_financiado`, `valor_parcela`, `total_pago`, `total_juros` NUMERIC(18,2)
- `pct_juros` NUMERIC(7,4)
- `cet_mes`, `cet_ano` NUMERIC(10,8)
- `status` TEXT — `rascunho` | `finalizada` | `arquivada`
- `rules_snapshot_json` TEXT — regras vigentes na criação (reproduzibilidade)
- `criado_em`, `atualizado_em`

**`simulation_fees`**

- `id` PK
- `simulation_id` FK→`simulations.id`
- `nome` TEXT — `Cadastro`, `Avaliação`, `Registro`, custom
- `valor` NUMERIC(18,2)
- `incluir_no_principal` BOOLEAN

**`simulation_extras`** — custos adicionais mensais acrescidos à parcela (§6.5)

- `id` PK
- `simulation_id` FK→`simulations.id`
- `tipo` TEXT — `protecao_veicular` | `ipva` | `emplacamento` | `seguro` | `custom`
- `nome` TEXT — descrição amigável exibida (ex.: "Plano de proteção veicular Mensal")
- `valor_total` NUMERIC(18,2) — valor mensal (modalidade `mensal_continuo`) ou anual (modalidade `rateio_meses`)
- `modalidade` TEXT — `mensal_continuo` (sempre durante todo o prazo) | `rateio_meses` (rateado em N primeiras parcelas) | `unico_inicial` (uma vez na 1ª parcela)
- `duracao_meses` INTEGER — quantas parcelas recebem o lançamento (para `mensal_continuo` = prazo total; para `rateio_meses` = N; para `unico_inicial` = 1)
- `valor_por_parcela` NUMERIC(18,4) — derivado: `valor_total / duracao_meses` (cached para evitar recálculo)
- `ordem` INTEGER — ordem de exibição no PDF e UI

**`amortization_rows`**

- `id` PK
- `simulation_id` FK→`simulations.id` (índice)
- `numero_parcela` INTEGER
- `data_vencimento` DATE
- `dias_periodo` INTEGER
- `saldo_anterior`, `juros`, `amortizacao`, `parcela`, `saldo_devedor` NUMERIC(18,4)
- `extras_total` NUMERIC(18,4) — soma dos extras aplicáveis a esta parcela
- `parcela_total` NUMERIC(18,4) — `parcela + extras_total` (valor que o cliente paga no mês)
- `ajuste_arredondamento` NUMERIC(18,4) — resíduo na última parcela

**`extraordinary_amortizations`**

- `id` PK
- `simulation_id` FK→`simulations.id`
- `data` DATE
- `valor` NUMERIC(18,2)
- `modo` TEXT — `reduzir_parcela` | `reduzir_prazo`
- `tipo` TEXT — `parcial` | `total`
- `aplicado_em` DATETIME

### 5.3 Propostas e comparações

**`proposals`**

- `id` PK
- `codigo` TEXT UNIQUE — `PROP-2026-00123`
- `simulation_id` FK→`simulations.id`
- `cliente_id` FK→`clients.id`
- `gerado_por` FK→`users.id`
- `snapshot_json` TEXT — tudo congelado para reproduzir o PDF
- `pdf_path` TEXT
- `carne_path` TEXT — caminho do carnê PDF gerado (opcional, preenchido por `generate_carne()`)
- `validade_dias` INTEGER
- `gerado_em` DATETIME

**`comparisons`**

- `id` PK
- `simulation_a_id`, `simulation_b_id` FK→`simulations.id`
- `criado_por` FK→`users.id`
- `criado_em`

### 5.4 Indicadores, regras, auditoria, config

**`indicators_history`**

- `id` PK
- `codigo` TEXT — `SELIC` | `CDI` | `IPCA` | `IOF_FIXO` | `IOF_DIARIO` | `TX_BACEN_VEIC`
- `data_referencia` DATE
- `valor` NUMERIC(12,8) — sempre em fração decimal
- `unidade` TEXT — `pct_aa` | `pct_am` | `pct_ad`
- `fonte` TEXT — `bcb_sgs` | `brasilapi` | `manual`
- `payload_json` TEXT
- `coletado_em` DATETIME
- UNIQUE(`codigo`, `data_referencia`)

**`business_rules`**

- `id` PK
- `chave` TEXT UNIQUE — `entrada_minima_pct`, `taxa_por_prazo_curva`, `incluir_iof_default`, `iof_fixo_pct`, `iof_diario_pct`, `iof_diario_max_dias`, `dias_max_carencia`, `prazo_minimo_meses`, `prazo_maximo_meses`, `taxa_minima_mes`, `taxa_maxima_mes`, `valor_minimo_financiado`, `extras_padrao`, `rateio_ipva_meses_default`, `rateio_emplacamento_meses_default` (lista completa em §12)
- `valor_json` TEXT
- `descricao` TEXT
- `atualizado_em`, `atualizado_por` FK→`users.id`

**`audit_log`**

- `id` PK
- `timestamp` DATETIME
- `usuario_id` FK→`users.id`
- `acao` TEXT — `login`, `sim_criada`, `sim_editada`, `proposta_gerada`, `config_alterada`, `migration_applied`, etc.
- `entidade`, `entidade_id`
- `diff_json` TEXT — antes/depois
- `ip`, `hostname` TEXT

**`app_settings`**

- `chave` PK TEXT
- `valor_json` TEXT
- `atualizado_em` DATETIME

**`fipe_cache`**

- `id` PK
- `tipo` TEXT
- `acao` TEXT — tipo de requisição (`brands`, `models`, `years`, `price`, etc.)
- `marca_id`, `modelo_id`, `ano_id` TEXT (nullable)
- `payload_json` TEXT
- `coletado_em` DATETIME
- `ttl_horas` INTEGER (default 720 = 30 dias)
- UNIQUE(`tipo`, `acao`, `marca_id`, `modelo_id`, `ano_id`)

### 5.5 Decisões importantes do modelo

- **Snapshot JSON em `vehicles`, `simulations.rules_snapshot_json`, `proposals.snapshot_json`** garante reproduzibilidade ao longo dos anos.
- `amortization_rows` materializada (não recalculada) evita drift de arredondamento e carrega `extras_total` + `parcela_total` por parcela.
- `simulation_extras` em tabela própria 1:N permite extensão para novos tipos (rastreador, seguros adicionais) sem alterar schema.
- `indicators_history` com UNIQUE permite upsert idempotente diário.
- `extraordinary_amortizations` em separado preserva cronograma original e permite reverter.
- `audit_log.diff_json` cobre o requisito "logs de alterações" sem versionar cada tabela.
- `fipe_cache` com TTL reduz dependência de rede (FIPE muda mensalmente).

---

## 6. Core financeiro

### 6.1 Base — `money.py`

```python
from decimal import Decimal, getcontext, ROUND_HALF_UP
getcontext().prec = 28

CENTAVO  = Decimal("0.01")
PCT_DEC  = Decimal("0.0001")
TAXA_DEC = Decimal("0.00000001")

def quantize_brl(v: Decimal) -> Decimal:
    return v.quantize(CENTAVO, rounding=ROUND_HALF_UP)
```

Política de arredondamento: **half-up** em 2 casas para R$. Resíduo do arredondamento do cronograma vai **integralmente na última parcela**, garantindo saldo devedor zero exato.

### 6.2 Tabela Price com dias corridos — `price_table.py`

Modelo de capitalização exponencial fracionada (convenção BACEN/CCB):

- `i_m` = taxa mensal nominal (fração)
- `i_d = (1 + i_m)^(1/30) − 1` = taxa diária equivalente
- `d1` = dias entre liberação e primeiro vencimento
- `n` = número de parcelas (intervalos de 30 dias após `d1`)

**Parcela fixa:**

```text
PMT = PV · (1+i_d)^d1 · (i_m · (1+i_m)^(n-1)) / ((1+i_m)^n − 1)
```

Quando `d1 = 30`, reduz-se à Tabela Price clássica `PMT = PV · i · (1+i)^n / ((1+i)^n − 1)`.

**Cronograma:**

- Parcela 1: `juros = PV · ((1+i_d)^d1 − 1)`; `amortização = PMT − juros`; `saldo = PV − amortização`
- Parcelas 2..n−1: `juros = saldo · i_m`; `amortização = PMT − juros`
- Parcela n: força saldo → 0; resíduo em `ajuste_arredondamento`

**Saída:**

```python
@dataclass
class Schedule:
    rows: list[ScheduleRow]
    pmt: Decimal
    total_pago: Decimal
    total_juros: Decimal
    saldo_residual: Decimal     # 0 após ajuste
```

### 6.3 IOF veículo (opcional) — `iof.py`

**O IOF é opcional por simulação**, controlado pela flag `simulations.incluir_iof`. Default `true` (cobrar IOF — comportamento padrão de bancos). Vendedor pode desligar para simulações em que o IOF é cobrado fora do principal ou em cenários hipotéticos.

Regulamento: Decreto 6.306/2007. Percentuais ficam em `business_rules`.

- **Fixo**: 0,38% × valor financiado
- **Diário**: 0,0082% × min(dias até vencimento da parcela, 365), aplicado sobre a amortização daquela parcela
- **Total** = fixo + Σ diário por parcela

**Fórmula (quando `incluir_iof = true`):**

```
IOF_fixo    = 0.0038 × valor_financiado
IOF_diario  = Σ_k [ amortização_k × 0.000082 × min(dias_até_venc_k, 365) ]
IOF_total   = IOF_fixo + IOF_diario
```

**Circularidade quando incorporado ao principal** — resolvida por iteração:

```text
PV₀ = valor_veículo − entrada + tarifas_incluídas
PV_{n+1} = PV₀ + IOF(PV_n, cronograma(PV_n))
parar quando |PV_{n+1} − PV_n| < R$ 0,01
```

Converge em 2–3 iterações na prática.

**Quando `incluir_iof = false`:**

- IOF não é iterado nem somado ao principal
- `PV = valor_veículo − entrada + tarifas_incluídas` (uma única passada)
- `simulations.iof_total = 0`
- UI mostra badge informativo "IOF não incluído nesta simulação"

> **Importante:** desligar o IOF afasta a simulação do "modo banco real". Use apenas quando a loja sabe que o IOF será cobrado externamente. O CET (§6.4) continua sendo calculado normalmente sobre o fluxo resultante.

### 6.4 CET via TIR — `cet.py`

CET é a TIR mensal do fluxo de caixa do **financiamento** (do ponto de vista do cliente):

- `t = 0`: cliente recebe (em seu favor) `valor_veículo − entrada`
- `t = d1, d1+30, ...`: cliente paga `PMT` (parcela do financiamento, **sem incluir extras**)

Encontrar `i_cet` tal que:

```text
(valor_veículo − entrada) = Σ_{k=1}^{n} PMT / (1 + i_cet)^(k * d1/30)
```

Resolvido com **bisseção pure-Python** (200 iterações, tolerância 1e-10) no intervalo `[1e-8, 1.0]`.

> **Decisão de implementação:** `scipy.optimize.brentq` foi substituído por bisseção pure-Python para evitar ~35MB de deps C. A função é suave o bastante que bisseção converge em <200 iterações. **Modelo de timing:** `meses = numero_parcela * (d1/30.0)` — garante CET == taxa_nominal quando não há IOF nem extras.
>
> **Convenção BCB:** o CET reflete apenas o custo do crédito. Custos adicionais (proteção veicular, IPVA, emplacamento — §6.5) **não entram no cálculo do CET**, porque são despesas externas ao crédito (serviços e tributos do veículo). Eles aparecem no cronograma e no PDF como linhas separadas, mas não distorcem o CET.

Saída:

- `cet_mes` (Decimal, 8 casas)
- `cet_ano = (1 + cet_mes)^12 − 1`

### 6.5 Custos adicionais mensais (extras) — `extras.py`

A parcela paga pelo cliente todo mês pode incluir **custos externos ao financiamento** que a loja embute no boleto/débito para facilitar a cobrança. Modelados na tabela `simulation_extras` (§5.2).

**Tipos suportados de fábrica:**

| Tipo | Modalidade típica | Significado |
| --- | --- | --- |
| `protecao_veicular` | `mensal_continuo` | Plano de proteção/seguro mensal durante TODO o prazo do financiamento |
| `ipva` | `rateio_meses` (default 12) | IPVA anual rateado em N primeiras parcelas |
| `emplacamento` | `rateio_meses` (default 12) | Emplacamento + licenciamento rateados em N primeiras parcelas |
| `seguro` / `custom` | livre | Outros itens (rastreador, garantia estendida, etc.) |

**Modalidades:**

- **`mensal_continuo`** — `valor_total` é mensal; aplicado em todas as `prazo_meses` parcelas → `valor_por_parcela = valor_total`
- **`rateio_meses`** — `valor_total` é anual/global; rateado em `duracao_meses` (default 12) primeiras parcelas → `valor_por_parcela = valor_total / duracao_meses`
- **`unico_inicial`** — `valor_total` adicionado integralmente à 1ª parcela → `duracao_meses = 1`

**Composição da parcela exibida:**

```text
parcela_total[k] = parcela_financiamento[k] + Σ_extras_aplicáveis_à_parcela_k

extras_aplicáveis_à_parcela_k = { e ∈ simulation_extras
                                  | k está dentro do intervalo de aplicação de e }
```

**Persistência:**

- `amortization_rows.extras_total` materializa o somatório por parcela (auditável)
- `amortization_rows.parcela_total` = `parcela + extras_total`
- `simulations.extras_total_acumulado` = soma de todos os extras ao longo de todas as parcelas (informativo)

**O que extras NÃO afetam:**

- `PMT` (parcela do financiamento) — calculada apenas com `PV`, taxa e prazo
- `valor_financiado` — extras não são financiados (não incidem juros)
- `IOF` — não incide sobre extras
- `CET` — extras são serviços externos ao crédito (§6.4)

**O que extras afetam:**

- `parcela_total` mostrada para o cliente
- `total_pago_cliente` (informativo): `total_pago_financiamento + extras_total_acumulado`
- Cronograma exibido no PDF e na UI
- Comparativo entre cenários (mostra parcela total além da parcela do financiamento)

### 6.6 Taxa sugerida por prazo — `rate_suggestions.py`

Curva configurável em `business_rules.taxa_por_prazo_curva`:

```json
[
  { "ate_meses": 24, "taxa_mensal": 0.0149 },
  { "ate_meses": 36, "taxa_mensal": 0.0169 },
  { "ate_meses": 48, "taxa_mensal": 0.0189 },
  { "ate_meses": 60, "taxa_mensal": 0.0199 },
  { "ate_meses": 72, "taxa_mensal": 0.0219 }
]
```

Comportamento: se taxa atual < sugerida, UI mostra badge amarelo com botão "usar sugerida". Não bloqueia.

### 6.7 Validações — `validators.py`

Regras configuráveis (todas em `business_rules`):

- `entrada_minima_pct` (default **10%**)
- `prazo_minimo_meses` (12) / `prazo_maximo_meses` (72)
- `taxa_minima_mes` (0,5%) / `taxa_maxima_mes` (5%)
- `dias_max_carencia` (90)
- `valor_minimo_financiado` (R$ 5.000)
- Validações específicas de extras: `valor_total ≥ 0`, `duracao_meses ≥ 1`, `duracao_meses ≤ prazo_meses` (não pode ratear além do prazo do financiamento)

Cada violação retorna `ValidationIssue(level='error'|'warning', field, message)`. Errors bloqueiam; warnings exibem badge na UI.

### 6.8 Amortização extraordinária — `amortization.py`

Entrada: simulação + lista de pagamentos extras `(data, valor, modo)`.

Algoritmo:

1. Percorre cronograma original aplicando pagamento extra na data (paga juros pro-rata até a data, depois reduz saldo)
2. Modo `reduzir_prazo`: mantém PMT; recalcula quantas parcelas restantes cabem
3. Modo `reduzir_parcela`: mantém prazo; recalcula PMT para saldo restante
4. Quitação total: saldo + juros pro-rata até a data; retorna desconto vs. somar parcelas remanescentes

Resultado é um **novo cronograma persistido em paralelo** (não destrói o original).

**Tratamento de extras na amortização extraordinária:**

- Extras `mensal_continuo` reduzem proporcionalmente ao novo prazo (param de incidir após a quitação)
- Extras `rateio_meses` ainda no período de rateio: continuam sendo cobrados nas próximas parcelas até completar o rateio (são despesas do veículo, não do financiamento — quitar o financiamento não as cancela)
- Comportamento explícito documentado no `guia_usuario.md`

### 6.9 Testes do core

Indispensáveis:

- **Casos conhecidos**: cronogramas de simuladores reais (Santander, Itaú, Bradesco) com mesma entrada → bate centavo a centavo
- **Property tests (hypothesis)**: para qualquer `(PV, i, n, d1)` válido, `Σ amortizações ≈ PV`, `saldo_final == 0`, `parcelas > 0`
- **Casos-borda**: `d1 = 0`, `d1 = 90`, `n = 1`, taxa próxima de 0%
- **IOF opcional**: comparação `incluir_iof=true` vs `incluir_iof=false` no mesmo cenário; diferença bate com cálculo manual do IOF
- **Extras**: rateio 12x do IPVA bate com `valor_anual / 12`; proteção veicular mensal incide em todas as parcelas; extras NÃO alteram PMT/CET

---

## 7. Integrações externas

### 7.1 Padrão `ProviderChain` — `integrations/base.py` + `integrations/factory.py`

`base.py` define `Provider` (Protocol), `ProviderChain`, e os tipos `Ok[T]` / `Err` (Result pattern):

```python
class Provider(Protocol):
    name: str
    async def fetch(self, query: dict) -> Ok[Any] | Err: ...

class ProviderChain:
    async def fetch(self, query) -> Ok[Any] | Err:
        for p in self.providers:
            result = await p.fetch(query)
            if result.is_ok:
                return result
        return Err("all_providers_failed: ...")
```

`factory.py` expõe `build_fipe_chain(session_factory)` e `build_bacen_chain(session_factory)` que montam as chains com cache. `http.py` centraliza o cliente httpx (timeout 8s, User-Agent `FinacialSim/0.1`).

- HTTP: `httpx.AsyncClient`, timeout 8s — via `integrations/http.py`
- Retry: `tenacity` disponível mas não aplicado em todas as chamadas ainda
- User-Agent identificando app + versão

### 7.2 FIPE — `integrations/fipe/`

**Primário — Parallelum FIPE API**

- Base: `https://parallelum.com.br/fipe/api/v2`
- Endpoints:
  - `GET /{tipo}/brands` — `tipo` ∈ `cars`, `motorcycles`, `trucks`
  - `GET /{tipo}/brands/{brandId}/models`
  - `GET /{tipo}/brands/{brandId}/models/{modelId}/years`
  - `GET /{tipo}/brands/{brandId}/models/{modelId}/years/{yearId}`

**Fallback 1 — BrasilAPI**

- Base: `https://brasilapi.com.br/api/fipe`
- Endpoints: `/marcas/v1/{tipo}`, `/preco/v1/{codigoFipe}`
- Schema adaptado para `VehicleQuote` interno

**Fallback 2 — Manual**

- Vendedor digita tipo/marca/modelo/ano/valor; gravado com `fonte='manual'`

**Cache** — `fipe/cache.py` (implementado como `cached.py` no spec original)

- Decorator sobre provider
- TTL: 30 dias para listas, 24h para preço
- Tabela `fipe_cache`

**Schema normalizado:**

```python
@dataclass
class VehicleQuote:
    tipo: Literal["carro", "moto", "caminhao"]
    marca: str
    marca_id: str
    modelo: str
    modelo_id: str
    ano_modelo: int
    combustivel: str
    codigo_fipe: str
    valor: Decimal               # parseado de "R$ 45.230,00"
    mes_referencia: str
    fonte: str
    raw_payload: dict
```

### 7.3 Indicadores econômicos — `integrations/bacen/`

**Primário — BCB SGS**

- Base: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=...&dataFinal=...`
- Códigos:
  - `SELIC_META`: 432 (% a.a.)
  - `SELIC_DIARIA`: 11 (% a.d.)
  - `CDI`: 12 (% a.d.)
  - `IPCA`: 433 (% a.m.)
  - `TX_BACEN_VEIC`: 20714 (taxa média mensal — crédito PF aquisição veículos)
- Retorno: `[{"data": "23/05/2026", "valor": "10.50"}, ...]`

**Fallback 1 — BrasilAPI**

- `/taxas/v1/{selic|cdi|ipca}` — só último valor

**Fallback 2 — Cache local + manual**

- Usa último valor de `indicators_history` com flag `stale`
- UI mostra badge laranja "Indicador desatualizado há X dias"
- Admin pode forçar valor manual em Configurações

**IOF** — não vem de API. Vive em `business_rules` (0,38% fixo + 0,0082%/dia). Alterado por admin se a regra mudar.

**Normalização canônica:**

```python
@dataclass
class IndicatorPoint:
    codigo: str
    data_referencia: date
    valor_fracao: Decimal        # SEMPRE em fração decimal (0.015 = 1,5%)
    unidade: Literal["pct_aa", "pct_am", "pct_ad"]
    fonte: str
```

Conversões aplicadas no adapter:

- BCB SGS retorna `"10.50"` → `Decimal("10.50") / 100`
- Detecta unidade pela série (CDI=`pct_ad`, IPCA=`pct_am`, SELIC=`pct_aa`)
- Rejeita valor fora de `[0, 1]` em fração ou `[0, 100]` em pct — loga erro

**Conversões entre unidades — `bacen/conversions.py`:**

- Mensal → anual: `(1+i_m)^12 − 1`
- Diária (252) → mensal: `(1+i_d)^21 − 1`
- Diária (252) → anual: `(1+i_d)^252 − 1`
- Anual → mensal: `(1+i_a)^(1/12) − 1`

UI sempre mostra mensal e anual lado a lado para evitar confusão.

### 7.4 Agendamento — `services/scheduler.py` (movido de `utils/` para `services/`)

APScheduler em background no processo NiceGUI:

| Job | Frequência | Ação |
|---|---|---|
| `update_bacen_indicators` | Diária 09:00 | Upsert em `indicators_history` |
| `prune_fipe_cache` | Diária 03:00 | Remove além do TTL |
| `backup_sqlite` | Diária 23:00 | `.backup` + zip + retenção 30 dias |
| `verify_provider_health` | A cada 6h | Ping nos providers; status na aba APIs |

Cada job:

- Loga início/fim em `audit_log` (`acao='scheduled_job'`)
- Em falha, incrementa contador; badge vermelho na aba APIs
- Falhas não travam o app

### 7.5 Aba APIs (resumo — detalhado em §8.8)

Visível para gerente/admin: status, atualizar agora, reordenar chain, habilitar/desabilitar providers, histórico das últimas 50 chamadas.

---

## 8. Fluxos das 10 abas, navegação e perfis

### Layout geral

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ [Logo loja]        FinacialSim — Simulador de Financiamentos             │
│                                                  [Vendedor: João] [⚙] [⎋]│
├──────────────────────────────────────────────────────────────────────────┤
│ 📊 Dashboard  📋 Cadastro  💰 Simulação  ⚖ Comparativo  ⏩ Amortização   │
│ 📈 Indicadores  🚗 Veículos  ⚙ Configurações  📝 Logs  📚 Documentação    │
├──────────────────────────────────────────────────────────────────────────┤
│                       [conteúdo da aba selecionada]                      │
└──────────────────────────────────────────────────────────────────────────┘
```

> **Nota de implementação:** A aba "🔌 APIs" (originalmente no spec) não está registrada na navegação principal (`layout.py`). O arquivo `pages/apis.py` existe mas a rota `/apis` não é montada em `main.py` — está pendente de integração. No lugar, foi adicionada a aba "🚗 Veículos" (inventário de estoque com FIPE picker integrado como componente — `pages/veiculos.py`).

Abas restritas por perfil ficam **ocultas**, não apenas desabilitadas.

### Visibilidade por perfil (implementado em `layout.py`)

| Aba | Vendedor | Gerente | Admin |
| --- | :---: | :---: | :---: |
| Cadastro de clientes | ✅ | ✅ | ✅ |
| Cadastro de usuários | ❌ | ❌ | ✅ |
| Dashboard | ✅ (próprio) | ✅ (loja) | ✅ |
| Simulação | ✅ | ✅ | ✅ |
| Comparativo | ✅ | ✅ | ✅ |
| Amortização | ✅ | ✅ | ✅ |
| Indicadores (leitura) | ✅ | ✅ | ✅ |
| Veículos (inventário) | ✅ | ✅ | ✅ |
| Indicadores (editar) | ❌ | ⚠️ valores manuais | ✅ |
| Configurações (regras) | ❌ | ⚠️ visualizar | ✅ |
| APIs *(pendente de integração)* | ❌ | ✅ | ✅ |
| Logs | ❌ | ✅ (próprios + equipe) | ✅ (tudo) |
| Documentação | ✅ | ✅ | ✅ |

### 8.0 Login

- Dropdown "Usuário" com avatares dos usuários ativos
- Input "PIN" (4–6 dígitos, mascarado)
- 5 tentativas erradas → bloqueio de 5 min para aquele usuário
- Após login: `audit_log("login")` e abre Dashboard

### 8.1 Cadastro

Duas sub-abas (admin vê ambas; vendedor só "Clientes"):

**Clientes**

- Tabela paginada com busca por nome/CPF
- "+ Novo cliente" → modal:
  - Toggle PF/PJ alterna campos
  - PF: nome, CPF (mod-11), RG, data nasc, profissão, renda mensal
  - PJ: razão social, CNPJ, IE, faturamento
  - Telefone, email, endereço (auto-preenchido por CEP via BrasilAPI)
  - Observações
- Edição/desativação em-place
- "→ Nova simulação para este cliente" leva para Simulação pré-preenchida

**Usuários** (admin)

- Listar, criar, alterar PIN, alterar perfil, desativar
- Última atividade

### 8.2 Dashboard

Cards superiores (KPIs do mês):

- Nº de simulações
- Nº de propostas geradas
- Ticket médio financiado
- Taxa média praticada

Gráficos:

- Distribuição de prazos (barras: 24/36/48/60/72m)
- Mix de cenários (pizza PF vs PJ ou marcas mais simuladas)
- Indicadores econômicos atuais (mini-cards: SELIC, CDI, IPCA, Tx BACEN veículos)
- Evolução do saldo devedor médio
- Simulações recentes (últimas 10, click → abrir)

Vendedor vê apenas dados próprios; gerente/admin veem toda a loja com filtro por vendedor.

### 8.3 Simulação

Layout em 3 colunas.

**Esquerda — Entrada**

1. Cliente (combobox com busca, opcional)
2. Veículo:
   - Seleção do estoque (dropdown dos veículos `disponivel`/`reservado` do Cadastro de Veículos)
   - Botões para ver valor FIPE e ajustar valor de referência
   - Card mostra valor FIPE + mês de referência + valor de venda utilizado
   - Novos veículos são cadastrados na aba Veículos (via FIPE picker ou manual), não inline aqui
3. Valor do veículo (currency, pré-preenchido)
4. Entrada — R$ ou %, sincronizados
5. Prazo (meses) — slider 12–72 + input livre
6. Taxa mensal — badge sugerindo taxa por prazo
7. Data de liberação (default hoje)
8. Data 1° vencimento (default +30d; mostra dias de carência)
9. Tarifas (expansível): cadastro, avaliação, registro — toggle "incluir no principal"
10. **IOF** (expansível): toggle "Incluir IOF nesta simulação" (default ligado). Quando desligado, exibe badge informativo.
11. **Custos adicionais mensais** (expansível): cada linha permite adicionar/remover/editar:
    - **Plano de proteção veicular** — valor R$/mês, modalidade "mensal contínuo" (preenchido em todas as parcelas)
    - **IPVA anual** — valor R$ anual, modalidade "rateio em N meses" (default N=12)
    - **Emplacamento + licenciamento** — valor R$ total, modalidade "rateio em N meses" (default N=12)
    - **+ Adicionar custo personalizado** (rastreador, garantia estendida, etc.)
    - Cada linha mostra preview "= R$ X,XX por parcela"

Botão "Simular" + recálculo em tempo real ao alterar campos (debounced 400ms).

**Central — Resultado (cards)**

- **Parcela do financiamento** (PMT — valor fixo das parcelas do banco)
- **Parcela total — 1º ano** (PMT + extras_total no período de rateio, ex.: meses 1–12)
- **Parcela total — após rateio** (PMT + apenas extras mensais contínuos, ex.: meses 13+)
- Valor financiado / Total pago no financiamento / Total de juros / % juros / CET a.m. e a.a.
- **Total pago pelo cliente** (informativo: financiamento + extras acumulados)
- Cada card tem ícone "👁" para ocultar

> Se não houver extras com `rateio_meses < prazo_total`, mostra apenas um card "Parcela total" único.

**Direita — Visualizações**

- Composição da parcela (barras empilhadas: juros + amortização + extras por categoria)
- Saldo devedor (linha decrescente)
- **Curva de parcela total ao longo do tempo** (linha — mostra "degrau" quando rateios terminam)
- Tabela de amortização completa com colunas extras (expand, exportável CSV)

**Rodapé**

- Salvar simulação
- Gerar proposta PDF (requer cliente)
- Comparar com outra (envia para Comparativo)
- Simular amortização extra (envia para Amortização)

### 8.4 Comparativo

Duas colunas espelhadas A/B com mesmo formulário compacto. Carrega simulações salvas ou edita ao vivo.

**Linha central de diferenças:**

```text
                A              ↔             B              Diferença
Taxa            1,69% a.m.                   1,49% a.m.     ▼ 0,20 p.p.
Prazo           60 meses                     48 meses       ▼ 12 meses
Entrada         R$ 12.000,00                 R$ 18.000,00   ▲ R$ 6.000,00
Parcela         R$ 1.456,32                  R$ 1.523,18    ▲ R$ 66,86
Juros totais    R$ 27.380,12                 R$ 19.111,64   ▼ R$ 8.268,48
Total pago      R$ 99.380,12                 R$ 91.111,64   ▼ R$ 8.268,48
```

Gráficos sobrepostos: evolução do saldo devedor (2 linhas), juros pagos acumulados (2 linhas).

Salvar comparativo → grava em `comparisons`.

### 8.5 Amortização extraordinária

1. Carrega simulação existente (combobox)
2. Mostra cronograma original em cinza
3. Painel "Adicionar pagamento extra": data, valor, modo (parcela ou prazo)
4. Múltiplos pagamentos em sequência
5. Botões rápidos: "Quitação total agora" | "Quitação parcial 50%"
6. Recálculo em tempo real:
   - Cronograma original (cinza) vs novo (colorido) sobrepostos
   - Cards: Economia de juros, Redução de prazo (se modo prazo), Nova parcela (se modo parcela)
7. "Salvar cenário com amortização" gera nova simulação derivada

### 8.6 Indicadores

- Cards atuais: SELIC, CDI, IPCA, Tx BACEN veículos, IOF (fixo + diário)
- Cada card: valor, data, fonte, badge "atual"/"desatualizado"
- Botão "↻ Atualizar agora" (gerente/admin)
- Gráficos série histórica 12 meses (linha)
- Tabela de conversões úteis (SELIC anual → mensal, CDI diário → anual)
- Painel "Sobreposição SELIC × Tx BACEN Veículos × Taxa praticada"

### 8.7 Configurações

Áreas (admin vê todas; gerente vê leitura em algumas):

- Geral: nome da loja, logo (upload), endereço, CNPJ — usados no PDF
- Regras de negócio: entrada mínima, prazos min/max, faixa de taxa, dias máx carência, curva taxa-por-prazo
- Tarifas: cadastro/avaliação/registro (default + habilitadas)
- IOF: percentuais fixo e diário (histórico preservado) + default da flag `incluir_iof`
- **Custos adicionais padrão** (`extras_padrao`): editar lista pré-cadastrada de proteção veicular, IPVA, emplacamento e custom (valor default, duração default do rateio, habilitar/desabilitar). Tudo que estiver habilitado aparece automaticamente na tela de Simulação como sugestão.
- Backup: trigger manual, lista de backups, restaurar de arquivo
- Aparência: tema claro/escuro, cor primária
- PDF: textos cabeçalho/rodapé, observações padrão

### 8.8 APIs

- Status por provider (verde/amarelo/vermelho) + última coleta bem-sucedida
- "Atualizar agora" por indicador
- "Testar conexão" por provider
- Toggle habilitar/desabilitar (admin)
- Histórico últimas 50 chamadas (hit/miss, latência, erro)
- Ordem da chain reordenável via drag-and-drop

### 8.9 Logs

- Tabela paginada de `audit_log` com filtros por data, usuário, ação, entidade
- Detalhe expandível por linha (mostra `diff_json` formatado)
- Exportar CSV para período selecionado
- Vendedor vê só logs próprios

### 8.10 Documentação Técnica

- Visualizador embutido dos `.md` do projeto (`guia_usuario.md`, `matematica_price.md`, `troubleshooting.md`)
- Sidebar com sumário
- Renderiza Markdown com KaTeX para fórmulas
- Search box no topo

### Navegação e estado

- `router.py` centraliza guards: cada rota declara `required_role`; tentativa por perfil inferior redireciona para Dashboard com toast
- Estado da simulação atual em `app.storage.user` (NiceGUI) — sobrevive navegação, perdido ao deslogar
- Atalhos: Ctrl+S salvar, Ctrl+P imprimir/PDF, Ctrl+Tab próxima aba (configuráveis)
- Toasts padronizados (sucesso/atenção/erro/info, 4s auto-dismiss)

---

## 9. PDF, backup, migrations, logs

### 9.1 PDF de proposta — `app/reports/` + `services/proposal_service.py`

Pipeline: dados → template Jinja2 (HTML/CSS) → WeasyPrint → PDF.

**Blocos do `proposta.html`:**

1. Cabeçalho — logo, razão social, CNPJ, endereço, telefone, código, data, validade
2. Cliente — nome, CPF/CNPJ, contato, endereço
3. Veículo — marca/modelo/ano/cor/placa (opc), valor FIPE, valor de venda, fonte FIPE + mês ref
4. Condições — valor financiado, entrada (R$ e %), prazo, taxa (a.m. e a.a.), CET (a.m. e a.a.), IOF total (ou "não incluído"), tarifas detalhadas, data 1º venc
5. **Custos adicionais mensais** (se houver) — tabela com tipo, modalidade, valor total, valor por parcela, parcelas afetadas (ex.: "IPVA — rateio 12x — R$ 1.800,00 → R$ 150,00/mês — parcelas 1 a 12")
6. Resumo financeiro — parcela do financiamento, parcela total 1º ano, parcela total após rateio, total pago financiamento, total pago cliente, total de juros, % juros (cards)
7. Cronograma completo — nº, vencimento, juros, amortização, parcela financiamento, **extras**, **parcela total**, saldo
8. Gráfico de composição da parcela — render server-side (Plotly → PNG embutido; inclui faixas de extras)
9. Observações — configuráveis, suportam variáveis `{cliente}`, `{vendedor}`, `{prazo}`
10. Rodapé — vendedor responsável, assinaturas, validade da proposta. **Nota fixa**: "Custos adicionais (proteção veicular, IPVA, emplacamento) não compõem o CET por serem despesas externas ao crédito."

CSS: paleta da loja (cor primária configurável), Inter + serif, A4 com page-break inteligente.

**Snapshot:** `proposals.snapshot_json` grava tudo usado no PDF (incluindo regras e indicadores vigentes). PDF reproduzível anos depois.

**Saída PDF:** `data/propostas/PROP-2026-00123_NomeCliente.pdf` + path em `proposals.pdf_path`. Dispara `audit_log("proposta_gerada")` e abre no visualizador padrão do SO.

**Carnê de pagamento** — `app/reports/carne.html` + `carne.css` [IMPLEMENTADO]

Pipeline idêntico ao PDF de proposta (Jinja2 → WeasyPrint). Gera um carnê estilo boleto por parcela com: código do contrato, vencimento, valor total da parcela, dados do cliente e veículo.

Gerado via `proposal_service.generate_carne(proposal_id, output_dir)`. Caminho salvo em `proposals.carne_path`.

### 9.2 Backup automático — `app/data/backup.py`

- Job APScheduler diário 23:00 (configurável)
- `sqlite3.Connection.backup()` (transação-safe, não copia arquivo em uso)
- Saída: `data/backups/finacialsim_2026-05-23_2300.sqlite.gz`
- Retenção default 30 dias
- Manual: Configurações → Backup → "Backup agora" / "Restaurar de arquivo..."
- Restauração: valida com `PRAGMA integrity_check`, confirma com usuário, aplica, reaplica migrations
- Backup adicional ao fechar (`_close`)

### 9.3 Migrations — `app/data/migrations/` (Alembic)

- Versionamento incremental (`001_initial.py`, ...)
- `alembic upgrade head` automático no startup (idempotente)
- Cada aplicação loga em `audit_log("migration_applied")`
- Nunca editar migration em produção — sempre nova migration corretiva
- `001_initial.py` seed: usuário `admin` com PIN `123456` (forçado a trocar no 1º login), `business_rules` defaults, IOF regulamentado

### 9.4 Logs técnicos — `app/utils/logger.py`

- loguru centralizado
- Arquivo: `logs/finacialsim_{time:YYYY-MM-DD}.log`
- Rotação diária, retenção 30 dias, gzip após 7 dias
- Níveis: DEBUG (dev), INFO (operações), WARNING (provider miss), ERROR, CRITICAL (falhas no core)
- Formato: `{time} | {level} | {module}:{function}:{line} | {message} | {extra}`
- Sentry opcional (env `SENTRY_DSN`) para ERROR/CRITICAL
- Distinção clara de `audit_log` (negócio) vs `logger` (técnico)

---

## 10. Empacotamento, instalação e atualização

### 10.1 PyInstaller — `scripts/build_exe.py`

**Windows** (`finacialsim.exe`)

- `--onedir` (startup mais rápido que `--onefile`)
- Ícone `assets/icon.ico`
- Inclui GTK+ runtime do WeasyPrint
- Saída: `dist/FinacialSim/` → NSIS gera `FinacialSim-Setup-1.0.0.exe`
- Cria `%APPDATA%/FinacialSim/data/` no primeiro run
- Atalho desktop, registro em Add/Remove Programs

**Linux** (`finacialsim.AppImage`)

- PyInstaller `--onedir` → AppImage
- Opcional: `.deb` via fpm em release futura
- Dados em `~/.local/share/FinacialSim/data/`

**macOS** (`FinacialSim.app`)

- PyInstaller `--onedir` → `.app bundle` + `dmg` via `create-dmg`
- Requer macOS 12+ (Monterey); Apple Silicon (arm64) e Intel (x86_64) suportados via fat binary
- Inclui GTK+ runtime do WeasyPrint (via Homebrew bundled)
- Dados em `~/Library/Application Support/FinacialSim/data/`
- Assinatura ad-hoc (`codesign --deep --force --sign -`) para distribuição manual; notarização Apple opcional em release futura

**Versionamento**

- `pyproject.toml` define versão
- Embutida no binário e no rodapé do app
- `app_settings.installed_version` detecta primeira execução pós-update → dispara `alembic upgrade`

### 10.2 Scripts de instalação

**Windows — `install_windows.ps1`**

- Verifica Windows 10+ x64
- Baixa instalador da última release (modo auto)
- Executa setup silenciosamente (`/S` NSIS)
- Cria atalho e entrada no menu iniciar

**Linux — `install_linux.sh`**

- Detecta distro via `/etc/os-release`
- Instala dependências de sistema do WeasyPrint se necessário
- Baixa AppImage, marca como executável, move para `/opt/finacialsim/`
- Cria `.desktop` em `~/.local/share/applications/`

**macOS — `install_macos.sh`**

- Verifica macOS 12+ e arquitetura (arm64/x86_64)
- Verifica/instala Homebrew (com prompt de confirmação do usuário)
- Instala dependências do WeasyPrint via Homebrew (`pango`, `gdk-pixbuf`, `libffi`)
- Baixa DMG da última release, monta, copia `FinacialSim.app` para `/Applications/`
- Cria atalho no Dock (opcional)

**Documentação** em `docs/INSTALACAO.md` — pré-requisitos, passo-a-passo com screenshots, troubleshooting comum.

### 10.3 Atualizações

- Checagem opcional no startup contra `https://github.com/{repo}/releases/latest`
- Versão nova → badge no topbar → modal com changelog → "Baixar e instalar"
- Desativável (lojas com internet instável)
- Atualização preserva o banco; migrations rodam após update
- Releases automatizadas via GitHub Actions (tag → build paralelo Win/Linux/macOS → publica artifacts)
- Channels `beta` e `stable` (admin escolhe em Configurações)

---

## 11. Segurança e proteção

- **PIN com bcrypt** (cost factor 12)
- **5 tentativas** erradas → lockout 5 min por usuário
- **Validação Pydantic** em todos os inputs (UI, providers, configs)
- **Validação extra** em payloads de providers (faixa de valores, tipos)
- **Audit log** com `diff_json` em toda alteração de regra, indicador, cliente, simulação
- **Backup automático** + restauração validada (`PRAGMA integrity_check`)
- **Migrations versionadas** (Alembic) — nunca editar uma migration em produção
- **Snapshot JSON** preserva o passado mesmo com mudança de regras
- **Perfis ocultam UI** — não apenas desabilitam (defense-in-depth)
- **Logs técnicos** (loguru) separados de logs de negócio (audit_log)

---

## 12. Regras de negócio resumidas

Todas configuráveis em `business_rules` por admin (versionadas em `audit_log`):

| Chave | Default | Descrição |
| --- | --- | --- |
| `entrada_minima_pct` | **0.10** | 10% mínimo de entrada |
| `prazo_minimo_meses` | 12 | |
| `prazo_maximo_meses` | 72 | |
| `taxa_minima_mes` | 0.005 | 0,5% a.m. |
| `taxa_maxima_mes` | 0.05 | 5% a.m. |
| `dias_max_carencia` | 90 | dias entre liberação e 1º vencimento |
| `valor_minimo_financiado` | 5000 | R$ |
| `incluir_iof_default` | true | default da flag por simulação (§6.3) |
| `iof_fixo_pct` | 0.0038 | 0,38% |
| `iof_diario_pct` | 0.000082 | 0,0082%/dia |
| `iof_diario_max_dias` | 365 | teto por parcela |
| `taxa_por_prazo_curva` | (ver §6.6) | curva crescente |
| `extras_padrao` | (ver abaixo) | lista de extras pré-cadastrados disponíveis ao vendedor |
| `rateio_ipva_meses_default` | 12 | meses do rateio de IPVA |
| `rateio_emplacamento_meses_default` | 12 | meses do rateio de emplacamento |
| `backup_diario_horario` | "23:00" | |
| `backup_retencao_dias` | 30 | |
| `update_indicadores_horario` | "09:00" | |
| `fipe_cache_listas_ttl_dias` | 30 | |
| `fipe_cache_preco_ttl_horas` | 24 | |

**`extras_padrao`** — lista de extras pré-cadastrados (admin edita em Configurações; vendedor seleciona com 1 clique na tela de Simulação):

```json
[
  { "tipo": "protecao_veicular", "nome": "Plano de proteção veicular",
    "modalidade": "mensal_continuo", "valor_total_default": 0,
    "habilitado": true },
  { "tipo": "ipva", "nome": "IPVA anual (rateio)",
    "modalidade": "rateio_meses", "duracao_meses_default": 12,
    "valor_total_default": 0, "habilitado": true },
  { "tipo": "emplacamento", "nome": "Emplacamento + licenciamento (rateio)",
    "modalidade": "rateio_meses", "duracao_meses_default": 12,
    "valor_total_default": 0, "habilitado": true }
]
```

---

## 13. Integrações futuras (arquitetura preparada, desativadas no MVP)

A camada `integrations/` e os `services/` foram desenhados para acomodar:

- **CRM** — `integrations/crm/` com providers Bling/RDStation/etc. — `client_service` exporta clientes em formato compatível
- **WhatsApp** — `integrations/whatsapp/` com Twilio/Z-API — `proposal_service.send_via_whatsapp(proposal_id, phone)` mockado
- **Geração de carnê** — **IMPLEMENTADO** em `proposal_service.generate_carne()` com template `reports/carne.html`/`carne.css`; `carne_service.py` separado não foi necessário
- **APIs bancárias** — `integrations/bancos/` (Santander, Itaú, BV, Bradesco) — submissão real de proposta

Cada uma fica desligada via feature flag em `app_settings`. Aba "Configurações → Integrações Futuras" exibe lista cinza com botão "Configurar (em breve)".

---

## 14. Documentação a entregar

Em `docs/`:

- `ARQUITETURA.md` — versão "viva" deste spec, ligada ao código
- `DOCUMENTACAO.md` — documentação técnica completa (referência de módulos, contratos, exemplos)
- `guia_usuario.md` — voltado para vendedores: como cadastrar cliente, simular, gerar proposta, comparar
- `matematica_price.md` — explicação detalhada da Tabela Price, IOF, CET, com derivações
- `troubleshooting.md` — problemas comuns e soluções (firewall, antivírus, GTK runtime, banco corrompido)
- `INSTALACAO.md` — instalação Windows, Linux e macOS passo-a-passo

---

## 15. Testes e qualidade

- `tests/unit/core/` — bateria completa do core financeiro (cobertura ≥ 95%)
  - Cronogramas comparados centavo a centavo com Santander/Itaú/Bradesco
  - Property tests (hypothesis) garantindo invariantes
  - Casos-borda enumerados
- `tests/unit/services/` — serviços com repositórios e providers mockados
- `tests/integration/` — fluxo completo (criar cliente → simular → gerar proposta → recuperar)
- `pytest --cov` no CI; falha se cobertura cair
- Lint: `ruff` + `mypy --strict` em `core/`

---

## 16. Fora do escopo do MVP

- CRM, WhatsApp, APIs bancárias (apenas arquitetura preparada)
- ~~Geração de carnê~~ → **já implementada** em `proposal_service.generate_carne()` + `reports/carne.html`
- Sincronização entre lojas/PCs (estratégia "híbrido com sync futuro" não foi escolhida)
- Multi-tenancy
- App mobile
- Integração contábil
- Análise de crédito automatizada (consulta SCR, Serasa)
- Sistema SAC (alternativo à Tabela Price)

Esses itens podem ser adicionados em releases futuras sem reescrita do core, graças à camadização.

---

## 17. Critérios de aceitação do MVP

- [ ] Vendedor consegue, em < 2 min, simular um financiamento partindo do veículo via FIPE e vinculando a cliente cadastrado
- [ ] Cronograma gerado bate centavo a centavo com simulador de pelo menos 1 banco brasileiro de referência para 3 casos de teste
- [ ] CET calculado bate com calculadora oficial do BCB em 5 casos de teste — **CET NÃO muda ao adicionar/remover extras** (regressão garantida)
- [ ] IOF opcional: simulação com `incluir_iof=false` apresenta `iof_total=0` e `PV = valor_veículo − entrada + tarifas` (sem iteração)
- [ ] Custos adicionais: cenário com IPVA R$ 1.800,00 rateado em 12x apresenta R$ 150,00 nas primeiras 12 parcelas e R$ 0,00 nas demais; plano de proteção R$ 80,00/mês incide em todas as parcelas
- [ ] PDF de proposta abre corretamente no Adobe Reader, Foxit, e leitor padrão do Windows/Linux/macOS, com bloco de "Custos adicionais mensais" detalhado
- [ ] Backup diário roda e arquivo `.sqlite.gz` é válido (restauração bem-sucedida)
- [ ] Atualização de indicadores às 09:00 atualiza os 5 indicadores ou marca como `stale`
- [ ] App roda em Windows 10, Ubuntu 22.04 e macOS 12 (Monterey) a partir do instalador, sem Python instalado no host
- [ ] Vendedor com perfil "vendedor" não consegue ver as abas APIs/Configurações/Logs

---

**Próximo passo:** invocar a skill `writing-plans` para criar o plano de implementação em fases (testáveis e revisáveis em separado).
