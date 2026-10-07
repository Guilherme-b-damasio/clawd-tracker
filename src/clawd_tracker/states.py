"""Animações de status do Clawd para a tela do teclado, com barra de agentes embaixo."""
from PIL import Image, ImageDraw
from .art import W, H, U, ORANGE, LIGHT, DIM, CX, clawd, text, spinner, sparkle

BLACK = (0, 0, 0)            # preto puro não é enviado ao teclado (fica fora do retângulo)
AMBER = (245, 190, 60)
GREEN = (110, 200, 120)
MUTED = (150, 90, 70)
GRAY = (95, 90, 85)

SEG_COLOR = {"idle": MUTED, "working": ORANGE, "attention": AMBER, "done": GREEN}
PRIORITY = ["attention", "working", "done", "idle"]

TOP = 34                     # topo do Clawd
LABEL_Y = 92
BAR_Y = 110


def overall(agents):
    """Estado geral a partir da lista de estados dos agentes."""
    for s in PRIORITY:
        if s in agents:
            return s
    return "offline"


def bar(d, agents):
    x0, x1, gap = 8, 120, 3
    if not agents:
        for x in range(x0, x1, 8):
            d.rectangle([x, BAR_Y + 4, x + 3, BAR_Y + 5], fill=(40, 38, 36))
        return
    order = sorted(agents, key=PRIORITY.index)
    n = len(order)
    seg = (x1 - x0 - gap * (n - 1)) / n
    for i, s in enumerate(order):
        a = x0 + i * (seg + gap)
        d.rectangle([round(a), BAR_Y, round(a + seg) - 1, BAR_Y + 9], fill=SEG_COLOR[s])


def bang(d, x, y, color):
    d.rectangle([x, y, x + 5, y + 14], fill=color)
    d.rectangle([x, y + 18, x + 5, y + 23], fill=color)


def zzz(d, x, y, size, color):
    s = size
    d.rectangle([x, y, x + s * 3 - 1, y + s - 1], fill=color)
    d.rectangle([x + s, y + s, x + s * 2 - 1, y + s * 2 - 1], fill=color)
    d.rectangle([x, y + s * 2, x + s * 3 - 1, y + s * 3 - 1], fill=color)


def frame():
    img = Image.new("RGB", (W, H), BLACK)
    return img, ImageDraw.Draw(img)


def render(state, agents):
    """Retorna (quadros, delay_ms) para o estado e a lista de estados dos agentes."""
    frames = []
    if state == "offline":
        for f in range(4):
            img, d = frame()
            clawd(d, CX, TOP, blink=True, color=GRAY, eye=BLACK)
            zzz(d, 90 + f % 2 * 3, 24 - f * 4, 3 + (f >= 2), GRAY)
            text(d, "OFFLINE", LABEL_Y, GRAY)
            bar(d, agents)
            frames.append(img)
        return frames, 350

    if state == "idle":
        eyes = [0, 0, None, 0, -1, 1]
        for e in eyes:
            img, d = frame()
            clawd(d, CX, TOP, eye_dx=e or 0, blink=e is None, eye=BLACK)
            text(d, "IDLE", LABEL_Y, DIM)
            bar(d, agents)
            frames.append(img)
        return frames, 300

    if state == "working":
        for f, glyph in enumerate([1, 2, 3, 4, 3, 2]):
            img, d = frame()
            clawd(d, CX, TOP + f % 2, eye_dy=-1, eye=BLACK, walk=f % 2)
            spinner(d, W // 2, 17, glyph * 2)
            dots = f // 2 + 1
            text(d, "WORKING" + "." * dots + " " * (3 - dots), LABEL_Y, LIGHT)
            bar(d, agents)
            frames.append(img)
        return frames, 130

    if state == "attention":
        for f in range(4):
            img, d = frame()
            up = f % 2
            clawd(d, CX + (2 if f == 1 else -2 if f == 3 else 0), TOP,
                  arm_l=up, arm_r=1 - up, eye=BLACK)
            if f % 2 == 0:
                bang(d, 61, 4, AMBER)
            text(d, "ATTENTION", LABEL_Y, AMBER if f % 2 == 0 else LIGHT)
            bar(d, agents)
            frames.append(img)
        return frames, 170

    if state == "done":
        spots = [(14, 20), (112, 14), (24, 50), (104, 46), (64, 8)]
        for f in range(4):
            img, d = frame()
            clawd(d, CX, TOP - (3 if f in (1, 2) else 0), arm_l=1, arm_r=1, happy=True, eye=BLACK)
            for i, (sx, sy) in enumerate(spots):
                if (f + i) % 3 != 0:
                    sparkle(d, sx, sy, 3 if (f + i) % 2 else 2, GREEN if i % 2 else LIGHT)
            text(d, "DONE!", LABEL_Y, GREEN)
            bar(d, agents)
            frames.append(img)
        return frames, 180

    raise ValueError(state)


def write_preview(path):
    """Prévia (3x) com todos os estados lado a lado."""
    demo = {
        "offline": [],
        "idle": ["idle"],
        "working": ["working", "working", "idle"],
        "attention": ["attention", "working", "done"],
        "done": ["done", "idle"],
    }
    rendered = [render(k, v)[0] for k, v in demo.items()]
    n = max(len(f) for f in rendered)
    frames = []
    for i in range(n * 2):
        sheet = Image.new("RGB", (W * 5 + 24, H + 8), (30, 30, 30))
        for j, fr in enumerate(rendered):
            sheet.paste(fr[i % len(fr)], (4 + j * (W + 4), 4))
        frames.append(sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=170, loop=0)
