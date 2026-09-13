"""
Interface gráfica do Analisador de Pedidos da Lanchonete.

    python gui.py          (ou: python main.py --gui)

Usa apenas tkinter, da biblioteca padrão — nada a instalar além do que a
voz já pede.

A tela mostra, ao mesmo tempo, as três coisas que importam num balcão:

- o **cardápio**, à esquerda, com os preços sempre à vista;
- o **microfone**, ao centro: um círculo que gira e funciona como botão
  (clicar liga a escuta, clicar de novo desliga), cercado por barras que
  crescem com o volume real captado;
- o **pedido atual** e o total, à direita, atualizados a cada comando.

A análise dos pedidos é exatamente a mesma do modo terminal: esta janela só
troca a forma de entrar com a frase e de mostrar a resposta.

Regras de interação:
- falando, só frases com um verbo de pedido contam ("quero...", "me vê...",
  "adicione...", "remova...") — com o microfone aberto num balcão, quase tudo
  captado é conversa, e o verbo é o que separa pedido de conversa. A
  resposta sai em áudio;
- digitando, basta os itens ("2 hambúrgueres") e a resposta sai só na tela;
- "sair" encerra o programa, falado ou digitado.
"""

from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

import cardapio
from lexer import analisar_lexico, tem_comando_explicito
from semantic import Pedido, interpretar, texto_para_audio
from visual import AnimacaoCircular, MedidorDeNivel, gerar_disco_ppm, misturar_cores
from voice import STT_DISPONIVEL, ErroReconhecimento, OuvidorContinuo, falar

COMANDOS_SAIR = ("sair", "exit", "quit")

INTERVALO_QUADRO_MS = 33

COR_FUNDO = "#1a1410"
COR_PAINEL = "#241c16"
COR_ENTRADA = "#2e241c"
COR_BORDA = "#4a3a2c"
COR_TEXTO = "#f5ead9"
COR_TEXTO_FRACO = "#b09a80"
COR_CIRCULO_PARADO = "#463322"
COR_CIRCULO_PARADO_CLARO = "#5e4630"
COR_CIRCULO_OUVINDO = "#b06a1e"
COR_CIRCULO_OUVINDO_CLARO = "#e09236"
COR_ARCO = "#ffc46b"
COR_BARRA_BAIXA = "#463322"
COR_BARRA_ALTA = "#ffc46b"
COR_DESTAQUE = "#c98b34"

ARCO_GRAUS = 110
ARCO_SEGMENTOS = 40

TEXTO_AJUDA_ENTRADA = "digite um pedido (ex.: 2 hambúrguer e 1 refrigerante)"


class JanelaLanchonete:
    """Janela principal. Toda manipulação de widget acontece na thread do
    tkinter; a escuta do microfone roda em uma thread separada e conversa
    com a interface por uma fila (queue), que é o jeito seguro de fazer
    isso em tkinter."""

    def __init__(self, pedido: Pedido | None = None) -> None:
        self.pedido = pedido or Pedido()
        self.medidor = MedidorDeNivel(quantidade_barras=40)
        self.animacao = AnimacaoCircular(
            quantidade_barras=40, raio_circulo=56, comprimento_maximo=42
        )
        self.eventos: queue.Queue[tuple[str, str]] = queue.Queue()

        self.escutando = threading.Event()
        self._ouvidor: OuvidorContinuo | None = None
        self._trava_pedido = threading.Lock()

        self.raiz = tk.Tk()
        self.raiz.title("Lanchonete — Analisador de Pedidos")
        self.raiz.configure(bg=COR_FUNDO)
        self.raiz.minsize(900, 620)

        self._montar_interface()
        self._atualizar_barras(self.medidor.niveis())
        self._atualizar_pedido()

        self.raiz.protocol("WM_DELETE_WINDOW", self.encerrar)
        self.raiz.after(INTERVALO_QUADRO_MS, self._quadro)
        self.raiz.after(80, self._processar_eventos)

    # ------------------------------------------------------------------
    # Construção da tela
    # ------------------------------------------------------------------

    def _montar_interface(self) -> None:
        self.fonte_titulo = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        self.fonte_normal = tkfont.Font(family="Segoe UI", size=10)
        self.fonte_mono = tkfont.Font(family="Consolas", size=10)
        self.fonte_secao = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        tk.Label(
            self.raiz, text="Lanchonete — Analisador de Pedidos",
            bg=COR_FUNDO, fg=COR_TEXTO, font=self.fonte_titulo,
        ).pack(pady=(14, 0))

        self.rotulo_status = tk.Label(
            self.raiz, text="", bg=COR_FUNDO, fg=COR_TEXTO_FRACO, font=self.fonte_normal
        )
        self.rotulo_status.pack(pady=(2, 6))

        corpo = tk.Frame(self.raiz, bg=COR_FUNDO)
        corpo.pack(fill=tk.BOTH, expand=True, padx=14)

        self._montar_cardapio(corpo)
        self._montar_microfone(corpo)
        self._montar_pedido(corpo)

        self._montar_conversa()
        self._atualizar_visual_do_circulo()

    def _montar_cardapio(self, pai: tk.Frame) -> None:
        coluna = tk.Frame(pai, bg=COR_PAINEL)
        coluna.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))

        tk.Label(
            coluna, text="Cardápio", bg=COR_PAINEL, fg=COR_DESTAQUE, font=self.fonte_secao
        ).pack(anchor="w", padx=14, pady=(12, 6))

        for produto in sorted(cardapio.PRODUTOS, key=lambda p: p.preco):
            linha = tk.Frame(coluna, bg=COR_PAINEL)
            linha.pack(fill=tk.X, padx=14, pady=1)
            tk.Label(
                linha, text=produto.nome, bg=COR_PAINEL, fg=COR_TEXTO, font=self.fonte_normal
            ).pack(side=tk.LEFT)
            tk.Label(
                linha, text=f"R$ {produto.preco:.2f}", bg=COR_PAINEL,
                fg=COR_TEXTO_FRACO, font=self.fonte_normal,
            ).pack(side=tk.RIGHT)

        tk.Label(
            coluna, text="", bg=COR_PAINEL
        ).pack(pady=6)

    def _montar_microfone(self, pai: tk.Frame) -> None:
        coluna = tk.Frame(pai, bg=COR_FUNDO)
        coluna.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            coluna, width=300, height=240, bg=COR_FUNDO, highlightthickness=0
        )
        self.canvas.pack(pady=(6, 0))
        self.canvas.bind("<Button-1>", self._clique_no_canvas)

        self.centro = (150, 120)
        centro_x, centro_y = self.centro
        raio = self.animacao.raio_circulo

        # A ordem de criação é a ordem de empilhamento, e importa: a imagem
        # do círculo é um QUADRADO preenchido com a cor do fundo, cujos
        # cantos alcançam mais longe que a borda circular. Criada depois das
        # barras, cobriria o início delas nas diagonais.
        lado = int(raio * 2) + 8
        self.imagens_circulo = {
            "parado": tk.PhotoImage(
                data=gerar_disco_ppm(lado, raio, COR_CIRCULO_PARADO_CLARO, COR_CIRCULO_PARADO, COR_FUNDO)
            ),
            "ouvindo": tk.PhotoImage(
                data=gerar_disco_ppm(lado, raio, COR_CIRCULO_OUVINDO_CLARO, COR_CIRCULO_OUVINDO, COR_FUNDO)
            ),
        }
        self.item_circulo = self.canvas.create_image(
            centro_x, centro_y, image=self.imagens_circulo["parado"]
        )

        self.itens_barras = [
            self.canvas.create_line(
                centro_x, centro_y, centro_x, centro_y,
                width=4, fill=COR_BARRA_BAIXA, capstyle=tk.ROUND,
            )
            for _ in range(self.animacao.quantidade_barras)
        ]

        self.item_arco = self.canvas.create_line(
            centro_x, centro_y, centro_x, centro_y,
            fill=COR_ARCO, width=4, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True,
        )
        self.item_texto_circulo = self.canvas.create_text(
            centro_x, centro_y, text="", fill=COR_TEXTO,
            font=tkfont.Font(family="Segoe UI", size=10, weight="bold"),
        )

    def _montar_pedido(self, pai: tk.Frame) -> None:
        coluna = tk.Frame(pai, bg=COR_PAINEL)
        coluna.pack(side=tk.LEFT, fill=tk.BOTH, padx=(10, 0))

        tk.Label(
            coluna, text="Pedido atual", bg=COR_PAINEL, fg=COR_DESTAQUE, font=self.fonte_secao
        ).pack(anchor="w", padx=14, pady=(12, 6))

        self.lista_pedido = tk.Text(
            coluna, width=30, height=11, bg=COR_PAINEL, fg=COR_TEXTO,
            font=self.fonte_mono, relief=tk.FLAT, padx=12, wrap=tk.WORD,
        )
        self.lista_pedido.pack(fill=tk.BOTH, expand=True)
        self.lista_pedido.configure(state=tk.DISABLED)

        self.rotulo_total = tk.Label(
            coluna, text="Total: R$ 0,00", bg=COR_PAINEL, fg=COR_DESTAQUE,
            font=tkfont.Font(family="Segoe UI", size=13, weight="bold"),
        )
        self.rotulo_total.pack(anchor="e", padx=14, pady=(4, 12))

    def _montar_conversa(self) -> None:
        painel = tk.Frame(self.raiz, bg=COR_FUNDO)
        painel.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 12))

        self.conversa = tk.Text(
            painel, height=7, bg=COR_PAINEL, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            font=self.fonte_mono, wrap=tk.WORD, relief=tk.FLAT, padx=10, pady=8,
        )
        self.conversa.pack(fill=tk.BOTH, expand=True)
        self.conversa.tag_configure("cliente", foreground="#ffd79a")
        self.conversa.tag_configure("sistema", foreground="#b8e0a0")
        self.conversa.tag_configure("aviso", foreground=COR_TEXTO_FRACO)
        self.conversa.configure(state=tk.DISABLED)

        linha_entrada = tk.Frame(painel, bg=COR_FUNDO)
        linha_entrada.pack(fill=tk.X, pady=(8, 0))

        self.entrada = tk.Entry(
            linha_entrada, bg=COR_ENTRADA, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            font=self.fonte_normal, relief=tk.FLAT, highlightthickness=1,
            highlightbackground=COR_BORDA, highlightcolor=COR_ARCO,
        )
        self.entrada.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7, padx=(0, 8))
        self.entrada.bind("<Return>", lambda _evento: self._enviar_texto())
        self.entrada.focus_set()
        self._preparar_texto_de_ajuda_da_entrada()

        tk.Button(
            linha_entrada, text="Enviar", command=self._enviar_texto,
            bg=COR_CIRCULO_OUVINDO, fg=COR_TEXTO, activebackground=COR_ARCO,
            relief=tk.FLAT, font=self.fonte_normal, padx=16,
        ).pack(side=tk.LEFT)

        self._mostrar_boas_vindas()

    def _preparar_texto_de_ajuda_da_entrada(self) -> None:
        """Texto-fantasma na caixa de digitação, que sai ao clicar nela."""
        self._entrada_com_ajuda = True
        self.entrada.insert(0, TEXTO_AJUDA_ENTRADA)
        self.entrada.configure(fg=COR_TEXTO_FRACO)

        def ao_focar(_evento=None):
            if self._entrada_com_ajuda:
                self.entrada.delete(0, tk.END)
                self.entrada.configure(fg=COR_TEXTO)
                self._entrada_com_ajuda = False

        def ao_desfocar(_evento=None):
            if not self.entrada.get().strip():
                self._entrada_com_ajuda = True
                self.entrada.delete(0, tk.END)
                self.entrada.insert(0, TEXTO_AJUDA_ENTRADA)
                self.entrada.configure(fg=COR_TEXTO_FRACO)

        self.entrada.bind("<FocusIn>", ao_focar)
        self.entrada.bind("<FocusOut>", ao_desfocar)
        self.entrada.bind("<Button-1>", ao_focar, add="+")

    def _mostrar_boas_vindas(self) -> None:
        self._escrever(
            "Digite o pedido (ex.: 2 hambúrguer e 1 refrigerante) ou clique no círculo "
            'para falar. Falando, use um verbo: "quero...", "me vê...", "remova...".',
            "aviso",
        )
        if not STT_DISPONIVEL:
            self._escrever(
                "Reconhecimento de voz não instalado (pip install -r requirements.txt): "
                "a janela funciona normalmente digitando.",
                "aviso",
            )

    # ------------------------------------------------------------------
    # Animação
    # ------------------------------------------------------------------

    def _quadro(self) -> None:
        self.animacao.avancar()
        if not self.escutando.is_set():
            self.medidor.registrar_silencio()

        self._atualizar_barras(self.medidor.niveis())
        self._atualizar_arco()
        self.raiz.after(INTERVALO_QUADRO_MS, self._quadro)

    def _atualizar_arco(self) -> None:
        centro_x, centro_y = self.centro
        raio = self.animacao.raio_circulo - 9
        pontos = []
        for passo in range(ARCO_SEGMENTOS + 1):
            graus = self.animacao.angulo + ARCO_GRAUS * (passo / ARCO_SEGMENTOS)
            radianos = math.radians(graus)
            pontos.extend(
                (centro_x + math.cos(radianos) * raio, centro_y + math.sin(radianos) * raio)
            )
        self.canvas.coords(self.item_arco, *pontos)

    def _atualizar_barras(self, niveis: list[float]) -> None:
        centro_x, centro_y = self.centro
        posicoes = self.animacao.posicoes_das_barras(centro_x, centro_y, niveis)
        ativo = self.escutando.is_set()

        for item, (x1, y1, x2, y2), nivel in zip(self.itens_barras, posicoes, niveis):
            self.canvas.coords(item, x1, y1, x2, y2)
            cor = misturar_cores(COR_BARRA_BAIXA, COR_BARRA_ALTA, nivel) if ativo else COR_BARRA_BAIXA
            self.canvas.itemconfig(item, fill=cor)

    def _atualizar_visual_do_circulo(self) -> None:
        ouvindo = self.escutando.is_set()
        self.canvas.itemconfig(
            self.item_circulo, image=self.imagens_circulo["ouvindo" if ouvindo else "parado"]
        )
        self.canvas.itemconfig(
            self.item_texto_circulo, text="ouvindo" if ouvindo else "clique\npara falar"
        )
        if ouvindo:
            self.rotulo_status.config(text='Microfone ligado — fale com um verbo: "quero dois sucos"')
        elif STT_DISPONIVEL:
            self.rotulo_status.config(text="Microfone desligado — clique no círculo para falar")
        else:
            self.rotulo_status.config(text="Sem reconhecimento de voz: use a caixa de texto")

    # ------------------------------------------------------------------
    # Pedido
    # ------------------------------------------------------------------

    def _atualizar_pedido(self) -> None:
        """Redesenha o painel do pedido a partir do estado atual."""
        self.lista_pedido.configure(state=tk.NORMAL)
        self.lista_pedido.delete("1.0", tk.END)

        if self.pedido.vazio():
            self.lista_pedido.insert(tk.END, "(nenhum item ainda)\n")
        else:
            for produto, quantidade in self.pedido.itens.items():
                nome = cardapio.nome_exibicao(produto)
                subtotal = cardapio.preco(produto) * quantidade
                self.lista_pedido.insert(tk.END, f"{quantidade}x {nome}\n")
                self.lista_pedido.insert(tk.END, f"      R$ {subtotal:.2f}\n")

        self.lista_pedido.configure(state=tk.DISABLED)
        self.rotulo_total.config(text=f"Total: R$ {self.pedido.total():.2f}")

    # ------------------------------------------------------------------
    # Entrada por texto
    # ------------------------------------------------------------------

    def _enviar_texto(self) -> None:
        frase = self.entrada.get()
        if getattr(self, "_entrada_com_ajuda", False):
            frase = frase.replace(TEXTO_AJUDA_ENTRADA, "")
        frase = frase.strip()
        if not frase:
            return
        self.entrada.delete(0, tk.END)
        self._escrever(f"Cliente: {frase}", "cliente")

        if frase.lower() in COMANDOS_SAIR:
            self.encerrar()
            return

        with self._trava_pedido:
            resposta = self._processar(frase)
        self._escrever(f"Sistema: {resposta}", "sistema")  # digitado: sem áudio
        self._atualizar_pedido()

    # ------------------------------------------------------------------
    # Entrada por voz
    # ------------------------------------------------------------------

    def _clique_no_canvas(self, evento) -> None:
        """Só o clique dentro do círculo central alterna a escuta."""
        centro_x, centro_y = self.centro
        distancia = ((evento.x - centro_x) ** 2 + (evento.y - centro_y) ** 2) ** 0.5
        if distancia <= self.animacao.raio_circulo:
            self.alternar_escuta()

    def alternar_escuta(self) -> None:
        if self.escutando.is_set():
            self._parar_escuta()
        else:
            self._iniciar_escuta()

    def _iniciar_escuta(self) -> None:
        if not STT_DISPONIVEL:
            self._escrever(
                "Reconhecimento de voz não está instalado. Rode: pip install -r requirements.txt",
                "aviso",
            )
            return

        self.escutando.set()
        self._atualizar_visual_do_circulo()
        self._escrever("(microfone ligado)", "aviso")
        threading.Thread(target=self._laco_de_escuta, daemon=True).start()

    def _parar_escuta(self) -> None:
        self.escutando.clear()
        self._atualizar_visual_do_circulo()
        self._escrever("(microfone desligado)", "aviso")

    def _laco_de_escuta(self) -> None:
        """Roda fora da thread da interface: abre o microfone e fica ouvindo
        até o círculo ser clicado de novo. Nada aqui toca em widget — tudo
        vai para a fila de eventos."""
        try:
            if self._ouvidor is None:
                self._ouvidor = OuvidorContinuo(ao_medir_nivel=self.medidor.registrar)
        except ErroReconhecimento as erro:
            self.eventos.put(("erro_fatal", str(erro)))
            return

        while self.escutando.is_set():
            try:
                frase = self._ouvidor.ouvir(timeout=3.0)
            except ErroReconhecimento as erro:
                mensagem = str(erro)
                if "Ninguém falou" in mensagem:
                    continue
                if "não consegui entender" in mensagem.lower():
                    # ruído de fundo gera isso em sequência; a interface
                    # colapsa repetições (ver _escrever_sem_repetir)
                    self.eventos.put(("ruido", "(não entendi o que foi falado — pode repetir)"))
                    continue
                self.eventos.put(("aviso", mensagem))
                continue

            if not self.escutando.is_set():
                break

            if frase.strip().lower() in COMANDOS_SAIR:
                self.eventos.put(("sair", ""))
                return

            # Com o microfone aberto, só vira pedido o que tem um verbo de
            # comando ("quero", "me vê", "remova"...). O resto é conversa.
            tokens = analisar_lexico(frase)
            if not tem_comando_explicito(tokens):
                self.eventos.put(("ignorado", frase))
                continue

            self.eventos.put(("voz", frase))
            with self._trava_pedido:
                resposta = interpretar(tokens, self.pedido)
            self.eventos.put(("resposta_falada", resposta))

    def _processar(self, frase: str) -> str:
        return interpretar(analisar_lexico(frase), self.pedido)

    # ------------------------------------------------------------------
    # Ponte entre a thread de áudio e a interface
    # ------------------------------------------------------------------

    def _processar_eventos(self) -> None:
        """Consome a fila preenchida pela thread de áudio. Só aqui os
        widgets são alterados, sempre na thread do tkinter."""
        try:
            while True:
                tipo, conteudo = self.eventos.get_nowait()

                if tipo == "voz":
                    self._escrever(f"Cliente (voz): {conteudo}", "cliente")
                elif tipo == "ignorado":
                    self._escrever(
                        f"Cliente (voz): {conteudo}  (ignorado: sem verbo de pedido)", "aviso"
                    )
                elif tipo == "aviso":
                    self._escrever(conteudo, "aviso")
                elif tipo == "ruido":
                    self._escrever_sem_repetir(conteudo, "aviso")
                elif tipo == "resposta_falada":
                    self._escrever(f"Sistema: {conteudo}", "sistema")
                    self._atualizar_pedido()
                    # falar bloqueia alguns segundos: em outra thread, para
                    # não congelar a animação nem a digitação
                    threading.Thread(
                        target=falar, args=(texto_para_audio(conteudo),), daemon=True
                    ).start()
                elif tipo == "erro_fatal":
                    self.escutando.clear()
                    self._atualizar_visual_do_circulo()
                    self._escrever(conteudo, "aviso")
                elif tipo == "sair":
                    self.encerrar()
                    return
        except queue.Empty:
            pass

        self.raiz.after(80, self._processar_eventos)

    def _escrever(self, texto: str, estilo: str) -> None:
        self.conversa.configure(state=tk.NORMAL)
        self.conversa.insert(tk.END, texto + "\n", estilo)
        self.conversa.see(tk.END)
        self.conversa.configure(state=tk.DISABLED)
        self._ultima_linha = texto

    def _escrever_sem_repetir(self, texto: str, estilo: str) -> None:
        """Escreve só se a linha anterior não for igual — evita o histórico
        encher de "(não entendi...)" quando o microfone capta ruído
        contínuo."""
        if getattr(self, "_ultima_linha", None) != texto:
            self._escrever(texto, estilo)

    # ------------------------------------------------------------------
    # Encerramento
    # ------------------------------------------------------------------

    def encerrar(self) -> None:
        self.escutando.clear()
        try:
            self.raiz.destroy()
        except tk.TclError:
            pass

    def executar(self) -> None:
        self.raiz.mainloop()


def main() -> None:
    JanelaLanchonete().executar()


if __name__ == "__main__":
    main()
