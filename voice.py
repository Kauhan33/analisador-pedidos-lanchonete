"""
Módulo de voz do Mini-Alexa de Casa Inteligente: reconhecimento (fala -> texto)
e síntese (texto -> fala).

- Reconhecimento: SpeechRecognition + microfone, transcrito via Google Web
  Speech API (pt-BR, não exige chave para uso limitado).
- Síntese: tenta primeiro pyttsx3 (motor de voz do próprio sistema
  operacional — offline, mas só fala em português se o Windows tiver um
  pacote de voz pt-BR instalado). Quando nenhuma voz em português é
  encontrada, cai para gTTS (Google Text-to-Speech, online, sempre em
  pt-BR) — assim a resposta sai em português mesmo em computadores sem
  pacote de voz instalado.

O texto transcrito é devolvido como uma string comum, para ser processado
pelo mesmo pipeline de análise léxica/semântica usado no modo digitado — ou
seja, a voz é só outra forma de "digitar" a frase, e a resposta em áudio é
só outra forma de "imprimir" a resposta.
"""

from __future__ import annotations

import array
import math
import os
import tempfile
import uuid
from typing import Callable

try:
    import speech_recognition as sr
    STT_DISPONIVEL = True
except ImportError:
    sr = None  # type: ignore[assignment]
    STT_DISPONIVEL = False

try:
    import pyttsx3
    TTS_LOCAL_DISPONIVEL = True
except ImportError:
    pyttsx3 = None  # type: ignore[assignment]
    TTS_LOCAL_DISPONIVEL = False

try:
    from gtts import gTTS
    from playsound import playsound
    TTS_ONLINE_DISPONIVEL = True
except ImportError:
    gTTS = None  # type: ignore[assignment]
    playsound = None  # type: ignore[assignment]
    TTS_ONLINE_DISPONIVEL = False


class ErroReconhecimento(Exception):
    """Erro ao tentar ouvir ou transcrever um comando de voz."""


def ouvir_comando(idioma: str = "pt-BR", timeout: float = 5.0, limite_frase: float = 8.0) -> str:
    """
    Grava um único comando pelo microfone padrão (abre, calibra o ruído
    ambiente e escuta) e devolve o texto transcrito. Para escuta repetida
    (vários comandos seguidos), prefira a classe OuvidorContinuo — que
    calibra uma vez só, em vez de recalibrar (e arriscar perder o começo da
    fala) a cada comando.
    """
    if not STT_DISPONIVEL:
        raise ErroReconhecimento(
            "Reconhecimento de voz não está instalado. Rode: pip install -r requirements.txt"
        )

    reconhecedor = sr.Recognizer()
    try:
        with sr.Microphone() as fonte:
            reconhecedor.adjust_for_ambient_noise(fonte, duration=0.5)
            audio = reconhecedor.listen(fonte, timeout=timeout, phrase_time_limit=limite_frase)
    except OSError as exc:
        raise ErroReconhecimento(
            "Não encontrei um microfone disponível neste computador."
        ) from exc
    except sr.WaitTimeoutError as exc:
        raise ErroReconhecimento("Ninguém falou a tempo.") from exc

    return _transcrever(reconhecedor, audio, idioma)


def calcular_rms(dados: bytes, largura_amostra: int = 2) -> float:
    """Volume (raiz média quadrática) de um pedaço de áudio PCM.

    Implementado em Python puro de propósito: o módulo `audioop` da
    biblioteca padrão foi removido no Python 3.13 e só existe lá através de
    um pacote extra — este cálculo funciona em qualquer versão, sem
    dependência nenhuma.
    """
    if largura_amostra != 2 or len(dados) < 2:
        return 0.0
    amostras = array.array("h")
    amostras.frombytes(dados[: len(dados) - (len(dados) % 2)])
    if not amostras:
        return 0.0
    soma_quadrados = sum(amostra * amostra for amostra in amostras)
    return math.sqrt(soma_quadrados / len(amostras))


class _StreamComMedidor:
    """Envolve o stream do microfone para medir o volume de cada pedaço de
    áudio lido, sem alterar em nada o que o reconhecedor recebe.

    É o que permite desenhar barras de som fiéis ao áudio real na interface
    gráfica: em vez de abrir um segundo stream (que competiria pelo mesmo
    microfone), espiamos os mesmos bytes que o reconhecedor já está lendo.
    """

    def __init__(self, stream, ao_medir: Callable[[float], None], largura_amostra: int) -> None:
        self._stream = stream
        self._ao_medir = ao_medir
        self._largura_amostra = largura_amostra

    def read(self, tamanho: int) -> bytes:
        dados = self._stream.read(tamanho)
        try:
            self._ao_medir(calcular_rms(dados, self._largura_amostra))
        except Exception:
            pass  # a animação nunca pode atrapalhar o reconhecimento
        return dados

    def close(self) -> None:
        self._stream.close()


class OuvidorContinuo:
    """
    Mantém o microfone aberto e calibrado uma única vez (no construtor), para
    ser reaproveitado em loops de escuta contínua. Recalibrar o ruído
    ambiente a cada comando (como ouvir_comando faz) custa ~0.5s por vez e,
    se a pessoa já começar a falar durante essa calibração, a primeira
    palavra (geralmente a palavra-chave "Alexa") pode ser cortada.

    `ao_medir_nivel`, quando informado, recebe o volume de cada pedaço de
    áudio capturado — usado pela interface gráfica para animar as barras de
    som. No modo terminal fica em None e nada muda.
    """

    def __init__(
        self,
        idioma: str = "pt-BR",
        ao_medir_nivel: Callable[[float], None] | None = None,
    ) -> None:
        if not STT_DISPONIVEL:
            raise ErroReconhecimento(
                "Reconhecimento de voz não está instalado. Rode: pip install -r requirements.txt"
            )
        self._idioma = idioma
        self._ao_medir_nivel = ao_medir_nivel
        self._reconhecedor = sr.Recognizer()
        try:
            self._microfone = sr.Microphone()
            with self._microfone as fonte:
                self._reconhecedor.adjust_for_ambient_noise(fonte, duration=1.0)
        except OSError as exc:
            raise ErroReconhecimento(
                "Não encontrei um microfone disponível neste computador."
            ) from exc

    def ouvir(self, timeout: float = 5.0, limite_frase: float = 8.0) -> str:
        try:
            with self._microfone as fonte:
                if self._ao_medir_nivel is not None:
                    fonte.stream = _StreamComMedidor(
                        fonte.stream, self._ao_medir_nivel, fonte.SAMPLE_WIDTH
                    )
                audio = self._reconhecedor.listen(fonte, timeout=timeout, phrase_time_limit=limite_frase)
        except OSError as exc:
            raise ErroReconhecimento(
                "Não encontrei um microfone disponível neste computador."
            ) from exc
        except sr.WaitTimeoutError as exc:
            raise ErroReconhecimento("Ninguém falou a tempo.") from exc

        return _transcrever(self._reconhecedor, audio, self._idioma)


def _transcrever(reconhecedor, audio, idioma: str) -> str:
    try:
        return reconhecedor.recognize_google(audio, language=idioma)
    except sr.UnknownValueError as exc:
        raise ErroReconhecimento("Não consegui entender o que foi falado.") from exc
    except sr.RequestError as exc:
        raise ErroReconhecimento(
            "Não consegui contatar o serviço de reconhecimento de voz "
            "(verifique sua conexão com a internet)."
        ) from exc


# --------------------------------------------------------------------------
# Síntese de voz (texto -> áudio)
# --------------------------------------------------------------------------

_aviso_sem_voz_pt_mostrado = False
_aviso_falha_audio_mostrado = False


def existe_voz_local_em_portugues() -> bool:
    """Diz se o sistema tem alguma voz em português instalada. Cada consulta
    cria um motor descartável — inicializar pyttsx3 é rápido, e guardar a
    instância entre chamadas é justamente o que quebra a síntese (ver
    _falar_local)."""
    if not TTS_LOCAL_DISPONIVEL:
        return False
    try:
        motor = pyttsx3.init()
    except Exception:
        return False
    try:
        return _selecionar_voz_em_portugues(motor)
    finally:
        try:
            motor.stop()
        except Exception:
            pass


def _avisar_sem_voz_pt() -> None:
    """Explica, uma única vez, como a resposta em português será produzida."""
    global _aviso_sem_voz_pt_mostrado
    if _aviso_sem_voz_pt_mostrado:
        return
    _aviso_sem_voz_pt_mostrado = True
    if TTS_ONLINE_DISPONIVEL:
        print(
            "(nenhuma voz em português instalada neste computador; "
            "usando o Google Text-to-Speech (online) para responder em pt-BR.)"
        )
    else:
        print(
            "(nenhuma voz em português instalada e gTTS indisponível; a resposta em "
            "áudio sairá na voz padrão do sistema, em outro idioma. Para instalar uma "
            "voz pt-BR no Windows: Configurações -> Hora e Idioma -> Voz -> Adicionar vozes.)"
        )


def _avisar_falha_audio(origem: str, erro: BaseException) -> None:
    """Mostra, uma única vez, por que o áudio não saiu — sem engolir o erro
    em silêncio (o que já dificultou um diagnóstico antes) nem repetir o
    aviso a cada resposta."""
    global _aviso_falha_audio_mostrado
    if _aviso_falha_audio_mostrado:
        return
    _aviso_falha_audio_mostrado = True
    print(f"(aviso: não consegui falar a resposta em áudio via {origem}: {erro})")


def _selecionar_voz_em_portugues(motor) -> bool:
    """Procura, entre as vozes instaladas no sistema, uma em português do
    Brasil e a ativa; na falta dela, aceita qualquer português. Devolve True
    se encontrou e selecionou alguma, False se manteve a voz padrão."""
    vozes = motor.getProperty("voices")

    for voz in vozes:
        idiomas = " ".join(str(v) for v in (getattr(voz, "languages", None) or []))
        pistas = f"{voz.id} {voz.name} {idiomas}".lower()
        if any(p in pistas for p in ("pt-br", "pt_br", "brazil", "brasil")):
            motor.setProperty("voice", voz.id)
            return True

    for voz in vozes:
        idiomas = " ".join(str(v) for v in (getattr(voz, "languages", None) or []))
        pistas = f"{voz.id} {voz.name} {idiomas}".lower()
        if "portuguese" in pistas or "português" in pistas or "pt-pt" in pistas:
            motor.setProperty("voice", voz.id)
            return True

    return False


def _falar_local(texto: str, exigir_portugues: bool = True) -> bool:
    """
    Fala usando o motor do sistema operacional. Devolve True se falou.

    IMPORTANTE: cria um motor pyttsx3 **novo a cada fala**. Reaproveitar a
    mesma instância parece natural, mas depois do primeiro runAndWait() o
    loop interno do pyttsx3 é encerrado e as chamadas seguintes retornam na
    hora, sem produzir som nenhum — foi exatamente esse o bug em que só a
    primeira resposta era falada e as demais saíam apenas por escrito.
    """
    motor = pyttsx3.init()
    try:
        tem_voz_pt = _selecionar_voz_em_portugues(motor)
        if exigir_portugues and not tem_voz_pt:
            return False
        motor.say(texto)
        motor.runAndWait()
        return True
    finally:
        try:
            motor.stop()
        except Exception:
            pass


def _falar_online_pt_br(texto: str) -> None:
    """Sintetiza com o Google Text-to-Speech (sempre pt-BR) e toca o mp3."""
    caminho = os.path.join(tempfile.gettempdir(), f"mini_alexa_{uuid.uuid4().hex}.mp3")
    try:
        gTTS(text=texto, lang="pt", tld="com.br").save(caminho)
        playsound(caminho)
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass


def falar(texto: str) -> None:
    """
    Lê o texto em voz alta, em português, tentando em ordem:

    1. voz pt-BR/português instalada no sistema (pyttsx3 — offline, rápido);
    2. gTTS + playsound (online, sempre pt-BR, funciona mesmo em máquina
       sem nenhuma voz instalada);
    3. voz padrão do sistema, em qualquer idioma (melhor que silêncio);
    4. nada.

    Falar é sempre best-effort: a resposta já foi impressa na tela, então
    nenhum problema de áudio (falta de biblioteca, de voz, de internet ou de
    placa de som) interrompe o programa. Se todas as tentativas falharem, o
    motivo é mostrado uma única vez, em vez de falhar em silêncio.
    """
    if not texto:
        return

    ultimo_erro: BaseException | None = None
    origem_erro = "síntese de voz"

    # 1) voz local em português
    if TTS_LOCAL_DISPONIVEL:
        try:
            if _falar_local(texto, exigir_portugues=True):
                return
            _avisar_sem_voz_pt()
        except Exception as exc:
            ultimo_erro, origem_erro = exc, "voz do sistema (pyttsx3)"

    # 2) gTTS (garante pt-BR em qualquer máquina, desde que haja internet)
    if TTS_ONLINE_DISPONIVEL:
        try:
            _falar_online_pt_br(texto)
            return
        except Exception as exc:
            ultimo_erro, origem_erro = exc, "Google Text-to-Speech (gTTS)"

    # 3) qualquer voz local, mesmo em outro idioma — melhor que silêncio
    if TTS_LOCAL_DISPONIVEL:
        try:
            if _falar_local(texto, exigir_portugues=False):
                return
        except Exception as exc:
            ultimo_erro, origem_erro = exc, "voz do sistema (pyttsx3)"

    if ultimo_erro is not None:
        _avisar_falha_audio(origem_erro, ultimo_erro)


def diagnosticar() -> str:
    """Relatório do que está disponível nesta máquina para voz — útil para
    checar o ambiente antes de testar (e para entender, sem adivinhação,
    por que a voz pode não estar funcionando em um computador específico)."""
    linhas = ["Diagnóstico de voz do Mini-Alexa", "-" * 34]

    linhas.append(
        f"Reconhecimento de fala (SpeechRecognition): {'OK' if STT_DISPONIVEL else 'NÃO INSTALADO'}"
    )

    if STT_DISPONIVEL:
        try:
            microfones = sr.Microphone.list_microphone_names()
            linhas.append(f"Microfones detectados: {len(microfones)}")
        except Exception as exc:
            linhas.append(f"Microfones detectados: falha ao listar ({exc})")

    linhas.append(
        f"Voz do sistema (pyttsx3): {'OK' if TTS_LOCAL_DISPONIVEL else 'NÃO INSTALADO'}"
    )
    if TTS_LOCAL_DISPONIVEL:
        linhas.append(
            f"  voz em português instalada: {'SIM' if existe_voz_local_em_portugues() else 'NÃO'}"
        )
    linhas.append(
        f"Voz online em pt-BR (gTTS + playsound): {'OK' if TTS_ONLINE_DISPONIVEL else 'NÃO INSTALADO'}"
    )

    linhas.append("")
    if STT_DISPONIVEL:
        linhas.append("Comandos por voz: disponíveis.")
    else:
        linhas.append(
            "Comandos por voz: indisponíveis — o programa roda só com o teclado "
            "(python main.py --texto)."
        )
    if TTS_LOCAL_DISPONIVEL or TTS_ONLINE_DISPONIVEL:
        linhas.append("Respostas em áudio: disponíveis.")
    else:
        linhas.append("Respostas em áudio: indisponíveis — as respostas sairão só por escrito.")

    return "\n".join(linhas)
