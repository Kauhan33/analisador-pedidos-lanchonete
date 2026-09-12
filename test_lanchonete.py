"""Testes automatizados do Analisador de Pedidos da Lanchonete.

Rodar com:  python -m unittest test_lanchonete.py -v
"""

import unittest

import cardapio
from lexer import TipoToken, analisar_lexico
from semantic import Pedido, associar_itens, interpretar, montar_ajuda


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
        qtd_num = [t.valor for t in analisar_lexico("Pedir 3 refrigerante")
                   if t.tipo == TipoToken.QUANTIDADE]
        qtd_ext = [t.valor for t in analisar_lexico("Pedir tres refrigerante")
                   if t.tipo == TipoToken.QUANTIDADE]
        self.assertEqual(qtd_num, ["3"])
        self.assertEqual(qtd_ext, ["3"])

    def test_palavra_desconhecida(self):
        desconhecidos = [t.lexema for t in analisar_lexico("Pedir lasanha")
                         if t.tipo == TipoToken.DESCONHECIDO]
        self.assertIn("lasanha", desconhecidos)

    def test_apelidos_do_cardapio(self):
        for frase, esperado in [
            ("quero um refri", "refrigerante"),
            ("quero uma coca", "refrigerante"),
            ("quero um hot dog", "cachorro_quente"),
            ("quero fritas", "batata_frita"),
        ]:
            with self.subTest(frase=frase):
                produtos = [t.valor for t in analisar_lexico(frase)
                            if t.tipo == TipoToken.PRODUTO]
                self.assertEqual(produtos, [esperado])


class TestAssociacaoDeItens(unittest.TestCase):
    """A análise semântica precisa descobrir a qual produto cada quantidade
    se refere — a ordem dos tokens é o que diz isso."""

    def _itens(self, frase):
        return [(i.quantidade, i.produto) for i in associar_itens(analisar_lexico(frase))]

    def test_um_item_com_quantidade(self):
        self.assertEqual(self._itens("pedir 2 hamburguer"), [(2, "hamburguer")])

    def test_sem_quantidade_assume_um(self):
        self.assertEqual(self._itens("pedir hamburguer"), [(1, "hamburguer")])

    def test_dois_itens_com_quantidades_diferentes(self):
        self.assertEqual(
            self._itens("pedir 2 hamburguer e 1 refrigerante"),
            [(2, "hamburguer"), (1, "refrigerante")],
        )

    def test_quantidade_nao_vaza_para_o_proximo_produto(self):
        """Em "2 hambúrguer e refrigerante", o 2 vale só para o hambúrguer."""
        self.assertEqual(
            self._itens("pedir 2 hamburguer e refrigerante"),
            [(2, "hamburguer"), (1, "refrigerante")],
        )

    def test_tres_itens(self):
        self.assertEqual(
            self._itens("quero 2 pizza, 3 suco e uma salada"),
            [(2, "pizza"), (3, "suco"), (1, "salada")],
        )

    def test_mesmo_produto_repetido_e_somado(self):
        self.assertEqual(self._itens("pedir 2 refri e uma coca"), [(3, "refrigerante")])


class TestAdicionar(unittest.TestCase):
    def setUp(self) -> None:
        self.pedido = Pedido()

    def _dizer(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    def test_adicionar_item(self):
        resposta = self._dizer("Pedir Hamburguer")
        self.assertIn("Adicionado 1x Hambúrguer", resposta)
        self.assertEqual(self.pedido.itens.get("hamburguer"), 1)

    def test_adicionar_com_quantidade(self):
        self._dizer("Pedir 2 Refrigerante")
        self.assertEqual(self.pedido.itens.get("refrigerante"), 2)

    def test_adicionar_varios_itens_de_uma_vez(self):
        resposta = self._dizer("pedir 2 hamburguer e 1 refrigerante")
        self.assertEqual(self.pedido.itens, {"hamburguer": 2, "refrigerante": 1})
        self.assertIn("2x Hambúrguer e 1x Refrigerante", resposta)
        self.assertIn("42.00", resposta)  # 2*18 + 1*6

    def test_quantidade_zero_e_recusada(self):
        self.assertIn("inválida", self._dizer("pedir 0 hamburguer"))
        self.assertTrue(self.pedido.vazio())

    def test_quantidade_absurda_e_recusada(self):
        self.assertIn("alta demais", self._dizer("pedir 500 hamburguer"))
        self.assertTrue(self.pedido.vazio())


class TestRemover(unittest.TestCase):
    def setUp(self) -> None:
        self.pedido = Pedido()

    def _dizer(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    def test_remover_item_existente(self):
        self._dizer("Pedir Refrigerante")
        resposta = self._dizer("Remover Refrigerante")
        self.assertIn("Removido 1x Refrigerante", resposta)
        self.assertNotIn("refrigerante", self.pedido.itens)

    def test_remover_item_inexistente(self):
        resposta = self._dizer("Remover suco")
        self.assertIn("não tem", resposta.lower())

    def test_remover_mais_do_que_tem_nao_mente(self):
        """Regressão: pedir para remover 5 de um item com 2 no carrinho
        respondia "Removido 5x"."""
        self._dizer("pedir 2 hamburguer")
        resposta = self._dizer("remover 5 hamburguer")
        self.assertIn("Removido 2x Hambúrguer", resposta)
        self.assertIn("você pediu 5", resposta)
        self.assertTrue(self.pedido.vazio())

    def test_remover_parcial(self):
        self._dizer("pedir 5 suco")
        self._dizer("remover 2 suco")
        self.assertEqual(self.pedido.itens.get("suco"), 3)

    def test_remover_varios_itens_de_uma_vez(self):
        self._dizer("pedir 2 hamburguer e 2 refrigerante")
        self._dizer("remover 1 hamburguer e 2 refrigerante")
        self.assertEqual(self.pedido.itens, {"hamburguer": 1})


class TestSugestoes(unittest.TestCase):
    def setUp(self) -> None:
        self.pedido = Pedido()

    def _dizer(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    def test_erro_de_digitacao_gera_sugestao(self):
        resposta = self._dizer("pedir hamburgue")
        self.assertIn("você quis dizer Hambúrguer?", resposta)

    def test_produto_realmente_inexistente_nao_inventa_sugestao(self):
        resposta = self._dizer("pedir lasanha")
        self.assertIn("Não temos", resposta)
        self.assertNotIn("quis dizer", resposta)

    def test_sugestao_direta_do_cardapio(self):
        self.assertEqual(cardapio.sugerir("pizzaa"), "pizza")
        self.assertEqual(cardapio.sugerir("refrigerant"), "refrigerante")
        self.assertIsNone(cardapio.sugerir("computador"))

    def test_item_valido_e_aceito_mesmo_com_palavra_estranha_junto(self):
        resposta = self._dizer("pedir hamburguer com tofu")
        self.assertEqual(self.pedido.itens.get("hamburguer"), 1)
        self.assertIn("tofu", resposta)


class TestConsultas(unittest.TestCase):
    def setUp(self) -> None:
        self.pedido = Pedido()

    def _dizer(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    def test_cardapio_lista_produtos_e_precos(self):
        resposta = self._dizer("cardapio")
        self.assertIn("Hambúrguer", resposta)
        self.assertIn("18.00", resposta)

    def test_variacoes_de_cardapio(self):
        for frase in ("cardapio", "menu", "quais os precos"):
            with self.subTest(frase=frase):
                self.assertIn("Cardápio:", self._dizer(frase))

    def test_ajuda_lista_os_comandos(self):
        resposta = self._dizer("ajuda")
        self.assertEqual(resposta, montar_ajuda())
        for comando in ("pedir", "remover", "cardapio", "finalizar", "cancelar"):
            with self.subTest(comando=comando):
                self.assertIn(comando, resposta)

    def test_mostrar_pedido_vazio(self):
        self.assertIn("vazio", self._dizer("mostrar pedido"))

    def test_consulta_nao_altera_o_pedido(self):
        self._dizer("pedir hamburguer")
        self._dizer("cardapio")
        self._dizer("mostrar pedido")
        self.assertEqual(self.pedido.itens, {"hamburguer": 1})


class TestFecharPedido(unittest.TestCase):
    def setUp(self) -> None:
        self.pedido = Pedido()

    def _dizer(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    def test_finalizar_calcula_total_e_limpa_pedido(self):
        self._dizer("Pedir 2 Hamburguer")
        resposta = self._dizer("Finalizar pedido")
        self.assertIn("36.00", resposta)
        self.assertTrue(self.pedido.vazio())

    def test_finalizar_pedido_vazio(self):
        self.assertIn("vazio", self._dizer("finalizar pedido"))

    def test_cancelar_esvazia(self):
        self._dizer("pedir 3 pizza")
        self.assertIn("cancelado", self._dizer("cancelar pedido").lower())
        self.assertTrue(self.pedido.vazio())

    def test_cancelar_pedido_ja_vazio(self):
        self.assertIn("já está vazio", self._dizer("cancelar pedido"))


class TestCardapioComoFonteUnica(unittest.TestCase):
    def test_todo_produto_tem_preco_e_nome(self):
        for produto in cardapio.PRODUTOS:
            with self.subTest(produto=produto.codigo):
                self.assertGreater(produto.preco, 0)
                self.assertTrue(produto.nome)
                self.assertTrue(produto.sinonimos)

    def test_codigos_nao_se_repetem(self):
        codigos = [p.codigo for p in cardapio.PRODUTOS]
        self.assertEqual(len(codigos), len(set(codigos)))

    def test_sinonimo_nao_pertence_a_dois_produtos(self):
        vistos: dict[str, str] = {}
        for produto in cardapio.PRODUTOS:
            for sinonimo in produto.sinonimos:
                self.assertNotIn(sinonimo, vistos, f"'{sinonimo}' está em dois produtos")
                vistos[sinonimo] = produto.codigo


if __name__ == "__main__":
    unittest.main()
