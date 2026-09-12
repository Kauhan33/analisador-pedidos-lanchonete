"""
Analisador léxico do sistema de pedidos da lanchonete.

Transforma uma frase de pedido em uma lista de tokens (ação, quantidade,
produto), da mesma forma que a fase léxica de um compilador identifica os
"átomos" de significado em um texto de entrada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum, auto


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
    "pedir": "ADICIONAR", "adicionar": "ADICIONAR", "quero": "ADICIONAR", "add": "ADICIONAR",
    "remover": "REMOVER", "tirar": "REMOVER", "excluir": "REMOVER",
    "cancelar": "CANCELAR", "limpar": "CANCELAR",
    "finalizar": "FINALIZAR", "concluir": "FINALIZAR", "fechar": "FINALIZAR",
    "mostrar": "MOSTRAR", "ver": "MOSTRAR", "listar": "MOSTRAR",
    "ajuda": "AJUDA",
}

# cardápio: nome canônico -> (sinônimos, preço em R$)
CARDAPIO: dict[str, tuple[list[str], float]] = {
    "hamburguer": (["hamburguer", "hamburgueres", "hamburger", "x-burguer", "xburguer"], 18.00),
    "refrigerante": (["refrigerante", "refrigerantes", "refri", "refris"], 6.00),
    "batata_frita": (["batata frita", "batatas fritas", "batata"], 12.00),
    "suco": (["suco", "sucos"], 7.00),
    "pizza": (["pizza", "pizzas"], 35.00),
    "sorvete": (["sorvete", "sorvetes"], 9.00),
    "cachorro_quente": (["cachorro quente", "cachorro-quente", "hot dog", "hotdog"], 10.00),
    "agua": (["agua", "aguas"], 4.00),
    "milkshake": (["milkshake", "milk shake"], 11.00),
    "salada": (["salada", "saladas"], 15.00),
}

EXTENSO: dict[str, int] = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
}

PALAVRAS_IGNORADAS = {
    "de", "do", "da", "dos", "das", "o", "a", "os", "as", "por", "favor",
    "para", "pra", "com", "e", "no", "na",
}


def _normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def analisar_lexico(frase: str) -> list[Token]:
    """
    Percorre a frase palavra a palavra (com lookahead de 2 palavras para
    reconhecer produtos compostos, como "batata frita") e devolve a lista
    de tokens classificados.
    """
    palavras = _normalizar(frase).split(" ") if frase.strip() else []
    tokens: list[Token] = []

    i = 0
    while i < len(palavras):
        palavra = palavras[i]
        duas_palavras = " ".join(palavras[i:i + 2]) if i + 1 < len(palavras) else None

        # 1) produto composto (2 palavras), ex.: "batata frita", "cachorro quente"
        casado = False
        if duas_palavras:
            for canonico, (sinonimos, _preco) in CARDAPIO.items():
                if duas_palavras in sinonimos:
                    tokens.append(Token(TipoToken.PRODUTO, canonico, duas_palavras))
                    i += 2
                    casado = True
                    break
        if casado:
            continue

        # 2) ação
        if palavra in ACOES:
            tokens.append(Token(TipoToken.ACAO, ACOES[palavra], palavra))
            i += 1
            continue

        # 3) produto de uma palavra só
        encontrado = None
        for canonico, (sinonimos, _preco) in CARDAPIO.items():
            if palavra in sinonimos:
                encontrado = canonico
                break
        if encontrado:
            tokens.append(Token(TipoToken.PRODUTO, encontrado, palavra))
            i += 1
            continue

        # 4) quantidade numérica ou por extenso
        if re.fullmatch(r"\d+", palavra):
            tokens.append(Token(TipoToken.QUANTIDADE, palavra, palavra))
            i += 1
            continue
        if palavra in EXTENSO:
            tokens.append(Token(TipoToken.QUANTIDADE, str(EXTENSO[palavra]), palavra))
            i += 1
            continue

        # 5) conectivo
        if palavra in PALAVRAS_IGNORADAS:
            tokens.append(Token(TipoToken.CONECTIVO, palavra, palavra))
            i += 1
            continue

        # 6) desconhecida
        tokens.append(Token(TipoToken.DESCONHECIDO, palavra, palavra))
        i += 1

    return tokens


def preco(produto_canonico: str) -> float:
    return CARDAPIO[produto_canonico][1]


def nome_exibicao(produto_canonico: str) -> str:
    return produto_canonico.replace("_", " ").capitalize()
