# Contexto

Voce esta trabalhando no desenvolvimento do FinacialSim, que é um aplicativo desktop multi-perfil para uma loja brasileira, com cálculo financeiro fiel ao praticado por bancos e financeiras brasileiras para CCB de veículos. Os objetivos primários são:

1. Permitir a vendedores leigos simular financiamentos com precisão bancária, em poucos cliques.
2. Vincular simulações a clientes cadastrados e gerar propostas em PDF profissionais.
3. Manter taxas e indicadores econômicos sempre atualizados, com fallback robusto a falhas de rede.
4. Comparar cenários e simular amortizações extraordinárias (parcial, total, reduzir prazo, reduzir parcela).
5. Manter histórico auditável e reproduzível (uma proposta de 2026 deve poder ser regerada em 2027, idêntica).
6. Servir de base modular para futuras integrações (CRM, WhatsApp, sistema pagamento PIX, geração de carnês, APIs bancárias).

Capacidades atuais resumidas:

[] Cadastro de clientes (PF/PJ) com validação de CPF/CNPJ.
[] Consulta FIPE com filtros encadeados (tipo → marca → modelo → ano).
[] Atualização automática de SELIC, CDI, IPCA, taxa BACEN de veículos, IOF.
[] Simulação Tabela Price com dias corridos e primeiro vencimento variável.
[] **IOF opcional por simulação** (default ligado): quando ativo, 0,38% fixo + 0,0082%/dia (teto 365 dias) iterado para convergência ao ser incorporado ao principal.
[] **Custos adicionais mensais acrescidos à parcela**: plano de proteção veicular (mensal contínuo), IPVA anual com rateio em N meses (default 12), emplacamento + licenciamento com rateio em N meses (default 12), e itens personalizados (rastreador, garantia, etc.).
[] CET via TIR exata (Brent) — calculado apenas sobre o fluxo do financiamento (convenção BCB; extras não compõem o CET).
[] Cronograma de amortização completo (com colunas de extras e parcela total), com gráficos interativos.
[] Comparação lado-a-lado de dois cenários.
[] Amortização extraordinária com escolha de modo (parcela ou prazo).
[] Geração de PDF de proposta com snapshot reproduzível.
[] Geracao de Carnê para impressao
[] integracao com sistema pix
[] Backup automático e restauração do banco.
[] Logs de execução (técnico) e audit log (negócio).
[] Três perfis: vendedor / gerente / administrador.

## Necessidades
A natureza do applicativo implica na necessidade de administrar pagamentos recorrentes. A administracao dos pagamentos envolve previsão para diversos cenarios como:
- Cobranças geradas dinamicamente
- gerar lembretes automáticos
- calculo de juros diários
- inadimplência (alerta de status, definicao de multa)
- renegociação
- sincronização

Recomendar arquitetura ideal (exemplo:)

```text
Frontend
    ↓
API Gateway
    ↓
Auth Service
    ↓
Financial Service
    ↓
Pix Service
    ↓
Notification Service
    ↓
Queue Workers
```

Suggest an Event-driven architecture
Example:
```text
PIX_RECEIVED
INSTALLMENT_OVERDUE
PAYMENT_CONFIRMED
CONTRACT_DEFAULTED
```



## Tarefa

Sua tarefa é me auxiliar na implantação do sistema de um sistema de pagamentos pix usando a API do Efí.

## Requisitos primarios

A implementação do pix deve seguir as seguintes diretrizes:

- Geração de QR codes e links de pagamento (rastreáveis).

- Confirmação de pagamento.

- Deve ser possível gerar os códigos de pix no ato da geração do carnê, na mesma janela.

- Cobrança de multa juros em caso de atraso.

- Verificar capacidade de gerar os códigos de pix e enviá-los por whatsapp, email ou SMS.


