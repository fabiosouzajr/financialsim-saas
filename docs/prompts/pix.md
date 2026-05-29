# Contexto

Você é um expert em desenvolvimentos de sistemas de pagamentos eletronicos no Brasil com ampla experiencia em integração de sistemas com a modalidade pix.
Estou desenvolvendo um sistema para uma loja de carros usados. Esse sistema implementa a geração de carnês para pagamentos. Prazos de pagamentos variam de 12 a 48 meses, podendo ser semanais ou mensais. Um dos requerimentos é  possibilidade de pagamentos via pix no carnê.
O sistema foi desenvolvido em python com interface gtk4 e utiliza banco de dados sqlite3. O sistema é executado em modo local na máquina do usuário, não há um servidor central de processamento de pagamentos.
O sistema já é capaz de gerar os carnês.

## Tarefa

Sua tarefa é me auxiliar no planejamento e desenvolvimento da implementação do sistema de pagamentos pix no carnê. Faça uma ampla pequisa sobre implantaçao de pix em sistemas de pequena escala, as ferramentas e bibliotecas disponiveis para implementação e me apresente as opções mais interessantes. Leve em consideração as limitações e especificidades de um sistema de pequena escala, que opera em modo local e sem um servidor central de processamento de pagamentos.

## Requisitos primarios

A implementação do pix deve seguir as seguintes diretrizes:

- Geração de QR codes e links de pagamento (rastreáveis).

- Confirmação de pagamento.

- Deve ser possível gerar os códigos de pix no ato da geração do carnê, na mesma janela.

- O usuário deve ser capaz de gerar os códigos de pix e imprimir o carnê.

## Requisitos secundarios

- Cobrança de juros em caso de atraso.

- Verificar capacidade de gerar os códigos de pix e enviá-los por whatsapp, email ou SMS.

## Atentar para

- Expiracao de codigos QR e links pix em longos periodos (meses e anos)
