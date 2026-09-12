"""Testes da palavra-chave, da voz e da interface gráfica.

Nenhum deles usa microfone, alto-falante ou internet: as bibliotecas
externas são sempre substituídas por dublês. Os testes da janela são
pulados automaticamente onde não há tkinter ou display — a interface é
opcional, e o resto do programa não depende dela.

Rodar com:  python -m unittest test_voz_e_interface.py -v
"""

import unittest
from unittest.mock import MagicMock, patch

import voice
from semantic import Pedido
from visual import AnimacaoCircular, MedidorDeNivel, gerar_disco_ppm
from wakeword import extrair_comando, parece_palavra_chave

try:
    import tkinter as tk

    _raiz_teste = tk.Tk()
    _raiz_teste.destroy()
    TEM_JANELA = True
except Exception:  # sem tkinter ou sem display
    TEM_JANELA = False


class TestPalavraChave(unittest.TestCase):
    def test_pedido_com_palavra_chave(self):
        self.assertEqual(
            extrair_comando("Atendente, pedir dois hambúrgueres"),
            "pedir dois hambúrgueres",
        )

    def test_sem_virgula(self):
        self.assertEqual(extrair_comando("Atendente cardápio"), "cardápio")

    def test_variacoes_mal_transcritas(self):
        for frase in ("Atendent pedir suco", "Atendendo pedir suco", "atendentes pedir suco"):
            with self.subTest(frase=frase):
                self.assertEqual(extrair_comando(frase), "pedir suco")

    def test_nome_quebrado_em_duas_palavras(self):
        self.assertEqual(extrair_comando("A tendente pedir suco"), "pedir suco")

    def test_conversa_sem_palavra_chave_e_ignorada(self):
        for frase in ("o hambúrguer daqui é bom", "pedir 2 hambúrguer", "acho caro"):
            with self.subTest(frase=frase):
                self.assertIsNone(extrair_comando(frase))

    def test_vocabulario_da_lanchonete_nao_vira_palavra_chave(self):
        """O limiar precisa separar o nome do sistema das palavras do
        próprio domínio, senão qualquer pedido viraria ativação."""
        for palavra in ("pedir", "remover", "hamburguer", "refrigerante",
                        "cardapio", "finalizar", "cancelar", "batata"):
            with self.subTest(palavra=palavra):
                self.assertFalse(parece_palavra_chave(palavra))

    def test_so_a_palavra_chave_devolve_vazio(self):
        self.assertEqual(extrair_comando("Atendente"), "")

    def test_nao_engole_quantidade_curta_depois_do_nome(self):
        """"2" é curto, mas significa algo — não pode ser confundido com
        resto de uma transcrição errada do nome."""
        self.assertEqual(extrair_comando("Atendente 2 sucos"), "2 sucos")


class TestSintese(unittest.TestCase):
    def test_texto_vazio_nao_chama_nenhum_motor(self):
        with patch.object(voice, "_falar_local") as local_mock, \
             patch.object(voice, "_falar_online_pt_br") as online_mock:
            voice.falar("")
            local_mock.assert_not_called()
            online_mock.assert_not_called()

    def test_falha_de_audio_nunca_derruba_o_programa(self):
        with patch.object(voice, "TTS_LOCAL_DISPONIVEL", True), \
             patch.object(voice, "_falar_local", side_effect=RuntimeError("sem áudio")), \
             patch.object(voice, "TTS_ONLINE_DISPONIVEL", True), \
             patch.object(voice, "_falar_online_pt_br", side_effect=OSError("offline")), \
             patch.object(voice, "_aviso_falha_audio_mostrado", False):
            voice.falar("teste")  # não deve levantar exceção

    def test_cada_fala_inicializa_um_motor_novo(self):
        """Regressão herdada da Mini-Alexa: reaproveitar o motor pyttsx3 faz
        só a primeira resposta sair com som."""
        motores = []

        def init_falso(*_a, **_k):
            motor = MagicMock()
            motor.getProperty.return_value = []
            motores.append(motor)
            return motor

        with patch.object(voice, "pyttsx3", MagicMock(init=init_falso)):
            voice._falar_local("primeira", exigir_portugues=False)
            voice._falar_local("segunda", exigir_portugues=False)

        self.assertEqual(len(motores), 2)


class TestAnimacao(unittest.TestCase):
    def test_barras_seguem_o_volume(self):
        medidor = MedidorDeNivel()
        self.assertTrue(medidor.em_silencio())
        medidor.registrar(5000)
        self.assertFalse(medidor.em_silencio())

    def test_circulo_gira(self):
        animacao = AnimacaoCircular()
        antes = animacao.angulo
        animacao.avancar()
        self.assertNotEqual(animacao.angulo, antes)

    def test_disco_tem_borda_suavizada(self):
        dados = gerar_disco_ppm(40, 15.0, "#ffffff", "#ffffff", "#000000")
        corpo = dados[len(b"P6\n40 40\n255\n"):]
        intermediarios = sum(1 for i in range(0, len(corpo), 3) if 20 < corpo[i] < 235)
        self.assertGreater(intermediarios, 10)


@unittest.skipUnless(TEM_JANELA, "tkinter/display não disponível")
class TestJanela(unittest.TestCase):
    def setUp(self) -> None:
        from gui import JanelaLanchonete

        self.janela = JanelaLanchonete()

    def tearDown(self) -> None:
        self.janela.encerrar()

    def _digitar(self, frase: str) -> None:
        self.janela.entrada.delete(0, tk.END)
        self.janela._entrada_com_ajuda = False
        self.janela.entrada.insert(0, frase)
        self.janela._enviar_texto()

    def _conversa(self) -> str:
        return self.janela.conversa.get("1.0", tk.END)

    def _painel_pedido(self) -> str:
        return self.janela.lista_pedido.get("1.0", tk.END)

    def test_pedido_digitado_e_processado(self):
        self._digitar("pedir 2 hamburguer e 1 refrigerante")
        self.assertIn("Adicionado", self._conversa())
        self.assertEqual(self.janela.pedido.itens, {"hamburguer": 2, "refrigerante": 1})

    def test_painel_do_pedido_e_total_sao_atualizados(self):
        self._digitar("pedir 2 hamburguer")
        self.assertIn("2x Hambúrguer", self._painel_pedido())
        self.assertIn("36.00", self.janela.rotulo_total.cget("text"))

    def test_painel_volta_a_vazio_ao_cancelar(self):
        self._digitar("pedir 1 pizza")
        self._digitar("cancelar pedido")
        self.assertIn("nenhum item", self._painel_pedido())
        self.assertIn("0.00", self.janela.rotulo_total.cget("text"))

    def test_pedido_digitado_nao_fala(self):
        with patch("gui.falar") as falar_mock:
            self._digitar("pedir hamburguer")
        falar_mock.assert_not_called()

    def test_texto_fantasma_nao_entra_no_pedido(self):
        from gui import TEXTO_AJUDA_ENTRADA

        self.janela.entrada.delete(0, tk.END)
        self.janela._entrada_com_ajuda = True
        self.janela.entrada.insert(0, "pedir hamburguer" + TEXTO_AJUDA_ENTRADA)
        self.janela._enviar_texto()
        self.assertEqual(self.janela.pedido.itens.get("hamburguer"), 1)

    def test_clique_no_circulo_alterna_a_escuta(self):
        with patch("gui.STT_DISPONIVEL", True), patch("gui.threading.Thread"):
            self.janela.alternar_escuta()
            self.assertTrue(self.janela.escutando.is_set())
            self.janela.alternar_escuta()
            self.assertFalse(self.janela.escutando.is_set())

    def test_clique_fora_do_circulo_nao_liga_o_microfone(self):
        class EventoFalso:
            x, y = 5, 5

        with patch("gui.STT_DISPONIVEL", True), patch("gui.threading.Thread"):
            self.janela._clique_no_canvas(EventoFalso())
        self.assertFalse(self.janela.escutando.is_set())

    def test_sem_reconhecimento_o_clique_avisa(self):
        with patch("gui.STT_DISPONIVEL", False):
            self.janela.alternar_escuta()
        self.assertFalse(self.janela.escutando.is_set())
        self.assertIn("não está instalado", self._conversa())

    def test_fala_sem_palavra_chave_aparece_como_ignorada(self):
        self.janela.eventos.put(("ignorado", "conversa qualquer da mesa ao lado"))
        self.janela._processar_eventos()
        self.assertIn("ignorado: sem a palavra-chave", self._conversa())

    def test_resposta_de_voz_atualiza_o_painel_e_fala_em_outra_thread(self):
        self.janela.eventos.put(("resposta_falada", "Adicionado 1x Pizza ao pedido."))
        with patch("gui.falar") as falar_mock, patch("gui.threading.Thread") as thread_mock:
            self.janela._processar_eventos()
        self.assertIn("Adicionado 1x Pizza", self._conversa())
        thread_mock.assert_called_once()
        falar_mock.assert_not_called()

    def test_sair_digitado_encerra(self):
        with patch.object(self.janela, "encerrar") as encerrar_mock:
            self._digitar("sair")
        encerrar_mock.assert_called_once()

    def test_barras_param_quando_nao_ha_captura(self):
        self.janela.medidor.registrar(5000)
        for _ in range(len(self.janela.medidor.niveis()) + 1):
            self.janela._quadro()
        self.assertTrue(self.janela.medidor.em_silencio())


if __name__ == "__main__":
    unittest.main()
