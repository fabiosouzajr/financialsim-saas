# Troubleshooting

## "App nao abre" (Windows)

- Verifique se o antivirus bloqueou o executavel. Adicione excecao para `C:\Program Files\FinacialSim\FinacialSim.exe`.
- Reinstale o app.

## "WeasyPrint error" / "libpango not found" (Linux)

Instale dependencias:

```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

## "App damaged" (macOS)

Va em System Settings > Privacy & Security > "Open Anyway". Necessario na primeira execucao por nao ser notarizado.

## Indicadores desatualizados

- Verifique conexao com internet.
- Va em "APIs" e clique "Atualizar indicadores agora".
- Se persistir, admin pode informar valores manuais em "Indicadores".

## FIPE nao retorna marcas

- Cache de listas dura 30 dias.
- Tente forcar atualizacao em "APIs".
- Use entrada manual caso ambas APIs falhem.

## Banco corrompido

- Backups automaticos diarios estao em `<data>/backups/`.
- Em Configuracoes > Backup, clique "Restaurar de arquivo..." e selecione o backup mais recente.

## CET nao bate com calculadora do banco

- Verifique se "Incluir IOF" esta ligado.
- Confira se valor do veiculo e entrada batem com o contrato.
- Lembre: custos adicionais (protecao, IPVA, emplacamento) NAO entram no CET por convencao BCB.
