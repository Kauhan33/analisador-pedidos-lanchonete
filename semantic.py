"""
Analisador semântico + gerenciador de pedidos da lanchonete.

Recebe os tokens da fase léxica (lexer.py) e faz o que a análise léxica
sozinha não consegue: entender o *significado* da sequência.

1. **Associação** — descobrir a qual produto cada quantidade se refere.
   "2 hambúrgueres e 1 refrigerante" tem duas quantidades e dois produtos;
   é a ordem dos tokens que diz quem pertence a quem.
2. **Validação no contexto** — um pedido só faz sentido diante do estado
   atual do carrinho: não dá para remover o que não foi pedido, nem
   remover 5 de um item que tem 2.
3. **Ajuda diante do erro** — palavra fora do cardápio não é só rejeitada;
   quando é parecida com algum produto, vira uma sugestão.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cardapio
from cardapio import nome_exibicao, preco
from lexer import ACOES, Token, TipoToken

QUANTIDADE_MAXIMA = 99


@dataclass
class ItemPedido:
    """Uma dupla quantidade/produto já associada pela análise semântica."""

    quantidade: int
    produto: str

    def descrever(self) -> str:
        return f"{self.quantidade}x {nome_exibicao(self.produto)}"

    def subtotal(self) -> float:
        return preco(self.produto) * self.quantidade


@dataclass
class Pedido:
    itens: dict[str, int] = field(default_factory=dict)

    def adicionar(self, produto: str, quantidade: int) -> None:
        self.itens[produto] = self.itens.get(produto, 0) + quantidade

    def quantidade_de(self, produto: str) -> int:
        return self.itens.get(produto, 0)

    def remover(self, produto: str, quantidade: int) -> int:
        """Remove até `quantidade` unidades e devolve **quantas saíram de
        fato**.

        Devolver o número removido (em vez de só True/False) é o que impede
        a assistente de afirmar "removi 5x" quando havia apenas 2 no
        carrinho.
        """
        atual = self.quantidade_de(produto)
        if atual <= 0:
            return 0
        removidos = min(atual, quantidade)
        restante = atual - removidos
        if restante:
            self.itens[produto] = restante
        else:
            self.itens.pop(produto, None)
        return removidos

    def total(self) -> float:
        return sum(preco(produto) * qtd for produto, qtd in self.itens.items())

    def vazio(self) -> bool:
        return not self.itens

    def resumo(self) -> str:
        if self.vazio():
            return "o pedido está vazio."
        linhas = [
            f"{qtd}x {nome_exibicao(produto)} (R$ {preco(produto) * qtd:.2f})"
            for produto, qtd in self.itens.items()
        ]
        return "; ".join(linhas) + f" | Total: R$ {self.total():.2f}"


# --------------------------------------------------------------------------
# Associação entre quantidades e produtos
# --------------------------------------------------------------------------


def associar_itens(tokens: list[Token]) -> list[ItemPedido]:
    """
    Percorre os tokens na ordem em que foram ditos e monta os pares
    quantidade/produto.

    A regra é a da própria língua: a quantidade vem antes do produto a que
    se refere, e vale até aparecer esse produto. Assim, "2 hambúrgueres e 1
    refrigerante" vira 2 hambúrgueres + 1 refrigerante, e "hambúrguer e
    refrigerante" vira 1 de cada.
    """
    itens: list[ItemPedido] = []
    quantidade_pendente: int | None = None

    for token in tokens:
        if token.tipo == TipoToken.QUANTIDADE:
            quantidade_pendente = int(token.valor)
        elif token.tipo == TipoToken.PRODUTO:
            # comparar com None em vez de usar "or 1": a quantidade zero é
            # um valor legítimo aqui, e precisa chegar à validação para ser
            # recusada — "or 1" a transformaria silenciosamente em 1
            quantidade = 1 if quantidade_pendente is None else quantidade_pendente
            itens.append(ItemPedido(quantidade, token.valor))
            quantidade_pendente = None  # a quantidade vale para um produto só

    return _consolidar(itens)


def _consolidar(itens: list[ItemPedido]) -> list[ItemPedido]:
    """Junta repetições do mesmo produto na frase.

    O cliente pode chamar o mesmo item por nomes diferentes ("2 refri e uma
    coca"): são 3 refrigerantes, e a resposta deve dizer isso, em vez de
    listar o mesmo produto duas vezes."""
    agrupados: dict[str, int] = {}
    for item in itens:
        agrupados[item.produto] = agrupados.get(item.produto, 0) + item.quantidade
    return [ItemPedido(quantidade, produto) for produto, quantidade in agrupados.items()]


def _juntar(descricoes: list[str]) -> str:
    """Une descrições em português: "a", "a e b", "a, b e c"."""
    if len(descricoes) <= 1:
        return "".join(descricoes)
    return ", ".join(descricoes[:-1]) + " e " + descricoes[-1]


# --------------------------------------------------------------------------
# Ajuda
# --------------------------------------------------------------------------


def _palavras_da_acao(acao: str) -> list[str]:
    palavras = [palavra for palavra, canonica in ACOES.items() if canonica == acao]
    return sorted(palavras, key=lambda p: (p != acao.lower(), p))


def montar_ajuda() -> str:
    """Lista de comandos montada a partir do vocabulário real do lexer, para
    não divergir do que o programa aceita."""
    linhas = ["Comandos disponíveis:", ""]
    descricoes = [
        ("ADICIONAR", "<qtd> <produto>", "põe itens no pedido"),
        ("REMOVER", "<qtd> <produto>", "tira itens do pedido"),
        ("MOSTRAR", "", "mostra o pedido atual"),
        ("CARDAPIO", "", "lista produtos e preços"),
        ("FINALIZAR", "", "fecha a conta"),
        ("CANCELAR", "", "esvazia o pedido"),
        ("AJUDA", "", "esta lista"),
    ]
    for acao, argumento, explicacao in descricoes:
        palavras = "/".join(_palavras_da_acao(acao))
        uso = f"{palavras} {argumento}".strip()
        linhas.append(f"  {uso:<46} {explicacao}")

    linhas.append("")
    linhas.append("Dá para pedir vários itens de uma vez:")
    linhas.append("  pedir 2 hambúrguer e 1 refrigerante")
    linhas.append("A quantidade pode ser número ou por extenso (dois, três...).")
    return "\n".join(linhas)


AJUDA_FALADA = (
    "A lista completa apareceu na tela. Em resumo: você pode pedir, remover, "
    "ver o pedido, consultar o cardápio, finalizar ou cancelar. Dá para pedir "
    "vários itens de uma vez, como dois hambúrgueres e um refrigerante."
)


def texto_para_audio(resposta: str) -> str:
    """Versão adequada para ser falada: listas longas viram resumo, e a
    tela fica com o conteúdo completo."""
    if resposta.startswith("Comandos disponíveis:"):
        return AJUDA_FALADA
    if resposta.startswith("Cardápio:"):
        return cardapio.falado()
    return resposta


# --------------------------------------------------------------------------
# Interpretação
# --------------------------------------------------------------------------


def _resposta_para_desconhecidos(desconhecidos: list[Token]) -> str:
    """Monta a recusa de palavras fora do cardápio, sugerindo o produto
    parecido quando existe algum."""
    partes = []
    for token in desconhecidos:
        sugestao = cardapio.sugerir(token.lexema)
        if sugestao:
            partes.append(f"'{token.lexema}' (você quis dizer {nome_exibicao(sugestao)}?)")
        else:
            partes.append(f"'{token.lexema}'")
    return f"Não temos {_juntar(partes)} no cardápio."


def interpretar(tokens: list[Token], pedido: Pedido) -> str:
    """Fase de análise semântica: valida o significado do pedido e executa
    a ação correspondente sobre o carrinho."""

    acoes = [t for t in tokens if t.tipo == TipoToken.ACAO]
    desconhecidos = [t for t in tokens if t.tipo == TipoToken.DESCONHECIDO]

    if not acoes:
        if desconhecidos:
            return _resposta_para_desconhecidos(desconhecidos)
        return "Não entendi o que você quer fazer. Diga 'ajuda' para ver os comandos."
    if len(acoes) > 1:
        return "Entendi mais de um comando na mesma frase. Faça um de cada vez."

    acao = acoes[0].valor

    if acao == "AJUDA":
        return montar_ajuda()

    if acao == "CARDAPIO":
        return cardapio.listar()

    if acao == "CANCELAR":
        if pedido.vazio():
            return "O pedido já está vazio."
        pedido.itens.clear()
        return "Pedido cancelado."

    if acao == "MOSTRAR":
        return f"Seu pedido até agora: {pedido.resumo()}"

    if acao == "FINALIZAR":
        if pedido.vazio():
            return "Seu pedido está vazio, não há o que finalizar."
        resposta = f"Pedido finalizado -> {pedido.resumo()}"
        pedido.itens.clear()
        return resposta

    itens = associar_itens(tokens)
    if not itens:
        if desconhecidos:
            return _resposta_para_desconhecidos(desconhecidos)
        return "Não entendi qual produto você quer. Diga 'cardápio' para ver as opções."

    invalidas = [item for item in itens if item.quantidade <= 0]
    if invalidas:
        return "Quantidade inválida: informe um número maior que zero."

    excessivas = [item for item in itens if item.quantidade > QUANTIDADE_MAXIMA]
    if excessivas:
        return f"Quantidade alta demais: o máximo por item é {QUANTIDADE_MAXIMA}."

    if acao == "ADICIONAR":
        resposta = _adicionar(itens, pedido)
    elif acao == "REMOVER":
        resposta = _remover(itens, pedido)
    else:
        return "Comando não implementado."

    if desconhecidos:
        resposta += " " + _resposta_para_desconhecidos(desconhecidos)
    return resposta


def _adicionar(itens: list[ItemPedido], pedido: Pedido) -> str:
    for item in itens:
        pedido.adicionar(item.produto, item.quantidade)

    descricao = _juntar([item.descrever() for item in itens])
    subtotal = sum(item.subtotal() for item in itens)
    return (
        f"Adicionado {descricao} ao pedido (R$ {subtotal:.2f}). "
        f"Total do pedido: R$ {pedido.total():.2f}."
    )


def _remover(itens: list[ItemPedido], pedido: Pedido) -> str:
    removidos: list[str] = []
    parciais: list[str] = []
    ausentes: list[str] = []

    for item in itens:
        disponivel = pedido.quantidade_de(item.produto)
        saiu = pedido.remover(item.produto, item.quantidade)

        if saiu == 0:
            ausentes.append(nome_exibicao(item.produto))
        elif saiu < item.quantidade:
            # pediu para tirar mais do que havia: sai o que existe, e a
            # resposta diz a verdade sobre o que foi removido
            parciais.append(
                f"{saiu}x {nome_exibicao(item.produto)} "
                f"(você pediu {item.quantidade}, mas tinha {disponivel})"
            )
        else:
            removidos.append(item.descrever())

    partes = []
    if removidos:
        partes.append(f"Removido {_juntar(removidos)} do pedido.")
    if parciais:
        partes.append(f"Removido {_juntar(parciais)}.")
    if ausentes:
        partes.append(f"Você não tem {_juntar(ausentes)} no pedido.")

    partes.append(
        "Pedido vazio." if pedido.vazio() else f"Total do pedido: R$ {pedido.total():.2f}."
    )
    return " ".join(partes)
