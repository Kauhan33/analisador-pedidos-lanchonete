"""
Cálculos da animação da interface gráfica, separados do tkinter.

Ficam aqui para poderem ser testados sem abrir janela nenhuma: dado o
volume que chega do microfone, este módulo diz o tamanho de cada barra ao
redor do círculo e o ângulo atual da rotação. A gui.py só desenha.
"""

from __future__ import annotations

import math
from collections import deque

# Volume mínimo considerado "cheio". Serve de piso para a auto-escala: sem
# ele, o silêncio (ruído de fundo baixíssimo) viraria barras no máximo.
REFERENCIA_MINIMA = 500.0

# A referência decai devagar para acompanhar mudanças de microfone e de voz
# sem ficar presa a um pico antigo.
DECAIMENTO_REFERENCIA = 0.995


class MedidorDeNivel:
    """
    Histórico recente do volume do microfone, normalizado entre 0 e 1.

    Cada barra desenhada ao redor do círculo mostra um instante diferente
    desse histórico, então o anel de barras é, literalmente, a forma de onda
    do que o microfone captou nos últimos instantes — e não uma animação
    aleatória.
    """

    def __init__(self, quantidade_barras: int = 48) -> None:
        self._historico: deque[float] = deque(
            [0.0] * quantidade_barras, maxlen=quantidade_barras
        )
        self._referencia = REFERENCIA_MINIMA

    def registrar(self, volume: float) -> None:
        """Guarda um volume vindo do microfone (RMS, escala do PCM 16 bits)."""
        volume = max(0.0, volume)
        # auto-escala: acompanha o pico recente, respeitando um piso
        self._referencia = max(
            self._referencia * DECAIMENTO_REFERENCIA, volume, REFERENCIA_MINIMA
        )
        self._historico.append(min(1.0, volume / self._referencia))

    def registrar_silencio(self) -> None:
        """Usado quando não há captura: o anel volta ao repouso."""
        self._historico.append(0.0)
        self._referencia = max(self._referencia * DECAIMENTO_REFERENCIA, REFERENCIA_MINIMA)

    def niveis(self) -> list[float]:
        return list(self._historico)

    def nivel_atual(self) -> float:
        return self._historico[-1]

    def em_silencio(self, limiar: float = 0.08) -> bool:
        """True quando nem o instante atual nem os anteriores têm som — é o
        que decide se as barras estão "paradas"."""
        return max(self._historico) <= limiar


class AnimacaoCircular:
    """Estado da animação: a rotação constante do círculo e a geometria das
    barras ao redor dele."""

    def __init__(
        self,
        quantidade_barras: int = 48,
        raio_circulo: float = 70.0,
        folga: float = 14.0,
        comprimento_minimo: float = 6.0,
        comprimento_maximo: float = 56.0,
        # ~0,6 grau por quadro a 30 quadros/s dá uma volta completa a cada
        # 20 segundos: o giro fica perceptível, mas calmo
        graus_por_quadro: float = 0.6,
    ) -> None:
        self.quantidade_barras = quantidade_barras
        self.raio_circulo = raio_circulo
        self.folga = folga
        self.comprimento_minimo = comprimento_minimo
        self.comprimento_maximo = comprimento_maximo
        self.graus_por_quadro = graus_por_quadro
        self.angulo = 0.0

    def avancar(self, quadros: float = 1.0) -> float:
        """Gira o círculo. Ele gira sempre — inclusive sem captura de áudio,
        quando é a única coisa em movimento."""
        self.angulo = (self.angulo + self.graus_por_quadro * quadros) % 360.0
        return self.angulo

    def comprimento_da_barra(self, nivel: float) -> float:
        nivel = min(1.0, max(0.0, nivel))
        extra = (self.comprimento_maximo - self.comprimento_minimo) * nivel
        return self.comprimento_minimo + extra

    def posicoes_das_barras(
        self, centro_x: float, centro_y: float, niveis: list[float]
    ) -> list[tuple[float, float, float, float]]:
        """Coordenadas (x1, y1, x2, y2) de cada barra radial ao redor do
        círculo, já giradas pelo ângulo atual."""
        posicoes = []
        total = max(1, len(niveis))
        inicio = self.raio_circulo + self.folga

        for indice, nivel in enumerate(niveis):
            graus = self.angulo + (360.0 * indice / total)
            radianos = math.radians(graus)
            cosseno, seno = math.cos(radianos), math.sin(radianos)
            fim = inicio + self.comprimento_da_barra(nivel)
            posicoes.append(
                (
                    centro_x + cosseno * inicio,
                    centro_y + seno * inicio,
                    centro_x + cosseno * fim,
                    centro_y + seno * fim,
                )
            )
        return posicoes


def _para_rgb(cor: str) -> tuple[int, int, int]:
    return (int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16))


def gerar_disco_ppm(
    lado: int,
    raio: float,
    cor_centro: str,
    cor_borda: str,
    cor_fundo: str,
    amostras: int = 4,
) -> bytes:
    """
    Desenha um disco com gradiente radial e **borda suavizada**, devolvendo
    a imagem no formato PPM (P6) — que o tkinter carrega direto com
    `tk.PhotoImage(data=...)`, sem precisar de Pillow.

    O Canvas do tkinter não faz antialiasing: um `create_oval` grande fica
    com a borda visivelmente serrilhada, e empilhar círculos de cores
    intermediárias não resolve (cada um deles também é serrilhado). Aqui a
    suavização é calculada de verdade: os pixels da borda recebem a
    proporção exata da área coberta pelo círculo, medida por amostragem em
    uma grade de `amostras` x `amostras` dentro de cada pixel.

    Só a faixa próxima à borda é amostrada assim — o interior e o exterior
    são resolvidos direto, o que mantém a geração na casa dos milissegundos.
    """
    centro = lado / 2.0
    rgb_centro = _para_rgb(cor_centro)
    rgb_borda = _para_rgb(cor_borda)
    rgb_fundo = _para_rgb(cor_fundo)

    passo = 1.0 / amostras
    deslocamentos = [(indice + 0.5) * passo for indice in range(amostras)]
    total_amostras = amostras * amostras
    raio2 = raio * raio

    pixels = bytearray()
    for y in range(lado):
        dy = y + 0.5 - centro
        for x in range(lado):
            dx = x + 0.5 - centro
            distancia = math.hypot(dx, dy)

            # cobertura: 1 dentro, 0 fora, fração exata na borda
            if distancia <= raio - 1.0:
                cobertura = 1.0
            elif distancia >= raio + 1.0:
                cobertura = 0.0
            else:
                dentro = 0
                for desloc_y in deslocamentos:
                    amostra_y = y + desloc_y - centro
                    for desloc_x in deslocamentos:
                        amostra_x = x + desloc_x - centro
                        if amostra_x * amostra_x + amostra_y * amostra_y <= raio2:
                            dentro += 1
                cobertura = dentro / total_amostras

            if cobertura == 0.0:
                pixels.extend(rgb_fundo)
                continue

            # gradiente radial: mais claro no centro, mais escuro na borda
            proporcao = min(1.0, distancia / raio) if raio else 0.0
            for canal in range(3):
                cor_disco = rgb_centro[canal] + (rgb_borda[canal] - rgb_centro[canal]) * proporcao
                valor = rgb_fundo[canal] + (cor_disco - rgb_fundo[canal]) * cobertura
                pixels.append(max(0, min(255, round(valor))))

    cabecalho = b"P6\n%d %d\n255\n" % (lado, lado)
    return cabecalho + bytes(pixels)


def misturar_cores(cor_inicial: str, cor_final: str, proporcao: float) -> str:
    """Interpola duas cores "#rrggbb" — usado para as barras ficarem mais
    quentes conforme o volume sobe."""
    proporcao = min(1.0, max(0.0, proporcao))
    inicio = [int(cor_inicial[i : i + 2], 16) for i in (1, 3, 5)]
    fim = [int(cor_final[i : i + 2], 16) for i in (1, 3, 5)]
    canais = [round(a + (b - a) * proporcao) for a, b in zip(inicio, fim)]
    return "#{:02x}{:02x}{:02x}".format(*canais)
