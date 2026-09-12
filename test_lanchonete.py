"""Testes automatizados do Analisador de Pedidos da Lanchonete.

Rodar com:  python -m unittest test_lanchonete.py -v
"""

import unittest

from lexer import TipoToken, analisar_lexico
from semantic import Pedido, interpretar


class TestLexer(unittest.TestCase):
    def test_reconhece_acao_produto(self):
        tokens = analisar_lexico("Pedir Hamburguer")
        tipos = [t.tipo for t in tokens]
        self.assertIn(TipoToken.ACAO, tipos)
        self.assertIn(TipoToken.PRODUTO, tipos)

    def test_reconhece_produto_composto(self):
        tokens = analisar_lexico("Pedir batata frita")
        produtos = [t.valor for t in tokens if t.tipo == TipoToken.PRODUTO]
        self.assertEqual(produtos, ["batata_frita"])

    def test_reconhece_quantidade_numero_e_extenso(self):
        tokens_num = analisar_lexico("Pedir 3 refrigerante")
        tokens_ext = analisar_lexico("Pedir tres refrigerante")
        qtd_num = [t.valor for t in tokens_num if t.tipo == TipoToken.QUANTIDADE]
        qtd_ext = [t.valor for t in tokens_ext if t.tipo == TipoToken.QUANTIDADE]
        self.assertEqual(qtd_num, ["3"])
        self.assertEqual(qtd_ext, ["3"])

    def test_palavra_desconhecida(self):
        tokens = analisar_lexico("Pedir lasanha")
        desconhecidos = [t.lexema for t in tokens if t.tipo == TipoToken.DESCONHECIDO]
        self.assertIn("lasanha", desconhecidos)


class TestSemantic(unittest.TestCase):
    def setUp(self) -> None:
        self.pedido = Pedido()

    def test_adicionar_item(self):
        resposta = interpretar(analisar_lexico("Pedir Hamburguer"), self.pedido)
        self.assertIn("adicionado", resposta.lower())
        self.assertEqual(self.pedido.itens.get("hamburguer"), 1)

    def test_adicionar_com_quantidade(self):
        interpretar(analisar_lexico("Pedir 2 Refrigerante"), self.pedido)
        self.assertEqual(self.pedido.itens.get("refrigerante"), 2)

    def test_remover_item_existente(self):
        interpretar(analisar_lexico("Pedir Refrigerante"), self.pedido)
        resposta = interpretar(analisar_lexico("Remover Refrigerante"), self.pedido)
        self.assertIn("removido", resposta.lower())
        self.assertNotIn("refrigerante", self.pedido.itens)

    def test_remover_item_inexistente_gera_erro(self):
        resposta = interpretar(analisar_lexico("Remover suco"), self.pedido)
        self.assertIn("não tem", resposta.lower())

    def test_produto_nao_reconhecido(self):
        resposta = interpretar(analisar_lexico("Pedir lasanha"), self.pedido)
        self.assertIn("não reconheço", resposta.lower())

    def test_finalizar_calcula_total_e_limpa_pedido(self):
        interpretar(analisar_lexico("Pedir 2 Hamburguer"), self.pedido)
        resposta = interpretar(analisar_lexico("Finalizar pedido"), self.pedido)
        self.assertIn("36.00", resposta)
        self.assertTrue(self.pedido.vazio())


if __name__ == "__main__":
    unittest.main()
