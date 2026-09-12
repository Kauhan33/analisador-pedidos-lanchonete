"""
Cardápio da lanchonete: a fonte única dos produtos, preços e apelidos.

Fica separado do lexer de propósito. O cardápio é um dado do negócio — quem
precisa dele não é só a análise léxica (para reconhecer as palavras), mas
também a análise semântica (preços e totais), a listagem para o cliente e a
interface gráfica. Centralizar aqui evita que o preço de um lanche exista
escrito em dois lugares diferentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Produto:
    codigo: str          # nome canônico, usado internamente
    nome: str            # nome bonito, mostrado ao cliente
    preco: float
    sinonimos: tuple[str, ...]  # como o cliente pode escrever/falar


# Os sinônimos são escritos sem acento e em minúsculas porque o lexer
# normaliza o texto do cliente dessa forma antes de comparar.
PRODUTOS: tuple[Produto, ...] = (
    Produto("hamburguer", "Hambúrguer", 18.00,
            ("hamburguer", "hamburgueres", "hamburger", "burguer", "x-burguer", "xburguer", "lanche")),
    Produto("cachorro_quente", "Cachorro-quente", 10.00,
            ("cachorro quente", "cachorro-quente", "cachorros quentes", "hot dog", "hotdog", "dogao")),
    Produto("pizza", "Pizza", 35.00, ("pizza", "pizzas")),
    Produto("batata_frita", "Batata frita", 12.00,
            ("batata frita", "batatas fritas", "batata", "batatas", "fritas")),
    Produto("salada", "Salada", 15.00, ("salada", "saladas")),
    Produto("refrigerante", "Refrigerante", 6.00,
            ("refrigerante", "refrigerantes", "refri", "refris", "coca", "guarana")),
    Produto("suco", "Suco", 7.00, ("suco", "sucos")),
    Produto("agua", "Água", 4.00, ("agua", "aguas", "agua mineral")),
    Produto("milkshake", "Milkshake", 11.00, ("milkshake", "milk shake", "milkshakes")),
    Produto("sorvete", "Sorvete", 9.00, ("sorvete", "sorvetes", "casquinha")),
)

POR_CODIGO: dict[str, Produto] = {produto.codigo: produto for produto in PRODUTOS}

# Similaridade mínima para sugerir um produto quando o cliente escreve algo
# parecido, mas fora do cardápio ("hamburgue" -> "Hambúrguer").
LIMIAR_SUGESTAO = 0.7


def preco(codigo: str) -> float:
    return POR_CODIGO[codigo].preco


def nome_exibicao(codigo: str) -> str:
    produto = POR_CODIGO.get(codigo)
    return produto.nome if produto else codigo.replace("_", " ")


def buscar_por_sinonimo(palavra: str) -> str | None:
    """Devolve o código do produto cujo sinônimo é exatamente `palavra`."""
    for produto in PRODUTOS:
        if palavra in produto.sinonimos:
            return produto.codigo
    return None


def sugerir(palavra: str) -> str | None:
    """
    Produto mais parecido com `palavra`, ou None se nada chegar perto.

    É o que transforma "não reconheço 'hamburgue'" em "você quis dizer
    Hambúrguer?" — erros de digitação e de transcrição por voz são comuns
    demais para simplesmente rejeitar a palavra.
    """
    melhor_codigo = None
    melhor_nota = 0.0

    for produto in PRODUTOS:
        for sinonimo in produto.sinonimos:
            nota = SequenceMatcher(None, palavra, sinonimo).ratio()
            if nota > melhor_nota:
                melhor_nota, melhor_codigo = nota, produto.codigo

    return melhor_codigo if melhor_nota >= LIMIAR_SUGESTAO else None


def listar() -> str:
    """Cardápio formatado para o cliente, em ordem de preço."""
    linhas = ["Cardápio:"]
    for produto in sorted(PRODUTOS, key=lambda p: p.preco):
        linhas.append(f"  {produto.nome:<16} R$ {produto.preco:6.2f}")
    return "\n".join(linhas)


def falado() -> str:
    """Cardápio em uma frase, para ser lido em voz alta."""
    itens = [f"{produto.nome}, {produto.preco:.2f} reais" for produto in PRODUTOS]
    return "Temos " + "; ".join(itens) + "."
