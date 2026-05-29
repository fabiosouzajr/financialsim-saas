# Instalacao do FinacialSim

## Windows 10+ (x64)

1. Baixe `FinacialSim-Setup-1.0.0.exe` na pagina de releases.
2. Execute o instalador. Aceite o UAC.
3. Escolha o diretorio de instalacao (default `C:\Program Files\FinacialSim`).
4. Aguarde a copia dos arquivos.
5. Ao terminar, abra pelo atalho no Desktop ou pelo menu Iniciar.
6. Primeiro login: usuario "Admin", PIN "123456" (sera solicitada a troca).

## Linux (Ubuntu/Debian/Fedora)

1. Baixe `FinacialSim-x86_64.AppImage`.
2. Torne-o executavel: `chmod +x FinacialSim-x86_64.AppImage`.
3. Execute: `./FinacialSim-x86_64.AppImage`.

Ou via script automatico:

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/finacialsim/main/scripts/install_linux.sh | bash
```

## macOS 12+ (Monterey, Apple Silicon ou Intel)

1. Baixe `FinacialSim-1.0.0.dmg`.
2. Monte o DMG, arraste FinacialSim para Applications.
3. Na primeira execucao, va em System Settings > Privacy & Security se aparecer "App nao verificado" e clique em "Abrir mesmo assim".

Ou via script:

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/finacialsim/main/scripts/install_macos.sh | bash
```

## Pos-instalacao

- Dados ficam em:
  - Windows: `%APPDATA%\FinacialSim`
  - Linux: `~/.local/share/FinacialSim`
  - macOS: `~/Library/Application Support/FinacialSim`
- Backups automaticos rodam diariamente as 23:00.
- Atualizacoes de indicadores rodam diariamente as 09:00 (precisa de internet).

Consulte `troubleshooting.md` para problemas comuns.
