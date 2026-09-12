"""
Analisador léxico do sistema de pedidos da lanchonete.

Transforma uma frase de pedido em uma lista de tokens (ação, quantidade,
produto), da mesma forma que a fase léxica de um compilador identifica os
"átomos" de significado em um texto de entrada.

O vocabulário de produtos não é definido aqui: vem do cardapio.py, que é a
fonte única de produtos e preços.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum, auto

from cardapio import PRODUTOS, buscar_por_sinonimo


class TipoToken(Enum):
    ACAO = auto()
    QUANTIDADE = auto()
    PRODUTO = auto()
    CONECTIVO = auto()
    DESCONHECIDO = auto()


@dataclass
class Token:
    tipo: TipoToken
    valor: str
    lexema: str

    def __repr__(self) -> str:
        return f"<{self.tipo.name}:{self.valor}>"


ACOES: dict[str, str] = {
    "pedir": "ADICIONAR", "adicionar": "ADICIONAR", "quero": "ADICIONAR",
    "add": "ADICIONAR", "coloca": "ADICIONAR", "colocar": "ADICIONAR",
    "remover": "REMOVER", "remove": "REMOVER", "tirar": "REMOVER",
    "tira": "REMOVER", "excluir": "REMOVER", "retirar": "REMOVER",
    "cancelar": "CANCELAR", "limpar": "CANCELAR",
    "finalizar": "FINALIZAR", "concluir": "FINALIZAR", "fechar": "FINALIZAR",
    "mostrar": "MOSTRAR", "ver": "MOSTRAR", "listar": "MOSTRAR",
    "cardapio": "CARDAPIO", "menu": "CARDAPIO", "precos": "CARDAPIO", "preco": "CARDAPIO",
    "ajuda": "AJUDA", "comandos": "AJUDA", "help": "AJUDA",
}

EXTENSO: dict[str, int] = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "duzia": 12,
}

# Palavras que ligam a frase sem acrescentar significado próprio. "e" está
# aqui e é importante: é o que separa os itens em "2 hambúrguer E 1 suco".
PALAVRAS_IGNORADAS = {
    "de", "do", "da", "dos", "das", "o", "a", "os", "as", "por", "favor",
    "para", "pra", "com", "e", "no", "na", "mais", "meu", "minha", "gostaria",
    "queria", "pedido", "conta", "tudo", "isso", "ai", "me", "diga",
    "qual", "quais", "lista", "sao", "voces", "tem",
}
# "um"/"uma" ficam fora desta lista de propósito: são reconhecidos antes,
# como quantidade 1 ("pedir um hambúrguer"), o que dá no mesmo resultado de
# tratá-los como artigo.


def _normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


# maior número de palavras que um sinônimo de produto ocupa ("cachorro quente")
_MAIOR_SINONIMO = max(len(sinonimo.split()) for p in PRODUTOS for sinonimo in p.sinonimos)


def analisar_lexico(frase: str) -> list[Token]:
    """
    Percorre a frase palavra a palavra, olhando à frente o suficiente para
    reconhecer produtos escritos com mais de uma palavra ("batata frita",
    "cachorro quente"), e devolve a lista de tokens classificados.
    """
    palavras = _normalizar(frase).split(" ") if frase.strip() else []
    tokens: list[Token] = []

    indice = 0
    while indice < len(palavras):
        # 1) produto composto: tenta primeiro a maior sequência possível
        casou = False
        for tamanho in range(min(_MAIOR_SINONIMO, len(palavras) - indice), 1, -1):
            trecho = " ".join(palavras[indice : indice + tamanho])
            codigo = buscar_por_sinonimo(trecho)
            if codigo:
                tokens.append(Token(TipoToken.PRODUTO, codigo, trecho))
                indice += tamanho
                casou = True
                break
        if casou:
            continue

        palavra = palavras[indice]

        # 2) ação
        if palavra in ACOES:
            tokens.append(Token(TipoToken.ACAO, ACOES[palavra], palavra))
            indice += 1
            continue

        # 3) produto de uma palavra só
        codigo = buscar_por_sinonimo(palavra)
        if codigo:
            tokens.append(Token(TipoToken.PRODUTO, codigo, palavra))
            indice += 1
            continue

        # 4) quantidade numérica ou por extenso
        if re.fullmatch(r"\d+", palavra):
            tokens.append(Token(TipoToken.QUANTIDADE, palavra, palavra))
            indice += 1
            continue
        if palavra in EXTENSO:
            tokens.append(Token(TipoToken.QUANTIDADE, str(EXTENSO[palavra]), palavra))
            indice += 1
            continue

        # 5) conectivo
        if palavra in PALAVRAS_IGNORADAS:
            tokens.append(Token(TipoToken.CONECTIVO, palavra, palavra))
            indice += 1
            continue

        # 6) nada reconhecido
        tokens.append(Token(TipoToken.DESCONHECIDO, palavra, palavra))
        indice += 1

    return tokens
