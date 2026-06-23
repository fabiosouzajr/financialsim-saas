# Proposta snapshot preserva o logo no momento da criação

O `LojaSnap` dentro de `PropostaSnapshot` armazena o `logo_key` do tenant no instante em que a proposta é gerada. Re-renderizações via admin usam esse mesmo `logo_key` — nunca o logo atual do tenant. A razão é que o snapshot é um registro histórico imutável do que foi apresentado ao cliente; alterar o logo retroativamente criaria ambiguidade jurídica sobre os termos que o cliente viu. Se o tenant quiser uma proposta com o novo logo, gera uma nova simulação.
