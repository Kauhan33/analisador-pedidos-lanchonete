"""
Detecção da palavra-chave ("Atendente") nas frases reconhecidas por voz.

Com o microfone aberto no balcão, quase tudo que é captado é conversa —
entre clientes, na mesa ao lado, na TV. Só deve virar pedido aquilo que foi
dirigido ao sistema, e é a palavra-chave que marca essa intenção:

    "Atendente, pedir dois hambúrgueres"

O reconhecimento de fala erra bastante em nomes, então o casamento não é
exato. São três camadas:

1. uma lista de variações já previstas (casamento exato, rápido);
2. similaridade aproximada (difflib) para as não previstas — o limiar 0.72
   foi calibrado contra o vocabulário real da lanchonete: aceita
   "atendent" (0.94) e "atendendo" (0.78), e rejeita as palavras do
   domínio, que ficam todas abaixo de 0.63;
3. tratamento de resíduo: quando o nome sai quebrado em duas palavras
   ("a tendente pedir"), a segunda só é absorvida se for curta E não
   significar nada no vocabulário — assim "Atendente 2 sucos" preserva o 2.

Isso funciona como uma etapa *anterior* à análise léxica: separa o que é
pedido do que é conversa, antes de a frase virar tokens.
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from lexer import TipoToken, analisar_lexico

PALAVRA_CHAVE = "atendente"

# Limiar de similaridade (0 a 1) calibrado com o vocabulário da lanchonete.
LIMIAR_SIMILARIDADE = 0.72

# Tamanho máximo de uma palavra para ser considerada "resto" do nome mal
# transcrito (o "a" de "a tendente").
MAX_TAMANHO_RESIDUO = 3

VARIACOES_CONHECIDAS = {
    "atendente", "atendentes", "atendent", "antendente", "atendende",
    "atende", "atendendo", "entendente", "atendenti", "tendente",
    "atendimento", "garcom", "garcon",
}


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acentuação e sem pontuação — só letras."""
    texto = texto.lower().strip()
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sem_acento if c.isalpha())


def parece_palavra_chave(candidato: str) -> bool:
    """True se `candidato` é a palavra-chave ou algo parecido o suficiente."""
    candidato = _normalizar(candidato)
    if not candidato:
        return False
    if candidato in VARIACOES_CONHECIDAS:
        return True
    return SequenceMatcher(None, candidato, PALAVRA_CHAVE).ratio() >= LIMIAR_SIMILARIDADE


def _e_residuo(palavra: str) -> bool:
    """True se `palavra` é curta e não significa nada no vocabulário do
    lexer — ou seja, provável sobra de uma transcrição errada do nome, e não
    parte do pedido."""
    normalizada = _normalizar(palavra)
    if not normalizada or len(normalizada) > MAX_TAMANHO_RESIDUO:
        return False
    tokens = analisar_lexico(normalizada)
    return all(
        token.tipo in (TipoToken.DESCONHECIDO, TipoToken.CONECTIVO) for token in tokens
    )


def extrair_comando(frase: str) -> str | None:
    """
    Devolve o pedido que vem depois da palavra-chave, ou None se a frase não
    foi dirigida ao sistema (sem palavra-chave no início).

    Devolve string vazia quando só a palavra-chave é dita, sem pedido algum.

    >>> extrair_comando("Atendente, pedir dois hambúrgueres")
    'pedir dois hambúrgueres'
    >>> extrair_comando("Atendente cardápio")
    'cardápio'
    >>> extrair_comando("o hambúrguer daqui é bom") is None
    True
    """
    palavras = frase.strip().split()
    if not palavras:
        return None

    # Hipótese 1: o nome foi transcrito quebrado em duas palavras. Isso
    # acontece dos dois jeitos — o pedaço solto pode vir depois do nome
    # ("atendent e"), ou antes dele ("a tendente"). Em qualquer caso, só
    # juntamos as duas quando o pedaço extra não significa nada sozinho,
    # para não engolir parte do pedido ("Atendente 2 sucos").
    if len(palavras) >= 2:
        primeira_e_curta = len(_normalizar(palavras[0])) <= MAX_TAMANHO_RESIDUO
        if (_e_residuo(palavras[1]) or primeira_e_curta) and parece_palavra_chave(
            palavras[0] + palavras[1]
        ):
            return " ".join(palavras[2:]).strip(" ,.!?;:")

    # Hipótese 2: o nome é a primeira palavra.
    if parece_palavra_chave(palavras[0]):
        return " ".join(palavras[1:]).strip(" ,.!?;:")

    return None
