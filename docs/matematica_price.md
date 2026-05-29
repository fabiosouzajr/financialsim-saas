# Matematica financeira do FinacialSim

Este documento explica em detalhe as formulas usadas.

## Tabela Price com dias corridos

Seja:

- `PV` = valor financiado
- `i_m` = taxa mensal nominal (fracao decimal)
- `i_d` = (1 + i_m)^(1/30) - 1
- `d1` = dias entre liberacao e 1o vencimento
- `n` = numero de parcelas

A parcela fixa e calculada por:

```text
PMT = PV * (1 + i_d)^d1 * (i_m * (1 + i_m)^(n-1)) / ((1 + i_m)^n - 1)
```

Quando `d1 = 30`, esta formula reduz a Tabela Price classica:

```text
PMT = PV * i_m * (1 + i_m)^n / ((1 + i_m)^n - 1)
```

## Cronograma

- Parcela 1: juros = `PV * ((1 + i_d)^d1 - 1)`, amortizacao = `PMT - juros`
- Parcelas 2..n-1: juros = `saldo * i_m`, amortizacao = `PMT - juros`
- Parcela n: amortizacao = saldo, ajuste de centavos vai em `ajuste_arredondamento`

## IOF

Decreto 6.306/2007:

- IOF fixo = 0,38% sobre o valor financiado
- IOF diario = sum(amortizacao_k *0,0082%* min(dias_ate_venc_k, 365))

Quando incorporado ao principal, ha iteracao:

```text
PV(0) = veiculo - entrada + tarifas
PV(n+1) = PV(0) + IOF(PV(n), schedule(PV(n)))
parar quando |PV(n+1) - PV(n)| < R$ 0,01
```

Convergencia em 2-3 iteracoes.

## CET

CET e a TIR (Taxa Interna de Retorno) mensal do fluxo de caixa:

```text
valor_liberado = sum_k PMT / (1 + i_cet)^(meses_t_k)
```

Onde `meses_t_k = (d1 + 30*(k-1)) / 30`. Resolvido pelo metodo de Brent (bisecao pura Python).

CET anual: `(1 + i_cet)^12 - 1`.

## Custos adicionais (extras)

Nao afetam PMT, IOF nem CET. Entram somente em `parcela_total = PMT + extras_total[k]`.

Modalidades:

- `mensal_continuo`: valor incide em todas as N parcelas
- `rateio_meses`: valor/duracao_meses incide nas D primeiras parcelas
- `unico_inicial`: valor incide apenas na 1a parcela
