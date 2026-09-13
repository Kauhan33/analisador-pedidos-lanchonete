"""Testes de linguagem natural: frases como um cliente de verdade fala.

Nasceu de uma rodada de testes reais em que várias frases comuns de balcão
falhavam — plural ("hamburguers"), pedido sem verbo ("2 hambúrgueres e um
suco"), dois verbos da mesma ação ("quero pedir"), conjugações ("fecha a
conta") e coloquialismos ("me vê"). Cada caso abaixo é uma dessas frases.

Rodar com:  python -m unittest test_linguagem_natural.py -v
"""

import unittest

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
