# CONTEXTO DO PRODUTO

Você é um Arquiteto de Software Sênior especializado em sistemas financeiros brasileiros, PIX, cobrança recorrente, crédito direto ao consumidor (CDC/CCB), event-driven architecture, integração com APIs bancárias e sistemas de cobrança.

Sua missão é elaborar um PLANO COMPLETO DE IMPLANTAÇÃO da camada de pagamentos PIX do sistema FinancialSim utilizando a API da Efí.

FinancialSim é um aplicativo desktop multi-perfil utilizado por uma loja de veículos para:

* Simulação financeira bancária
* Emissão de propostas
* Geração de carnês
* Controle de contratos
* Cobrança de parcelas
* Integração PIX
* Futuras integrações com CRM, WhatsApp e APIs bancárias

O sistema possui:

* Cadastro de clientes PF/PJ
* Simulação financeira estilo CCB
* Tabela Price
* IOF
* CET
* Geração de PDF
* Geração de carnês
* Histórico auditável
* Logs técnicos e de negócio
* Perfis vendedor, gerente e administrador

O sistema deve ser capaz de administrar contratos com duração entre 12 e 48 meses.

## OBJETIVO

Projetar toda a arquitetura necessária para permitir:

1. Geração de cobranças PIX
2. Geração de QR Codes PIX
3. Geração de Links de Pagamento PIX
4. Recebimento de confirmações via webhook
5. Controle de inadimplência
6. Cálculo automático de juros e multa
7. Renegociação
8. Emissão de segunda via
9. Envio automatizado de cobranças
10. Rastreabilidade completa de pagamentos

---

## REQUISITOS FUNCIONAIS

### Geração de Carnê

Ao gerar um carnê:

* Todas as parcelas devem ser criadas no banco.
* Deve ser possível gerar os PIX imediatamente.
* Deve ser possível gerar:

  * QR Code
  * Copia e Cola
  * Link de Pagamento

Avalie:

* gerar todos os PIX no ato da criação do contrato
* gerar PIX sob demanda
* modelo híbrido

Comparar vantagens e desvantagens.

---

### Cobrança

Cada parcela deve possuir estados:

```Text
PENDING

SCHEDULED

PIX_GENERATED

SENT

PAID

PARTIALLY_PAID

OVERDUE

RENEGOTIATED

CANCELLED

DEFAULTED

Descrever a máquina de estados completa.
```

---

### Inadimplência

Implementar:

* multa fixa configurável
* juros diário configurável
* carência configurável
* atualização automática dos valores

Avaliar:

* cálculo em tempo real
* cálculo batch diário

Comparar.

---

### Renegociação

Permitir:

* renegociar parcela única
* renegociar múltiplas parcelas
* renegociar contrato inteiro

Detalhar:

* impactos contábeis
* rastreabilidade
* preservação do histórico

---

### Comunicação

Analisar estratégias para envio por:

* WhatsApp
* Email
* SMS

Para cada canal informar:

* arquitetura recomendada
* custo operacional
* taxa de entrega
* limitações

---

### Integração Efí

Descrever detalhadamente:

* autenticação
* emissão de cobrança PIX
* QR Codes
* webhooks
* consulta de cobranças
* consulta de pagamentos
* cancelamentos
* tratamento de falhas
* idempotência
* retry policies

Explicar quais recursos da API Efí devem ser utilizados.

---

## EVENT-DRIVEN ARCHITECTURE

Projetar uma arquitetura baseada em eventos.

Apresentar:

### Eventos de Contrato

CONTRACT_CREATED

CONTRACT_ACTIVATED

CONTRACT_RENEGOTIATED

CONTRACT_CANCELLED

CONTRACT_DEFAULTED

---

### Eventos de Parcela

INSTALLMENT_CREATED

INSTALLMENT_UPDATED

INSTALLMENT_DUE_SOON

INSTALLMENT_OVERDUE

INSTALLMENT_RENEGOTIATED

INSTALLMENT_CANCELLED

---

### Eventos PIX

PIX_GENERATED

PIX_SENT

PIX_VIEWED

PIX_EXPIRED

PIX_RECEIVED

PIX_CONFIRMED

PIX_RECONCILED

---

### Eventos Financeiros

PAYMENT_RECEIVED

PAYMENT_CONFIRMED

PAYMENT_REVERSED

INTEREST_APPLIED

PENALTY_APPLIED

---

### Eventos de Comunicação

WHATSAPP_SENT

EMAIL_SENT

SMS_SENT

DELIVERY_FAILED

---

## ARQUITETURA

Projetar arquitetura completa.

Apresentar diagrama textual semelhante a:

```Text
Frontend Desktop
↓
API Gateway
↓
Authentication Service
↓
Contract Service
↓
Installment Service
↓
PIX Service
↓
Notification Service
↓
Event Bus
↓
Workers
```


Descrever responsabilidades de cada serviço.

---

## MODELAGEM DE DADOS

Projetar tabelas:

```Text
clients

contracts

installments

pix_charges

payments

payment_events

renegotiations

notifications

audit_logs

webhook_events
```

Incluir:

* campos
* índices
* relacionamentos
* chaves de auditoria

---

## RESILIÊNCIA

Detalhar:

* idempotência
* deduplicação de webhooks
* retry
* dead-letter queue
* circuit breaker
* cache
* auditoria

---

## SEGURANÇA

Analisar:

* LGPD
* criptografia
* armazenamento de tokens Efí
* assinatura de webhooks
* controle de acesso por perfil

---

## ESCALABILIDADE

Comparar:

## Opção A

Aplicação Desktop + Backend Monolítico

## Opção B

Modular Monolith

## Opção C

Microservices Event-Driven

Para cada opção apresentar:

* complexidade
* custo
* manutenção
* escalabilidade

E indicar qual é a melhor escolha para um sistema de loja de veículos de pequeno e médio porte.

---

## ROADMAP

Criar roadmap dividido em fases:

* FASE 1 - PIX básico

* FASE 2 - Cobrança automática

* FASE 3 - Inadimplência

* FASE 4 - Renegociação

* FASE 5 - Integração WhatsApp

* FASE 6 - Integração CRM

* FASE 7 - Integração bancária

Para cada fase informar:

* funcionalidades
* riscos
* dependências
* esforço estimado

---

## RESULTADO ESPERADO

Gerar um documento técnico completo contendo:

1. Arquitetura recomendada
2. Fluxos de negócio
3. Fluxos de eventos
4. Modelagem de banco
5. Estratégia de integração Efí
6. Estratégia de cobrança recorrente
7. Estratégia de inadimplência
8. Estratégia de renegociação
9. Roadmap de implantação
10. Riscos técnicos e operacionais

O nível de detalhamento deve ser equivalente ao de um documento de arquitetura produzido por um arquiteto de software sênior para aprovação de projeto.
