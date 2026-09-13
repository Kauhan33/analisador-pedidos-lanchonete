"""Testes de linguagem natural: frases como um cliente de verdade fala.

Nasceu de uma rodada de testes reais em que várias frases comuns de balcão
falhavam — plural ("hamburguers"), pedido sem verbo ("2 hambúrgueres e um
suco"), dois verbos da mesma ação ("quero pedir"), conjugações ("fecha a
conta") e coloquialismos ("me vê"). Cada caso abaixo é uma dessas frases.

Rodar com:  python -m unittest test_linguagem_natural.py -v
"""

import unittest

import cardapio
from lexer import TipoToken, analisar_lexico, candidatos_singular
from semantic import Pedido, interpretar


def _produtos(frase: str) -> list[str]:
    return [t.valor for t in analisar_lexico(frase) if t.tipo == TipoToken.PRODUTO]


class TestPlural(unittest.TestCase):
    def test_plural_regular_com_s(self):
        for frase, esperado in [
            ("refrigerantes", "refrigerante"),
            ("sucos", "suco"),
            ("pizzas", "pizza"),
            ("aguas", "agua"),
        ]:
            with self.subTest(frase=frase):
                self.assertEqual(_produtos(frase), [esperado])

    def test_plural_coloquial_e_formal_de_hamburguer(self):
        for frase in ("hamburguers", "hamburgueres", "hambúrgueres", "hambúrguers"):
            with self.subTest(frase=frase):
                self.assertEqual(_produtos(frase), ["hamburguer"])

    def test_plural_em_produto_composto(self):
        self.assertEqual(_produtos("batatas fritas"), ["batata_frita"])
        self.assertEqual(_produtos("cachorros quentes"), ["cachorro_quente"])

    def test_candidatos_singular(self):
        self.assertIn("hamburguer", candidatos_singular("hamburguers"))
        self.assertIn("hamburguer", candidatos_singular("hamburgueres"))
        self.assertIn("porcao", candidatos_singular("porcoes"))
        # a própria palavra vem primeiro: singular já existente casa direto
        self.assertEqual(candidatos_singular("suco")[0], "suco")

    def test_plural_nao_confunde_produtos_diferentes(self):
        """Tirar o "s" não pode transformar um produto em outro."""
        self.assertEqual(_produtos("sucos"), ["suco"])
        self.assertNotIn("sorvete", _produtos("sucos"))


class TestSinonimosComPontuacao(unittest.TestCase):
    def test_hifen_nao_atrapalha(self):
        """Regressão: "x-burguer" virava "x" + "burguer" e o "x" sobrava
        como palavra desconhecida."""
        tokens = analisar_lexico("pedir um x-burguer")
        self.assertEqual([t.valor for t in tokens if t.tipo == TipoToken.PRODUTO], ["hamburguer"])
        self.assertEqual([t for t in tokens if t.tipo == TipoToken.DESCONHECIDO], [])


class TestFrasesDeBalcao(unittest.TestCase):
    """Cada frase precisa ser entendida como um pedido válido, sem sobrar
    nenhuma palavra como "não temos X no cardápio"."""

    FRASES_DE_PEDIDO = [
        ("2 hamburguers e dois refrigerantes", {"hamburguer": 2, "refrigerante": 2}),
        ("duas batatas fritas", {"batata_frita": 2}),
        ("hamburguer", {"hamburguer": 1}),
        ("quero pedir 2 pizzas", {"pizza": 2}),
        ("gostaria de pedir um suco", {"suco": 1}),
        ("eu quero uma batata frita", {"batata_frita": 1}),
        ("me vê dois cachorros quentes", {"cachorro_quente": 2}),
        ("pode adicionar 2 sucos por favor", {"suco": 2}),
        ("vou querer 2 aguas", {"agua": 2}),
        ("quero uma coca e um dogao", {"refrigerante": 1, "cachorro_quente": 1}),
        ("tres sorvetes e uma agua", {"sorvete": 3, "agua": 1}),
        ("bota mais um hamburguer ai", {"hamburguer": 1}),
    ]

    def test_pedidos_em_linguagem_natural(self):
        for frase, esperado in self.FRASES_DE_PEDIDO:
            with self.subTest(frase=frase):
                pedido = Pedido()
                resposta = interpretar(analisar_lexico(frase), pedido)
                self.assertEqual(pedido.itens, esperado)
                self.assertIn("Adicionado", resposta)
                self.assertNotIn("Não temos", resposta)

    def test_pedido_sem_verbo_assume_adicionar(self):
        pedido = Pedido()
        interpretar(analisar_lexico("2 hamburguers e dois refrigerantes"), pedido)
        self.assertEqual(pedido.itens, {"hamburguer": 2, "refrigerante": 2})

    def test_dois_verbos_da_mesma_acao_nao_e_conflito(self):
        pedido = Pedido()
        resposta = interpretar(analisar_lexico("quero pedir 2 pizzas"), pedido)
        self.assertNotIn("mais de um comando", resposta)
        self.assertEqual(pedido.itens, {"pizza": 2})

    def test_verbos_de_acoes_diferentes_continuam_conflito(self):
        resposta = interpretar(analisar_lexico("pedir e remover hamburguer"), Pedido())
        self.assertIn("mais de um comando", resposta)

    def test_conjugacoes(self):
        pedido = Pedido()
        pedido.adicionar("refrigerante", 2)
        self.assertIn("Removido", interpretar(analisar_lexico("tira um refrigerante"), pedido))
        self.assertIn("finalizado", interpretar(analisar_lexico("fecha a conta"), pedido))

    def test_coloquialismos_de_balcao(self):
        for frase in ("me vê um suco", "manda um suco", "bota um suco", "traz um suco"):
            with self.subTest(frase=frase):
                pedido = Pedido()
                interpretar(analisar_lexico(frase), pedido)
                self.assertEqual(pedido.itens, {"suco": 1})


class TestSessaoRealDeUso(unittest.TestCase):
    """Reproduz uma sessão real que expôs vários problemas de uma vez. Cada
    caso abaixo era uma linha errada daquele log."""

    def setUp(self) -> None:
        self.pedido = Pedido()

    def _dizer(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    def test_conjugacao_no_imperativo_formal(self):
        """"adicione" e "remova" não estavam listados; agora entram pelo
        radical do verbo, como qualquer outra conjugação."""
        resposta = self._dizer("adicione dois hamburguers")
        self.assertEqual(self.pedido.itens, {"hamburguer": 2})
        self.assertNotIn("Não temos 'adicione'", resposta)

    def test_remova_remove_e_nao_adiciona(self):
        """O bug mais grave do log: "remova 99 refris" ADICIONAVA 99, porque
        o verbo desconhecido deixava a frase só com itens, e a ação implícita
        (pedir) entrava no lugar."""
        self._dizer("quero 3 refris")
        resposta = self._dizer("remova 2 refris")
        self.assertIn("Removido 2x Refrigerante", resposta)
        self.assertEqual(self.pedido.itens, {"refrigerante": 1})

    def test_outras_formas_de_remover(self):
        for frase in ("retire um refri", "tire um refri", "apague o refri", "exclua um refri"):
            with self.subTest(frase=frase):
                self.pedido.itens = {"refrigerante": 2}
                self._dizer(frase)
                self.assertEqual(self.pedido.itens, {"refrigerante": 1})

    def test_negacao_de_pedir_e_remover(self):
        """"Não vou querer o hambúrguer" / "não quero mais o refri" são
        NEGAR + ADICIONAR — ou seja, remover."""
        self.pedido.itens = {"hamburguer": 1, "refrigerante": 1}
        self._dizer("nao vou querer o hamburguer")
        self._dizer("não quero mais o refri")
        self.assertTrue(self.pedido.vazio())

    def test_verbo_desconhecido_nao_vira_pedido(self):
        """Uma palavra estranha na posição do verbo não pode ser tratada como
        "pedir": é exatamente o que fez "remova" adicionar."""
        resposta = self._dizer("xablau 2 refris")
        self.assertIn("Não conheço o comando 'xablau'", resposta)
        self.assertTrue(self.pedido.vazio())

    def test_erro_de_digitacao_grande_e_corrigido_sozinho(self):
        resposta = self._dizer("2 amburguers")
        self.assertEqual(self.pedido.itens, {"hamburguer": 2})
        self.assertIn("entendi 'amburguers' como Hambúrguer", resposta)

    def test_sugestao_confirmada_com_sim(self):
        """No log, "sim" depois de uma sugestão virou "não temos 'sim'"."""
        resposta = self._dizer("quero 3 sucus")
        self.assertIn("você quis dizer Suco?", resposta)
        self.assertTrue(self.pedido.vazio())

        self._dizer("sim")
        self.assertEqual(self.pedido.itens, {"suco": 3})

    def test_sugestao_negada_com_nao(self):
        self._dizer("quero 3 sucus")
        self.assertIn("deixa pra lá", self._dizer("nao"))
        self.assertTrue(self.pedido.vazio())

    def test_sugestao_e_descartada_por_qualquer_outra_frase(self):
        self._dizer("quero 3 sucus")
        self._dizer("quero um refri")
        self.assertIn("nada para confirmar", self._dizer("sim"))
        self.assertEqual(self.pedido.itens, {"refrigerante": 1})

    def test_sim_sem_sugestao_pendente(self):
        self.assertIn("nada para confirmar", self._dizer("sim"))

    def test_conversa_nao_e_tratada_como_produto(self):
        """"aí é foda" respondia "não temos 'foda' no cardápio", como se o
        cliente tivesse pedido isso."""
        resposta = self._dizer("aí é foda")
        self.assertNotIn("Não temos", resposta)
        self.assertIn("Não entendi", resposta)

    def test_so_pontuacao_nao_vira_palavra_vazia(self):
        """"???????" respondia "não temos '' no cardápio"."""
        resposta = self._dizer("???????")
        self.assertNotIn("''", resposta)
        self.assertIn("Não entendi", resposta)

    def test_palavra_depois_de_quantidade_e_produto_recusado(self):
        """Mas "2 lasanhas" está na forma de um pedido: aí vale dizer que não
        tem."""
        self.assertIn("Não temos 'lasanhas'", self._dizer("2 lasanhas"))

    def test_sobra_de_palavra_nao_e_recusa_de_produto(self):
        resposta = self._dizer("2 refris pra viagem")
        self.assertEqual(self.pedido.itens, {"refrigerante": 2})
        self.assertIn("não reconheci 'viagem'", resposta)
        self.assertNotIn("Não temos", resposta)


class TestQuantidadesEspeciais(unittest.TestCase):
    """"todas", "metade" e "um de cada" não são números: só viram número
    diante do carrinho (ou do cardápio). Vieram de uma sessão real em que
    "remover todas as águas" tirava uma só."""

    def setUp(self) -> None:
        self.pedido = Pedido()

    def _dizer(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    def test_remover_todas(self):
        self._dizer("5 aguas")
        resposta = self._dizer("remover todas as aguas")
        self.assertIn("Removido 5x", resposta)
        self.assertTrue(self.pedido.vazio())

    def test_variacoes_de_todas(self):
        for frase in ("tire todos os sucos", "remova toda a agua", "tira tudo de refri"):
            with self.subTest(frase=frase):
                self.pedido.itens = {"suco": 3, "agua": 2, "refrigerante": 4}
                self._dizer(frase)
                self.assertEqual(len(self.pedido.itens), 2)

    def test_remover_metade(self):
        self._dizer("5 aguas")
        self._dizer("remover metade das aguas")
        self.assertEqual(self.pedido.itens, {"agua": 3})

    def test_metade_de_um_tira_um(self):
        self._dizer("1 agua")
        self._dizer("tire metade das aguas")
        self.assertTrue(self.pedido.vazio())

    def test_todas_de_item_ausente(self):
        self.assertIn("não tem", self._dizer("remover todas as pizzas").lower())

    def test_um_de_cada_adiciona_todo_o_cardapio(self):
        self._dizer("adicione um de cada")
        self.assertEqual(len(self.pedido.itens), len(cardapio.PRODUTOS))
        self.assertTrue(all(qtd == 1 for qtd in self.pedido.itens.values()))

    def test_dois_de_cada(self):
        self._dizer("quero dois de cada")
        self.assertTrue(all(qtd == 2 for qtd in self.pedido.itens.values()))

    def test_remover_um_de_cada_so_mexe_no_que_esta_no_carrinho(self):
        self.pedido.itens = {"pizza": 2, "suco": 1}
        self._dizer("remova um de cada")
        self.assertEqual(self.pedido.itens, {"pizza": 1})

    def test_um_de_cada_com_carrinho_vazio_ao_remover(self):
        self.assertIn("vazio", self._dizer("remova um de cada"))

    def test_tudo_sem_produto_esvazia(self):
        self._dizer("2 pizza e 1 suco")
        self.assertIn("cancelado", self._dizer("tire tudo").lower())
        self.assertTrue(self.pedido.vazio())

    def test_todas_ao_pedir_pede_a_quantidade(self):
        resposta = self._dizer("adicionar todas as aguas")
        self.assertIn("diga a quantidade", resposta)
        self.assertTrue(self.pedido.vazio())


class TestVerbosAproximados(unittest.TestCase):
    """O reconhecimento de fala erra o verbo tanto quanto o produto."""

    def _dizer(self, frase: str, pedido: Pedido) -> str:
        return interpretar(analisar_lexico(frase), pedido)

    def test_verbo_transcrito_errado(self):
        for frase, esperado in [
            ("quiero 2 refris", {"refrigerante": 2}),
            ("adissione uma pizza", {"pizza": 1}),
            ("adicioni um suco", {"suco": 1}),
        ]:
            with self.subTest(frase=frase):
                pedido = Pedido()
                self._dizer(frase, pedido)
                self.assertEqual(pedido.itens, esperado)

    def test_remover_transcrito_errado(self):
        pedido = Pedido()
        pedido.itens = {"pizza": 2}
        self._dizer("remuva a pizza", pedido)
        self.assertEqual(pedido.itens, {"pizza": 1})

    def test_palavra_curta_nao_e_aproximada(self):
        """"jose" não pode virar verbo por parecer com algo."""
        tokens = analisar_lexico("jose 3 saladas")
        self.assertEqual([t.lexema for t in tokens if t.tipo == TipoToken.DESCONHECIDO], ["jose"])


class TestConsultaDePreco(unittest.TestCase):
    def test_preco_de_um_produto(self):
        for frase in ("quanto custa o hamburguer", "qual o valor da pizza", "preco do suco"):
            with self.subTest(frase=frase):
                resposta = interpretar(analisar_lexico(frase), Pedido())
                self.assertIn("custa R$", resposta)
                self.assertNotIn("Cardápio:", resposta)

    def test_preco_de_varios_produtos(self):
        resposta = interpretar(analisar_lexico("quanto custa o hamburguer e a pizza"), Pedido())
        self.assertIn("Hambúrguer custa R$ 18.00", resposta)
        self.assertIn("Pizza custa R$ 35.00", resposta)

    def test_sem_produto_mostra_o_cardapio_inteiro(self):
        resposta = interpretar(analisar_lexico("quais os precos"), Pedido())
        self.assertIn("Cardápio:", resposta)

    def test_consulta_de_preco_nao_adiciona_ao_pedido(self):
        pedido = Pedido()
        interpretar(analisar_lexico("quanto custa o hamburguer"), pedido)
        self.assertTrue(pedido.vazio())


if __name__ == "__main__":
    unittest.main()
