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
from difflib import SequenceMatcher

import cardapio
from cardapio import nome_exibicao, preco
from lexer import ACOES, Token, TipoToken, candidatos_singular

QUANTIDADE_MAXIMA = 99

# Similaridade a partir da qual um erro de digitação é corrigido sozinho,
# com aviso ("amburguers" -> Hambúrguer). Abaixo disso, até o limiar do
# cardápio, vira pergunta: "você quis dizer X?", que "sim" confirma.
LIMIAR_AUTOCORRECAO = 0.85


@dataclass
class ItemPedido:
    """Uma dupla quantidade/produto já associada pela análise semântica.

    `especial` guarda quantidades que ainda não são um número ("todas",
    "metade"): elas só viram número diante do carrinho, em _expandir().
    `produto` pode ser "*" (todos), pelo mesmo motivo.
    """

    quantidade: int
    produto: str
    especial: str | None = None

    def descrever(self) -> str:
        return f"{self.quantidade}x {nome_exibicao(self.produto)}"

    def subtotal(self) -> float:
        return preco(self.produto) * self.quantidade


@dataclass
class Pendencia:
    """Uma sugestão que ficou esperando "sim" ou "não" do cliente."""

    acao: str
    itens: list[ItemPedido]


@dataclass
class Pedido:
    itens: dict[str, int] = field(default_factory=dict)
    # sugestão aguardando confirmação (ver interpretar); qualquer outra frase
    # do cliente a descarta
    pendencia: Pendencia | None = None

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

    especial_pendente: str | None = None

    for token in tokens:
        if token.tipo == TipoToken.QUANTIDADE:
            if token.valor.isdigit():
                quantidade_pendente, especial_pendente = int(token.valor), None
            else:
                quantidade_pendente, especial_pendente = None, token.valor
        elif token.tipo == TipoToken.PRODUTO:
            # comparar com None em vez de usar "or 1": a quantidade zero é
            # um valor legítimo aqui, e precisa chegar à validação para ser
            # recusada — "or 1" a transformaria silenciosamente em 1
            quantidade = 1 if quantidade_pendente is None else quantidade_pendente
            itens.append(ItemPedido(quantidade, token.valor, especial_pendente))
            quantidade_pendente = especial_pendente = None  # valem para um produto só

    return _consolidar(itens)


def _consolidar(itens: list[ItemPedido]) -> list[ItemPedido]:
    """Junta repetições do mesmo produto na frase.

    O cliente pode chamar o mesmo item por nomes diferentes ("2 refri e uma
    coca"): são 3 refrigerantes, e a resposta deve dizer isso, em vez de
    listar o mesmo produto duas vezes."""
    agrupados: dict[str, ItemPedido] = {}
    for item in itens:
        if item.produto in agrupados:
            agrupados[item.produto].quantidade += item.quantidade
            agrupados[item.produto].especial = item.especial or agrupados[item.produto].especial
        else:
            agrupados[item.produto] = ItemPedido(item.quantidade, item.produto, item.especial)
    return list(agrupados.values())


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
    # (ação, explicação, verbos em destaque, exemplo). Os verbos em destaque
    # são os que um cliente realmente usa; a lista completa vive no lexer e
    # cada um deles é conferido contra ela, para a ajuda nunca prometer um
    # verbo que o programa não entende.
    descricoes = [
        ("ADICIONAR", "põe itens no pedido", ["pedir", "quero", "adicione", "ve"],
         "quero 2 hambúrgueres e 1 refri"),
        ("REMOVER", "tira itens do pedido", ["remover", "remova", "tire", "retire"],
         "remova 1 refri / tire todas as águas"),
        ("MOSTRAR", "mostra o pedido atual", ["mostrar", "ver", "listar"],
         "mostrar pedido"),
        ("CARDAPIO", "lista produtos e preços", ["cardapio", "menu", "preco"],
         "cardápio / quanto custa a pizza"),
        ("FINALIZAR", "fecha a conta", ["finalizar", "fechar", "pagar"],
         "fechar a conta"),
        ("CANCELAR", "esvazia o pedido", ["cancelar", "limpar"],
         "cancelar / limpar tudo"),
        ("AJUDA", "esta lista", ["ajuda", "comandos"], "ajuda"),
    ]
    for acao, explicacao, destaque, exemplo in descricoes:
        conhecidos = set(_palavras_da_acao(acao))
        verbos = [v for v in destaque if v in conhecidos]
        restantes = len(conhecidos) - len(verbos)
        resumo = "/".join(verbos) + (f" (+{restantes} formas)" if restantes else "")
        linhas.append(f"  {explicacao}")
        linhas.append(f"      verbos:  {resumo}")
        linhas.append(f"      ex.:     {exemplo}")

    linhas.append("")
    linhas.append("Também entendo:")
    linhas.append("  - só os itens, sem verbo: '2 hambúrgueres e um suco'")
    linhas.append("  - plural e quantidade por extenso: 'duas águas', 'três sucos'")
    linhas.append("  - 'todas', 'metade' e 'um de cada': 'tire todas as águas', 'um de cada'")
    linhas.append("  - negação: 'não vou querer o refri' = remover")
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


def _melhor_sugestao(palavra: str) -> tuple[str | None, float]:
    """Produto mais parecido com `palavra` (tentando também o singular dela)
    e a nota dessa semelhança."""
    melhor, melhor_nota = None, 0.0
    for forma in candidatos_singular(palavra):
        for produto in cardapio.PRODUTOS:
            for sinonimo in produto.sinonimos:
                nota = SequenceMatcher(None, forma, sinonimo).ratio()
                if nota > melhor_nota:
                    melhor, melhor_nota = produto.codigo, nota
    if melhor_nota < cardapio.LIMIAR_SUGESTAO:
        return None, melhor_nota
    return melhor, melhor_nota


def _resposta_para_desconhecidos(desconhecidos: list[Token]) -> str:
    """Recusa de palavras fora do cardápio, sugerindo o produto parecido
    quando existe algum."""
    partes = []
    for token in desconhecidos:
        sugestao, _ = _melhor_sugestao(token.lexema)
        if sugestao:
            partes.append(f"'{token.lexema}' (você quis dizer {nome_exibicao(sugestao)}?)")
        else:
            partes.append(f"'{token.lexema}'")
    return f"Não temos {_juntar(partes)} no cardápio."


def _acao_da_frase(tokens: list[Token]) -> str | None:
    """
    Decide a ação da frase a partir dos verbos, aplicando a negação.

    "Não vou querer o refri" tem NEGAR + ADICIONAR — e quer dizer REMOVER.
    A negação inverte o verbo de pedir; sobre os outros ("não cancela") não
    há inversão útil, então ela é só ignorada.
    """
    acoes = list(dict.fromkeys(t.valor for t in tokens if t.tipo == TipoToken.ACAO))
    negado = "NEGAR" in acoes
    acoes = [a for a in acoes if a not in ("NEGAR", "CONFIRMAR")]

    if negado and acoes == ["ADICIONAR"]:
        return "REMOVER"
    if len(acoes) > 1:
        return "CONFLITO"
    return acoes[0] if acoes else None


def _palavra_estranha_no_lugar_do_verbo(tokens: list[Token], estranhas: list[Token]) -> Token | None:
    """Uma palavra sem significado nenhum ANTES do primeiro produto (ou do
    primeiro produto provável) está na posição do verbo — "apague os
    refris". Nesse caso não dá para assumir que o cliente quer pedir. Só as
    palavras de `estranhas` contam: as parecidas com produto são produto."""
    estranhas_ids = {id(t) for t in estranhas}
    for token in tokens:
        if token.tipo == TipoToken.DESCONHECIDO and id(token) in estranhas_ids:
            return token
        if token.tipo == TipoToken.PRODUTO or token.tipo == TipoToken.DESCONHECIDO:
            return None  # chegou a um produto (conhecido ou provável)
    return None


def interpretar(tokens: list[Token], pedido: Pedido) -> str:
    """Fase de análise semântica: valida o significado do pedido e executa
    a ação correspondente sobre o carrinho."""

    desconhecidos = [t for t in tokens if t.tipo == TipoToken.DESCONHECIDO]
    itens = associar_itens(tokens)
    acao = _acao_da_frase(tokens)
    so_confirmacao = {t.valor for t in tokens if t.tipo == TipoToken.ACAO} & {"CONFIRMAR", "NEGAR"}

    # resposta a uma sugestão pendente ("você quis dizer Hambúrguer?")
    if pedido.pendencia and acao is None and not itens and so_confirmacao:
        pendencia, pedido.pendencia = pedido.pendencia, None
        if "CONFIRMAR" in so_confirmacao:
            return _executar(pendencia.acao, pendencia.itens, pedido)
        return "Ok, deixa pra lá."
    pedido.pendencia = None  # qualquer outra frase descarta a sugestão

    if acao == "CONFLITO":
        return "Entendi mais de um comando na mesma frase. Faça um de cada vez."

    # Palavras fora do cardápio, mas parecidas com algum produto: as muito
    # parecidas ("amburguers") são corrigidas na hora, com aviso; as
    # parecidas só até certo ponto viram pergunta, guardada como pendência
    # para o "sim" do cliente executar. As sem semelhança nenhuma sobram.
    corrigidos, duvidosos, sem_sugestao = _classificar_desconhecidos(tokens, desconhecidos)
    ha_produto_provavel = bool(itens or corrigidos or duvidosos)

    if acao is None:
        verbo_estranho = _palavra_estranha_no_lugar_do_verbo(tokens, sem_sugestao)
        if ha_produto_provavel and verbo_estranho is None:
            # só os itens, sem verbo ("2 hambúrgueres e um suco"): num balcão,
            # isso é um pedido — ADICIONAR é a ação implícita. Mas só quando
            # nenhuma palavra estranha ocupa o lugar do verbo: "apague os
            # refris" não pode virar "adicionar refris".
            acao = "ADICIONAR"
        elif ha_produto_provavel:
            return (
                f"Não conheço o comando '{verbo_estranho.lexema}'. Para pedir, diga "
                "'quero' ou só os itens; para tirar, 'remover'. Diga 'ajuda' para ver todos."
            )
        elif so_confirmacao:
            return "Não há nada para confirmar no momento."
        else:
            return _resposta_para_frase_sem_pedido(tokens, desconhecidos)

    if acao == "AJUDA":
        return montar_ajuda()

    if acao == "CARDAPIO":
        # com produto na frase ("quanto custa o hambúrguer"), responde só o
        # preço dele; sem produto, mostra o cardápio inteiro
        if itens:
            precos = [
                f"{nome_exibicao(item.produto)} custa R$ {preco(item.produto):.2f}"
                for item in itens
            ]
            return _juntar(precos) + "."
        return cardapio.listar()

    # "tire tudo" / "remova tudo": REMOVER com "todas" e sem produto é o
    # mesmo que esvaziar o pedido
    if acao == "REMOVER" and not itens and any(
        t.tipo == TipoToken.QUANTIDADE and t.valor == "todas" for t in tokens
    ):
        acao = "CANCELAR"

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

    itens = _consolidar(itens + [item for _, item in corrigidos])

    if not itens and not duvidosos:
        if sem_sugestao:
            return _resposta_para_desconhecidos(sem_sugestao)
        return "Não entendi qual produto você quer. Diga 'cardápio' para ver as opções."

    if duvidosos:
        pedido.pendencia = Pendencia(acao, _consolidar(itens + [item for _, item in duvidosos]))
        perguntas = _juntar(
            [f"'{lexema}' (você quis dizer {nome_exibicao(item.produto)}?)"
             for lexema, item in duvidosos]
        )
        return f"Não temos {perguntas} no cardápio. Responda 'sim' para confirmar."

    resposta = _executar(acao, itens, pedido)

    avisos = [f"entendi '{lexema}' como {nome_exibicao(item.produto)}" for lexema, item in corrigidos]
    if sem_sugestao:
        # o pedido foi atendido; o que sobrou é só palavra não reconhecida
        # ("pra viagem"), não um produto recusado
        avisos.append("não reconheci " + _juntar([f"'{t.lexema}'" for t in sem_sugestao]))
    if avisos:
        resposta += " (" + "; ".join(avisos) + ")"
    return resposta


def _classificar_desconhecidos(
    tokens: list[Token], desconhecidos: list[Token]
) -> tuple[list[tuple[str, ItemPedido]], list[tuple[str, ItemPedido]], list[Token]]:
    """Separa as palavras desconhecidas em: corrigidas sozinhas (nota alta),
    duvidosas (nota média, pedem confirmação) e sem sugestão nenhuma. Para
    as duas primeiras, devolve o lexema original junto de um ItemPedido com
    a quantidade que veio antes da palavra na frase."""
    corrigidos: list[tuple[str, ItemPedido]] = []
    duvidosos: list[tuple[str, ItemPedido]] = []
    sem_sugestao: list[Token] = []

    for token in desconhecidos:
        sugestao, nota = _melhor_sugestao(token.lexema)
        if sugestao is None:
            sem_sugestao.append(token)
            continue
        item = ItemPedido(_quantidade_antes_de(tokens, token), sugestao)
        if nota >= LIMIAR_AUTOCORRECAO:
            corrigidos.append((token.lexema, item))
        else:
            duvidosos.append((token.lexema, item))

    return corrigidos, duvidosos, sem_sugestao


def _quantidade_antes_de(tokens: list[Token], alvo: Token) -> int:
    """Quantidade dita imediatamente antes de `alvo` (ignorando conectivos),
    ou 1 — a mesma regra de associação usada para os produtos conhecidos."""
    quantidade = 1
    for token in tokens:
        if token is alvo:
            return quantidade
        if token.tipo == TipoToken.QUANTIDADE:
            quantidade = int(token.valor)
        elif token.tipo in (TipoToken.PRODUTO, TipoToken.DESCONHECIDO):
            quantidade = 1  # a quantidade valeu para esse produto, não para o próximo
    return quantidade


def _expandir(acao: str, itens: list[ItemPedido], pedido: Pedido) -> list[ItemPedido] | str:
    """
    Resolve o que só faz sentido diante do carrinho ou do cardápio:

    - produto "*" ("um de cada"): ao pedir, vira um item por produto do
      cardápio; ao remover, um item por produto que está no carrinho;
    - "todas": ao remover, a quantidade que há no carrinho;
    - "metade": ao remover, metade do que há (no mínimo 1).

    Devolve a lista concreta, ou uma mensagem de erro quando a frase não tem
    resolução ("adicionar todas as águas" — todas quantas?).
    """
    concretos: list[ItemPedido] = []

    for item in itens:
        if item.produto == "*":
            if acao == "ADICIONAR":
                alvos = [p.codigo for p in cardapio.PRODUTOS]
            else:
                alvos = list(pedido.itens)
                if not alvos:
                    return "Seu pedido está vazio, não há o que remover."
            concretos.extend(ItemPedido(item.quantidade, alvo, item.especial) for alvo in alvos)
        else:
            concretos.append(item)

    resolvidos: list[ItemPedido] = []
    for item in concretos:
        if item.especial is None:
            resolvidos.append(item)
            continue
        if acao != "REMOVER":
            return "Para pedir, diga a quantidade (ex.: '2 águas')."
        no_carrinho = pedido.quantidade_de(item.produto)
        if item.especial == "todas":
            quantidade = no_carrinho or 1  # 0 -> 1, para cair no "você não tem"
        else:  # metade
            quantidade = max(1, no_carrinho // 2) if no_carrinho else 1
        resolvidos.append(ItemPedido(quantidade, item.produto))

    return _consolidar(resolvidos)


def _executar(acao: str, itens: list[ItemPedido], pedido: Pedido) -> str:
    expandidos = _expandir(acao, itens, pedido)
    if isinstance(expandidos, str):
        return expandidos
    itens = expandidos

    invalidas = [item for item in itens if item.quantidade <= 0]
    if invalidas:
        return "Quantidade inválida: informe um número maior que zero."

    # O limite vale para o que o carrinho vai ficar TENDO ao pedir, e não
    # para o número dito na frase — senão "99 sucos" seguido de "mais 1"
    # passa. E vale só ao pedir: remover nunca excede o que existe, então
    # "remova todas" de um item com 100 unidades tem que funcionar.
    if acao == "ADICIONAR":
        for item in itens:
            resultante = pedido.quantidade_de(item.produto) + item.quantidade
            if resultante > QUANTIDADE_MAXIMA:
                atual = pedido.quantidade_de(item.produto)
                detalhe = f" (você já tem {atual})" if atual else ""
                return (
                    f"Quantidade alta demais para {nome_exibicao(item.produto)}: "
                    f"o máximo por item é {QUANTIDADE_MAXIMA}{detalhe}."
                )

    if acao == "ADICIONAR":
        return _adicionar(itens, pedido)
    if acao == "REMOVER":
        return _remover(itens, pedido)
    if acao == "CARDAPIO":
        precos = [f"{nome_exibicao(i.produto)} custa R$ {preco(i.produto):.2f}" for i in itens]
        return _juntar(precos) + "."
    return "Comando não implementado."


def _resposta_para_frase_sem_pedido(tokens: list[Token], desconhecidos: list[Token]) -> str:
    """Frase sem verbo e sem produto. Se alguma palavra parece um produto
    escrito errado, vale dizer; se é só conversa ("aí é foda"), não faz
    sentido responder "não temos 'foda' no cardápio"."""
    com_sugestao = [t for t in desconhecidos if _melhor_sugestao(t.lexema)[0]]
    if com_sugestao:
        return _resposta_para_desconhecidos(com_sugestao)
    # palavra logo depois de uma quantidade está no lugar de um produto:
    # "2 lasanhas" merece "não temos lasanhas"
    apos_quantidade = [
        t for anterior, t in zip(tokens, tokens[1:])
        if t.tipo == TipoToken.DESCONHECIDO and anterior.tipo == TipoToken.QUANTIDADE
    ]
    if apos_quantidade:
        return _resposta_para_desconhecidos(apos_quantidade)
    return "Não entendi. Diga o que quer pedir (ex.: '2 hambúrgueres'), ou 'cardápio' para ver as opções."


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
