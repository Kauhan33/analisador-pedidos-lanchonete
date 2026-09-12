"""
Analisador de Pedidos da Lanchonete — ponto de entrada.

Uso:
    python main.py            -> modo interativo
    python main.py --demo     -> roda uma lista de comandos de exemplo (inclui erros propositais)
"""

from __future__ import annotations

import sys

from lexer import analisar_lexico
from semantic import Pedido, interpretar

COMANDOS_DEMO = [
    "Pedir Hamburguer",
    "Pedir 2 Refrigerante",
    "Pedir uma batata frita",
    "Remover Refrigerante",
    "Remover suco",             # erro: item não está no pedido
    "Pedir pizza de chocolate",  # "chocolate" não é reconhecido, mas "pizza" é adicionada
    "Mostrar pedido",
    "Finalizar pedido",
]


def processar(frase: str, pedido: Pedido, verboso: bool = True) -> str:
    tokens = analisar_lexico(frase)
    if verboso:
        print(f"  tokens: {tokens}")
    return interpretar(tokens, pedido)


def rodar_demo() -> None:
    pedido = Pedido()
    for frase in COMANDOS_DEMO:
        print(f"\nCliente: {frase}")
        print(f"Sistema: {processar(frase, pedido)}")


def rodar_interativo() -> None:
    pedido = Pedido()
    print("Analisador de Pedidos da Lanchonete (digite 'sair' para encerrar)\n")
    while True:
        try:
            frase = input("Cliente: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not frase:
            continue
        if frase.lower() in ("sair", "exit", "quit"):
            print("Sistema: Até logo!")
            break
        print(f"Sistema: {processar(frase, pedido, verboso=False)}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        rodar_demo()
    else:
        rodar_interativo()
