"""
Analisador semântico + gerenciador de pedidos da lanchonete.

Recebe os tokens da fase léxica (lexer.py), valida se o pedido faz sentido
(produto existe no cardápio, quantidade válida, item realmente está no
carrinho antes de remover etc.) e mantém o estado do pedido atual.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lexer import Token, TipoToken, nome_exibicao, preco

AJUDA = (
    "Comandos disponíveis: 'pedir <qtd> <produto>', 'remover <qtd> <produto>', "
    "'mostrar pedido', 'finalizar pedido', 'cancelar pedido'."
)


@dataclass
class Pedido:
    itens: dict[str, int] = field(default_factory=dict)

    def adicionar(self, produto: str, quantidade: int) -> None:
        self.itens[produto] = self.itens.get(produto, 0) + quantidade

    def remover(self, produto: str, quantidade: int) -> bool:
        atual = self.itens.get(produto, 0)
        if atual <= 0:
            return False
        nova = atual - quantidade
        if nova <= 0:
            self.itens.pop(produto, None)
        else:
            self.itens[produto] = nova
        return True

    def total(self) -> float:
        return sum(preco(p) * qtd for p, qtd in self.itens.items())

    def vazio(self) -> bool:
        return not self.itens

    def resumo(self) -> str:
        if self.vazio():
            return "o pedido está vazio."
        linhas = [
            f"{qtd}x {nome_exibicao(p)} (R$ {preco(p) * qtd:.2f})"
            for p, qtd in self.itens.items()
        ]
        return "; ".join(linhas) + f" | Total: R$ {self.total():.2f}"


def interpretar(tokens: list[Token], pedido: Pedido) -> str:
    """Fase de análise semântica: valida o significado do pedido e executa
    a ação correspondente sobre o carrinho (Pedido)."""

    acoes = [t for t in tokens if t.tipo == TipoToken.ACAO]
    produtos = [t for t in tokens if t.tipo == TipoToken.PRODUTO]
    quantidades = [t for t in tokens if t.tipo == TipoToken.QUANTIDADE]
    desconhecidos = [t for t in tokens if t.tipo == TipoToken.DESCONHECIDO]

    if not acoes:
        return "Não entendi o que você quer fazer. " + AJUDA

    acao = acoes[0].valor

    if acao == "AJUDA":
        return AJUDA

    if acao == "CANCELAR":
        pedido.itens.clear()
        return "Pedido cancelado."

    if acao == "MOSTRAR":
        return f"Seu pedido até agora: {pedido.resumo()}"

    if acao == "FINALIZAR":
        if pedido.vazio():
            return "Seu carrinho está vazio, não há o que finalizar."
        resposta = f"Pedido finalizado -> {pedido.resumo()}"
        pedido.itens.clear()
        return resposta

    # ADICIONAR e REMOVER exigem um produto reconhecido no cardápio
    if not produtos:
        if desconhecidos:
            nomes = ", ".join(f"'{t.lexema}'" for t in desconhecidos)
            return f"Não reconheço {nomes} no cardápio."
        return "Não entendi qual produto você quer. " + AJUDA

    produto = produtos[0].valor
    quantidade = int(quantidades[0].valor) if quantidades else 1

    if quantidade <= 0:
        return "Quantidade inválida: informe um número maior que zero."

    if acao == "ADICIONAR":
        pedido.adicionar(produto, quantidade)
        return (
            f"Adicionado {quantidade}x {nome_exibicao(produto)} ao pedido. "
            f"Subtotal do item: R$ {preco(produto) * quantidade:.2f}."
        )

    if acao == "REMOVER":
        if not pedido.remover(produto, quantidade):
            return f"Você não tem {nome_exibicao(produto)} no pedido para remover."
        return f"Removido {quantidade}x {nome_exibicao(produto)} do pedido."

    return "Comando não implementado."
