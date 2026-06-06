# TODO List

## Contexto

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


## PIX
Diante da necessidade de pagamentos recorrentes, a integração com o sistema de pagamentos pix é essencial para o sucesso do aplicativo. Os pagamentos pix devem ser automatizados 


## implement a "veiculos" page

## include "fipe" vehicle data in "simulação"

- [] fetch vehicle data from "fipe"
- [] include vehicle data in "simulação"

## include client data in "simulação"

- [] fetch client data from "cadastro de clientes"
- [] include client data in "simulação"

## redesign the ui for "cadastro de clientes"

- [] make the "nome" field bigger
- [] display the full label for "pf" and "pj" in the search input
- [] apply the correct formatting for "cpf" and "cnpj"

## in "indicadores"

- [] in "IPCA" KPI
  - [] add display of "ipca" of the last 12 months
- [] in "TX_BACEN_VEIC" KPI
  - [] Change only the label to "Taxa Média Bacen Veículos"
  - [] calculate montlhy TX_BACEN_VEIC
- [] in "CDI" KPI
  - [] add display CDI of the past 30 days,
  - [] add display CDI of the last 12 months,

---

## minor fixes in the user login

- [] make the user field the same size as the pin field;
- [] make it possible to interface using the keyboard (enter key to submit, etc);

---

## changes in the "cadastro section"

- [] reduce paddding to maximize screen real estate while keeping aesthetic clean and pleasant to look at;
- [] in clientes cadastrados
  - [] center align column labels;
  - [] make the client list narrower by hiding unnecessary columns ("tipo_de_cliente" and "telefone");

---

## changes in simulacao

- [] reduce the size of the KPI components;
- [] reduce the sizes of the graphs;

## changes in "configuracoes - regras de negocio"

- [] implement actual user friendly labels for the ui;
- [] display percent values as "x%" (for example: "20%" instead of "0.20");
- [] group similar components in a user friendly way;

## changes in "Regras de Negócio"

- [] remove the " " from the "Dados de Loja" section text fields as this might confuse the user.
- [] include fields for "Seguro Proteção Veicular", "IPVA" and "Emplacamento" in "Extras / Rateio".

## changes in IPVA and emplacamento

We need to change the way values are calculated in the "Extras / Rateio" section:

"IPVA" is an anual vehicle tax that is calculated based on a percentage of the vehicle's value (from the fipe vehicle data), and the vehicle type ("carro", "moto", "caminhao").
Currently ipva has the follwing percentages based on vehicle types:
"carros":  3,5%;
"motas":  3%;
"caminhoes": 1%;

"emplacamento" is fixed value anual fee, also based on vehicle type:
"carros" e "caminhoes": R$ 220,46;
"motos": R$ 188,96;

Your task is to implement changes that create user updateable fields for these values in "regras de negocio - Extra / Rateio". The default values for these fields should be the current values.

These values (from "regras de negocio - Extra / Rateio") should appear when the user performs a simulation.

---

## changes in "simulação - comparação"
