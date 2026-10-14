"""Status nas luzes pelo efeito "Music Follow" do teclado (comando 0x0D: não grava na flash).

O teclado fica no modo Music Follow numa cor só; o daemon manda a altura (0..6) de cada uma
das 21 colunas, como um equalizador. Cada estado vira um desenho:

  working    onda correndo da esquerda para a direita
  attention  tudo piscando
  done       tudo aceso por DONE_LIGHT_S, depois apaga
  idle/offline  nada é enviado

Só funciona pelo cabo (pelo 2.4G o teclado ignora os dados).
"""
import math

from .x820 import BAR_COLS, BAR_MAX, MODE_MUSIC_FOLLOW

DONE_LIGHT_S = 30
DEFAULT_COLOR = (255, 70, 0)          # nos LEDs, o laranja do Clawd (#D97757) fica desbotado


def mode_params(color=DEFAULT_COLOR):
    """Bytes do 0x07 que colocam o teclado em Music Follow com a cor dada (brilho máximo)."""
    return bytes([MODE_MUSIC_FOLLOW, 4, 4, 4, *color])


def frame(state, t, since):
    """Alturas das colunas para o estado, ou None para não mandar nada."""
    if state == "working":
        pos = (t * 14) % (BAR_COLS + 8) - 4
        return [BAR_MAX * max(0.0, 1 - abs(x - pos) / 4) for x in range(BAR_COLS)]
    if state == "attention":
        return [BAR_MAX if int(t * 3) % 2 == 0 else 0] * BAR_COLS
    if state == "done" and t - since <= DONE_LIGHT_S:
        k = 0.5 + 0.5 * math.sin((t - since) * 2)
        return [BAR_MAX - round(k)] * BAR_COLS
    return None
