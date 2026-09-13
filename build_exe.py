"""
Gera o executável Windows (um único .exe) da interface gráfica.

    python build_exe.py

Requer o PyInstaller (pip install pyinstaller) e as dependências do
requirements.txt instaladas no mesmo Python que roda este script — o .exe
carrega tudo o que esse Python tiver.

O resultado fica em dist/<NOME>.exe. As pastas build/ e dist/ e o arquivo
.spec são gerados a cada execução e não entram no repositório.

Por que cada opção existe:
- --onefile: um arquivo só, fácil de distribuir. (Na primeira execução o
  Windows descompacta o conteúdo numa pasta temporária, por isso demora
  alguns segundos para abrir.)
- --windowed: sem janela de console atrás da interface.
- --collect-all speech_recognition: a biblioteca traz binários (o
  conversor FLAC usado antes de enviar o áudio ao Google) que o PyInstaller
  não descobre sozinho.
- --hidden-import pyttsx3.drivers.sapi5: o pyttsx3 carrega o driver de voz
  do Windows por nome, em tempo de execução, e o PyInstaller só enxerga
  imports escritos no código.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

NOME = "Lanchonete"
PONTO_DE_ENTRADA = "gui.py"

AQUI = Path(__file__).resolve().parent


def main() -> int:
    for pasta in ("build", "dist"):
        shutil.rmtree(AQUI / pasta, ignore_errors=True)
    (AQUI / f"{NOME}.spec").unlink(missing_ok=True)

    comando = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", NOME,
        "--collect-all", "speech_recognition",
        "--hidden-import", "pyttsx3.drivers",
        "--hidden-import", "pyttsx3.drivers.sapi5",
        "--hidden-import", "comtypes.gen",
        PONTO_DE_ENTRADA,
    ]
    print("Gerando", NOME + ".exe ...")
    resultado = subprocess.run(comando, cwd=AQUI)
    if resultado.returncode != 0:
        print("Falhou. Veja as mensagens acima.")
        return resultado.returncode

    exe = AQUI / "dist" / f"{NOME}.exe"
    tamanho_mb = exe.stat().st_size / (1024 * 1024)
    print(f"\nPronto: {exe}  ({tamanho_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
