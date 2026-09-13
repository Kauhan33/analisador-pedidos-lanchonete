"""
Analisador léxico do sistema de pedidos da lanchonete.

Transforma uma frase de pedido em uma lista de tokens (ação, quantidade,
produto), da mesma forma que a fase léxica de um compilador identifica os
"átomos" de significado em um texto de entrada.

O vocabulário de produtos não é definido aqui: vem do cardapio.py, que é a
fonte única de produtos e preços.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from difflib import SequenceMatcher
from dataclasses import dataclass
from enum import Enum, auto

from cardapio import PRODUTOS


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


# Cada verbo aparece nas formas em que um cliente realmente fala: infinitivo
# ("pedir"), imperativo/presente ("pede", "tira", "fecha") e os coloquiais
# de balcão ("me vê", "bota", "manda"). Sem isso, "fecha a conta" não seria
# entendido só porque a lista tinha "fechar".
ACOES: dict[str, str] = {
    # ADICIONAR
    "pedir": "ADICIONAR", "pede": "ADICIONAR", "peca": "ADICIONAR", "pedimos": "ADICIONAR",
    "adicionar": "ADICIONAR", "adiciona": "ADICIONAR", "add": "ADICIONAR",
    "quero": "ADICIONAR", "queremos": "ADICIONAR", "querer": "ADICIONAR", "quer": "ADICIONAR",
    "coloca": "ADICIONAR", "colocar": "ADICIONAR", "bota": "ADICIONAR", "botar": "ADICIONAR",
    "ve": "ADICIONAR", "traz": "ADICIONAR", "trazer": "ADICIONAR", "manda": "ADICIONAR",
    "inclui": "ADICIONAR", "incluir": "ADICIONAR",
    "adicione": "ADICIONAR", "coloque": "ADICIONAR", "inclua": "ADICIONAR",
    "bote": "ADICIONAR", "traga": "ADICIONAR", "mande": "ADICIONAR",
    # REMOVER
    "remover": "REMOVER", "remove": "REMOVER", "tirar": "REMOVER", "tira": "REMOVER",
    "excluir": "REMOVER", "exclui": "REMOVER", "retirar": "REMOVER", "retira": "REMOVER",
    "remova": "REMOVER", "tire": "REMOVER", "retire": "REMOVER", "exclua": "REMOVER",
    "apague": "REMOVER", "apagar": "REMOVER",
    # CANCELAR
    "cancelar": "CANCELAR", "cancela": "CANCELAR", "limpar": "CANCELAR", "limpa": "CANCELAR",
    "esvaziar": "CANCELAR", "esvazia": "CANCELAR", "cancele": "CANCELAR", "limpe": "CANCELAR",
    # FINALIZAR
    "finalizar": "FINALIZAR", "finaliza": "FINALIZAR", "concluir": "FINALIZAR",
    "conclui": "FINALIZAR", "fechar": "FINALIZAR", "fecha": "FINALIZAR",
    "encerrar": "FINALIZAR", "encerra": "FINALIZAR", "pagar": "FINALIZAR",
    "finalize": "FINALIZAR", "feche": "FINALIZAR", "encerre": "FINALIZAR",
    # MOSTRAR
    "mostrar": "MOSTRAR", "mostra": "MOSTRAR", "ver": "MOSTRAR", "listar": "MOSTRAR",
    "lista": "MOSTRAR", "exibir": "MOSTRAR", "exibe": "MOSTRAR", "mostre": "MOSTRAR",
    # CARDAPIO / preço
    "cardapio": "CARDAPIO", "menu": "CARDAPIO", "precos": "CARDAPIO", "preco": "CARDAPIO",
    "custa": "CARDAPIO", "custam": "CARDAPIO", "valor": "CARDAPIO", "valores": "CARDAPIO",
    # AJUDA
    "ajuda": "AJUDA", "comandos": "AJUDA", "help": "AJUDA",
    # CONFIRMAR / NEGAR: respostas a uma sugestão ("você quis dizer X?")
    "sim": "CONFIRMAR", "isso": "CONFIRMAR", "exato": "CONFIRMAR", "ok": "CONFIRMAR",
    "confirmo": "CONFIRMAR", "certo": "CONFIRMAR", "aham": "CONFIRMAR", "uhum": "CONFIRMAR",
    "nao": "NEGAR", "negativo": "NEGAR",
}

# Radicais dos verbos, para reconhecer qualquer conjugação que não esteja
# listada acima ("adicione", "remova", "tire", "cancele", "removendo"...).
# Uma palavra que COMEÇA com um destes radicais é tratada como a ação
# correspondente — mas só depois de já ter sido descartada como produto,
# quantidade ou palavra ignorada, para "pedido" não virar "pedir".
RADICAIS_ACAO: dict[str, str] = {
    "adicion": "ADICIONAR", "acrescent": "ADICIONAR", "inclu": "ADICIONAR",
    "coloc": "ADICIONAR", "coloq": "ADICIONAR", "quer": "ADICIONAR", "bot": "ADICIONAR",
    "remov": "REMOVER", "retir": "REMOVER", "tir": "REMOVER", "exclu": "REMOVER",
    "apag": "REMOVER", "delet": "REMOVER",
    "cancel": "CANCELAR", "limp": "CANCELAR", "esvazi": "CANCELAR",
    "finaliz": "FINALIZAR", "fech": "FINALIZAR", "encerr": "FINALIZAR", "conclu": "FINALIZAR",
    "mostr": "MOSTRAR", "exib": "MOSTRAR",
}


def acao_por_radical(palavra: str) -> str | None:
    for radical, acao in RADICAIS_ACAO.items():
        if palavra.startswith(radical) and len(palavra) > len(radical):
            return acao
    return None


def acao_aproximada(palavra: str) -> str | None:
    """Verbo de comando parecido com `palavra` — o reconhecimento de fala
    erra o verbo tanto quanto erra o nome do produto, e "adissione" ou
    "quiero" não devem derrubar um pedido inteiro."""
    if len(palavra) < 4:
        return None
    melhor, melhor_nota = None, 0.0
    for verbo, acao in ACOES.items():
        if len(verbo) < 4 or acao in ("CONFIRMAR", "NEGAR"):
            continue
        nota = SequenceMatcher(None, palavra, verbo).ratio()
        if nota > melhor_nota:
            melhor, melhor_nota = acao, nota
    return melhor if melhor_nota >= LIMIAR_VERBO_APROXIMADO else None


# Ações que são um pedido de fato (mexem no carrinho ou consultam algo).
# CONFIRMAR/NEGAR ficam de fora: sozinhos, "sim" ou "não" não são comando.
ACOES_DE_COMANDO = {
    "ADICIONAR", "REMOVER", "CANCELAR", "FINALIZAR", "MOSTRAR", "CARDAPIO", "AJUDA",
}


def tem_comando_explicito(tokens: list[Token]) -> bool:
    """
    True se a frase traz um verbo de comando ("quero", "adicione", "me vê",
    "remova", "cardápio"...).

    É o filtro usado pela voz: com o microfone aberto, quase tudo captado é
    conversa, e o que separa um pedido dela é justamente o verbo. "Dois
    hambúrgueres" dito à mesa pode ser só conversa; "quero dois hambúrgueres"
    é um pedido.
    """
    return any(
        t.tipo == TipoToken.ACAO and t.valor in ACOES_DE_COMANDO for t in tokens
    )

EXTENSO: dict[str, int] = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "duzia": 12,
}

# Quantidades que só fazem sentido diante do carrinho: "remover TODAS as
# águas", "tirar METADE dos refris". Viram tokens QUANTIDADE com um valor
# simbólico, e a semântica resolve o número olhando o pedido atual.
QUANTIDADES_ESPECIAIS: dict[str, str] = {
    "todas": "todas", "todos": "todas", "toda": "todas", "todo": "todas", "tudo": "todas",
    "metade": "metade",
}

# "um de cada" — o produto é "todos os do cardápio". Vira um token PRODUTO
# com o código simbólico "*", expandido pela semântica.
PALAVRA_CADA = "cada"
PRODUTO_TODOS = "*"

# Similaridade mínima para aceitar um verbo transcrito errado ("adissione",
# "removi" -> "remova"). Só palavras com 4+ letras entram nessa comparação:
# as curtas ("ve", "ok", "sim") casariam com qualquer coisa.
LIMIAR_VERBO_APROXIMADO = 0.8

# Palavras que ligam a frase sem acrescentar significado próprio. "e" está
# aqui e é importante: é o que separa os itens em "2 hambúrguer E 1 suco".
# As demais são o que sobra de frases naturais de balcão ("eu vou querer",
# "pode adicionar", "quanto custa") depois de tirar verbos e produtos —
# sem constar aqui, virariam "não temos 'eu' no cardápio".
PALAVRAS_IGNORADAS = {
    "de", "do", "da", "dos", "das", "o", "a", "os", "as", "por", "favor",
    "para", "pra", "com", "e", "no", "na", "mais", "meu", "minha", "gostaria",
    "queria", "pedido", "conta", "isso", "ai", "me", "diga",
    "qual", "quais", "sao", "voces", "tem", "eu", "nos", "vou", "vamos",
    "pode", "poderia", "podia", "quanto", "quantos", "esta", "fica",
    "sai", "deu", "entao", "ne", "obrigado", "obrigada", "oi", "ola", "bom",
    "boa", "dia", "tarde", "noite", "agora", "ja", "so", "tambem", "tbm",
    "aqui", "pro", "ao", "num", "numa", "outro", "outra", "desse", "dessa",
    "daquele", "daquela", "esse", "essa", "este", "item", "itens",
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


def candidatos_singular(palavra: str) -> list[str]:
    """
    Formas que `palavra` pode ter no singular, da mais provável à menos.

    O plural em português quase sempre é um sufixo previsível, então em vez
    de listar cada plural no cardápio ("hamburgueres", "hamburguers",
    "refrigerantes", ...), o lexer tenta desfazê-lo: "hamburguers" -> tira o
    "s" -> "hamburguer". A própria palavra vem primeiro na lista, para que
    um termo que já existe no singular case direto.
    """
    formas = [palavra]
    if palavra.endswith("s") and len(palavra) > 2:
        formas.append(palavra[:-1])           # refrigerantes -> refrigerante
    if palavra.endswith("es") and len(palavra) > 3:
        formas.append(palavra[:-2])           # hamburgueres -> hamburguer
    if palavra.endswith("oes") and len(palavra) > 4:
        formas.append(palavra[:-3] + "ao")    # porcoes -> porcao
    if palavra.endswith("ais") and len(palavra) > 4:
        formas.append(palavra[:-3] + "al")    # especiais -> especial
    return formas


# Índice de sinônimos passado pela MESMA normalização que o texto do cliente
# recebe. É o que faz "x-burguer" casar: o hífen vira espaço nos dois lados,
# e não só na frase digitada.
_INDICE_SINONIMOS: dict[str, str] = {
    _normalizar(sinonimo): produto.codigo
    for produto in PRODUTOS
    for sinonimo in produto.sinonimos
}

# maior número de palavras que um sinônimo de produto ocupa ("cachorro quente")
_MAIOR_SINONIMO = max(len(chave.split()) for chave in _INDICE_SINONIMOS)


def _buscar_produto(palavras: list[str]) -> str | None:
    """Procura um produto para a sequência de palavras, aceitando cada uma
    delas no plural: "cachorros quentes" -> "cachorro quente"."""
    trecho = " ".join(palavras)
    if trecho in _INDICE_SINONIMOS:
        return _INDICE_SINONIMOS[trecho]

    # tenta as combinações de singular de cada palavra (poucas: no máximo
    # 3 palavras x 4 formas cada)
    for combinacao in itertools.product(*(candidatos_singular(p) for p in palavras)):
        codigo = _INDICE_SINONIMOS.get(" ".join(combinacao))
        if codigo:
            return codigo
    return None


def analisar_lexico(frase: str) -> list[Token]:
    """
    Percorre a frase palavra a palavra, olhando à frente o suficiente para
    reconhecer produtos escritos com mais de uma palavra ("batata frita",
    "cachorro quente"), e devolve a lista de tokens classificados.
    """
    # split() sem argumento descarta pedaços vazios: "???" normaliza para ""
    # e, com split(" "), viraria uma "palavra" vazia classificada como
    # desconhecida ("não temos '' no cardápio")
    palavras = _normalizar(frase).split()
    tokens: list[Token] = []

    indice = 0
    while indice < len(palavras):
        # 1) produto composto: tenta primeiro a maior sequência possível
        casou = False
        for tamanho in range(min(_MAIOR_SINONIMO, len(palavras) - indice), 1, -1):
            trecho = palavras[indice : indice + tamanho]
            codigo = _buscar_produto(trecho)
            if codigo:
                tokens.append(Token(TipoToken.PRODUTO, codigo, " ".join(trecho)))
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

        # 3) produto de uma palavra só (singular ou plural)
        codigo = _buscar_produto([palavra])
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
        if palavra in QUANTIDADES_ESPECIAIS:
            tokens.append(Token(TipoToken.QUANTIDADE, QUANTIDADES_ESPECIAIS[palavra], palavra))
            indice += 1
            continue
        if palavra == PALAVRA_CADA:
            tokens.append(Token(TipoToken.PRODUTO, PRODUTO_TODOS, palavra))
            indice += 1
            continue

        # 5) conectivo
        if palavra in PALAVRAS_IGNORADAS:
            tokens.append(Token(TipoToken.CONECTIVO, palavra, palavra))
            indice += 1
            continue

        # 6) ação por radical — depois de tudo, para uma palavra ignorada
        #    ("pedido") ou um produto nunca ser confundido com verbo
        acao = acao_por_radical(palavra)
        if acao:
            tokens.append(Token(TipoToken.ACAO, acao, palavra))
            indice += 1
            continue

        # 7) verbo parecido com algum conhecido (transcrição errada)
        acao = acao_aproximada(palavra)
        if acao:
            tokens.append(Token(TipoToken.ACAO, acao, palavra))
            indice += 1
            continue

        # 8) nada reconhecido
        tokens.append(Token(TipoToken.DESCONHECIDO, palavra, palavra))
        indice += 1

    return tokens
