"""Desenhos do Clawd (mascote do Claude Code) em pixel art para telas 128x128, e o GIF animado longo."""
import math
from PIL import Image, ImageDraw

W = H = 128
U = 5                      # tamanho de um "pixel" do sprite
BG = (20, 20, 19)
ORANGE = (217, 119, 87)
LIGHT = (240, 238, 230)
DIM = (120, 110, 100)
GROUND_Y = 100
FRAME_MS = 70

# fonte 3x5 só com as letras que usamos
FONT = {
    "A": ["010", "101", "111", "101", "101"], "C": ["011", "100", "100", "100", "011"],
    "D": ["110", "101", "101", "101", "110"], "E": ["111", "100", "110", "100", "111"],
    "G": ["011", "100", "101", "101", "011"], "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"], "K": ["101", "101", "110", "101", "101"],
    "L": ["100", "100", "100", "100", "111"], "N": ["110", "101", "101", "101", "101"],
    "O": ["010", "101", "101", "101", "010"], "P": ["110", "101", "110", "100", "100"],
    "R": ["110", "101", "110", "101", "101"], "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"], "W": ["101", "101", "111", "111", "101"],
    "S": ["011", "100", "010", "001", "110"], "F": ["111", "100", "110", "100", "100"],
    "!": ["010", "010", "010", "000", "010"], ".": ["000", "000", "000", "000", "010"],
    " ": ["000", "000", "000", "000", "000"],
}


def text(d, s, y, color, scale=2):
    w = len(s) * 4 * scale - scale
    x0 = (W - w) // 2
    for i, ch in enumerate(s):
        for r, row in enumerate(FONT[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    x = x0 + i * 4 * scale + c * scale
                    d.rectangle([x, y + r * scale, x + scale - 1, y + r * scale + scale - 1], fill=color)


def cell(d, ox, oy, cx, cy, cw=1, ch=1, color=ORANGE):
    d.rectangle([ox + cx * U, oy + cy * U, ox + (cx + cw) * U - 1, oy + (cy + ch) * U - 1], fill=color)


def clawd(d, ox, oy, eye_dx=0, eye_dy=0, blink=False, happy=False,
          walk=None, arm_l=0, arm_r=0, color=ORANGE, eye=BG):
    """Desenha o Clawd com o canto superior esquerdo em (ox, oy). Sprite: 18x10 células."""
    cell(d, ox, oy, 3, 0, 12, 8, color)              # corpo
    cell(d, ox, oy, 1, 4 - arm_l * 2, 2, 2, color)   # braço esquerdo
    cell(d, ox, oy, 15, 4 - arm_r * 2, 2, 2, color)  # braço direito
    for i, lx in enumerate((4, 6, 11, 13)):          # pernas
        lifted = walk is not None and (i % 2) == walk
        cell(d, ox, oy, lx, 8, 1, 1 if lifted else 2, color)
    for ex in (5, 12):                               # olhos
        x, y = ex + eye_dx, 2 + eye_dy
        if happy:
            px, py = ox + x * U, oy + y * U + 3
            d.line([px - 1, py + 4, px + 2, py], fill=eye, width=2)
            d.line([px + 2, py, px + 5, py + 4], fill=eye, width=2)
        elif blink:
            d.rectangle([ox + x * U - 1, oy + (y + 1) * U + 1, ox + (x + 1) * U, oy + (y + 1) * U + 3], fill=eye)
        else:
            cell(d, ox, oy, x, y, 1, 2, eye)


def spinner(d, cx, cy, t, color=ORANGE):
    """Asterisco pulsante, inspirado no spinner do Claude Code (· ✢ ✳ ✶ ✻ ✽)."""
    glyph = SPIN[SPIN_SEQ[(t // 2) % len(SPIN_SEQ)]]
    n = len(glyph)
    for r, row in enumerate(glyph):
        for c, bit in enumerate(row):
            if bit == "1":
                x, y = cx + (c - n // 2) * 3, cy + (r - n // 2) * 3
                d.rectangle([x, y, x + 2, y + 2], fill=color)


SPIN = [
    ["1"],
    ["010", "111", "010"],
    ["10101", "01110", "11111", "01110", "10101"],
    ["1001001", "0101010", "0011100", "1111111", "0011100", "0101010", "1001001"],
    ["0001000", "1001001", "0101010", "0011100", "0101010", "1001001", "0001000"],
]
SPIN_SEQ = [0, 1, 2, 3, 4, 3, 2, 1]


def sparkle(d, x, y, s, color):
    d.rectangle([x - s, y, x + s, y + 1], fill=color)
    d.rectangle([x, y - s, x + 1, y + s], fill=color)


def heart(d, x, y, color):
    for r, row in enumerate(["0110110", "1111111", "1111111", "0111110", "0011100", "0001000"]):
        for c, bit in enumerate(row):
            if bit == "1":
                d.rectangle([x + c * 2, y + r * 2, x + c * 2 + 1, y + r * 2 + 1], fill=color)


def ground(d):
    for x in range(8, W - 8, 6):
        d.rectangle([x, GROUND_Y + 2, x + 2, GROUND_Y + 2], fill=(45, 43, 40))


SPRITE_W, SPRITE_H = 18 * U, 10 * U
CX = (W - SPRITE_W) // 2
BASE_Y = GROUND_Y - SPRITE_H
VERBS = ["PONDERING", "CLAUDING", "THINKING"]


def new_frame():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ground(d)
    return img, d


def build_frames():
    frames = []

    # 1) entra andando pela esquerda
    for f in range(30):
        img, d = new_frame()
        x = int(-SPRITE_W + (CX + SPRITE_W) * f / 29)
        clawd(d, x, BASE_Y - (f // 3) % 2, walk=(f // 3) % 2, eye_dx=1)
        frames.append(img)

    # 2) para, pisca e olha em volta
    for f in range(32):
        img, d = new_frame()
        eye = 0
        if 10 <= f < 18:
            eye = -1
        elif 18 <= f < 26:
            eye = 1
        clawd(d, CX, BASE_Y, eye_dx=eye, blink=f in (4, 5, 27, 28))
        frames.append(img)

    # 3) pensando, com spinner e verbos
    for f in range(48):
        img, d = new_frame()
        bob = int(round(math.sin(f * 0.35)))
        clawd(d, CX, BASE_Y + bob, eye_dy=-1, eye_dx=(1 if (f // 12) % 2 else 0),
              blink=f in (30, 31))
        spinner(d, W // 2, 28, f)
        verb = VERBS[(f // 16) % len(VERBS)]
        dots = "." * ((f // 4) % 4)
        text(d, (verb + dots).ljust(len(verb) + 3), 110, LIGHT)
        frames.append(img)

    # 4) eureka: pula com braços para cima e brilhos
    for f in range(24):
        img, d = new_frame()
        jump = int(22 * math.sin(math.pi * min(f, 14) / 14)) if f < 14 else 0
        clawd(d, CX, BASE_Y - jump, arm_l=1, arm_r=1, happy=True, walk=None)
        for i, (sx, sy) in enumerate([(14, 30), (110, 24), (24, 66), (104, 60), (64, 12)]):
            if (f + i * 2) % 6 < 4:
                s = 3 if (f + i) % 4 < 2 else 2
                sparkle(d, sx, sy, s, ORANGE if i % 2 else LIGHT)
        text(d, "DONE!", 110, ORANGE)
        frames.append(img)

    # 5) acena e solta um coração
    for f in range(30):
        img, d = new_frame()
        wave = (f // 4) % 2
        clawd(d, CX, BASE_Y, arm_r=1 + wave if wave else 1, happy=f < 20, blink=f in (24, 25))
        hy = 40 - f
        if hy > 2:
            heart(d, 96, hy, ORANGE if (f // 3) % 2 else (230, 140, 110))
        text(d, "HI!", 110, LIGHT)
        frames.append(img)

    # 6) sai andando pela direita
    for f in range(30):
        img, d = new_frame()
        x = int(CX + (W - CX) * f / 29)
        clawd(d, x, BASE_Y - (f // 3) % 2, walk=(f // 3) % 2, eye_dx=1)
        frames.append(img)

    # 7) tela vazia rápida com o spinner, antes do loop
    for f in range(10):
        img, d = new_frame()
        spinner(d, W // 2, 60, f, DIM)
        frames.append(img)
    return frames


def save(path, imgs, ms, scale=1):
    if scale > 1:
        imgs = [im.resize((W * scale, H * scale), Image.NEAREST) for im in imgs]
    pal = [im.convert("P", palette=Image.ADAPTIVE, colors=16) for im in imgs]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=ms, loop=0,
                optimize=True, disposal=1)


def write_gifs(out):
    """Gera o GIF longo (para enviar pelo app oficial ou outro uso) e uma prévia 4x."""
    import os
    frames = build_frames()
    save(os.path.join(out, "clawd_128.gif"), frames, FRAME_MS)
    save(os.path.join(out, "clawd_preview_4x.gif"), frames, FRAME_MS, scale=4)
    return len(frames)
