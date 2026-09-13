"""
Analisador de Pedidos da Lanchonete — ponto de entrada.

Uso:
    python main.py            -> modo interativo (digitado)
    python main.py --gui      -> abre a interface gráfica (ver gui.py)
    python main.py --demo     -> roda uma lista de pedidos de exemplo (inclui erros propositais)

Comandos aceitos (digite "ajuda" dentro do programa para a lista completa):
pedir, remover, mostrar, cardápio, finalizar, cancelar e sair. Dá para pedir
vários itens de uma vez — "pedir 2 hambúrguer e 1 refrigerante".
"""

from __future__ import annotations

import sys

from lexer import analisar_lexico
from semantic import Pedido, interpretar

COMANDOS_DEMO = [
    "Pedir Hamburguer",
    "2 hamburguers e dois refrigerantes",    # sem verbo, no plural
    "quero tres batata frita e dois suco",   # vários itens na mesma frase
    "me vê um x-burguer",                    # coloquial, com hífen
    "quanto custa a pizza",                  # consulta de preço
    "Remover Refrigerante",
    "remover 5 hamburguer",                  # mais do que existe no pedido
    "Remover suco",                          # ainda há suco: sai normalmente
    "Pedir hamburgue",                       # erro de digitação -> sugestão
    "Pedir lasanha",                         # fora do cardápio
    "Cardapio",
    "Mostrar pedido",
    "Finalizar pedido",
]

COMANDOS_SAIR = ("sair", "exit", "quit")


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
    print("Analisador de Pedidos da Lanchonete")
    print("Digite 'cardapio' para ver os produtos, 'ajuda' para os comandos, 'sair' para encerrar.\n")

    while True:
        try:
            frase = input("Cliente: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not frase:
            continue
        if frase.lower() in COMANDOS_SAIR:
            print("Sistema: Até logo!")
            break

        print(f"Sistema: {processar(frase, pedido, verboso=False)}")


def abrir_interface_grafica() -> None:
    """Abre a janela do gui.py. O import fica aqui dentro para o modo
    terminal continuar funcionando em instalações sem tkinter."""
    try:
        from gui import main as abrir_janela
    except ImportError as erro:
        print(
            "Não foi possível abrir a interface gráfica: tkinter não está "
            f"disponível nesta instalação do Python ({erro}).\n"
            "Use o modo terminal: python main.py"
        )
        return
    abrir_janela()


if __name__ == "__main__":
    if "--gui" in sys.argv:
        abrir_interface_grafica()
    elif "--demo" in sys.argv:
        rodar_demo()
    else:
        rodar_interativo()
