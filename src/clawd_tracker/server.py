"""Daemon: recebe os hooks por HTTP local e mantém o teclado atualizado.

- Tela: animação do Clawd, só pelo cabo. Grava na flash, então só troca quando o estado geral
  muda e respeita um intervalo mínimo entre gravações.
- Luzes (opcional, --lights): desenhos pelo efeito Music Follow, só pelo cabo, sem gravar na flash
  (exceto uma vez, para colocar o teclado nesse modo).

Endpoints (só em 127.0.0.1):
  POST /hook    JSON de um hook do Claude Code (hooks do tipo "http" apontam pra cá)
  POST /state   {"session": "qualquer-id", "state": "idle|working|attention|done|end"}
  GET  /status  estado atual em JSON
"""
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import lights
from .states import overall, render
from .tracker import Tracker

DEFAULT_PORT = 47820
DEFAULT_SCREEN_COOLDOWN = 60.0
BASE_DIR = os.path.join(os.path.expanduser("~"), ".clawd-tracker")
DEBOUNCE_S = 0.6
RETRY_S = 3.0
WIRED_CHECK_S = 10.0

log = logging.getLogger("clawd")


class KeyboardLink:
    """Conexão compartilhada com o teclado: prefere o cabo, cai para o 2.4G, reconecta sozinha."""

    def __init__(self):
        self._lock = threading.Lock()
        self.kb = None
        self._next_try = 0.0
        self._next_wired_check = 0.0

    def get(self):
        from .x820 import PID_WIRED, X820, find
        with self._lock:
            now = time.time()
            if self.kb and self.kb.wireless and now >= self._next_wired_check:
                self._next_wired_check = now + WIRED_CHECK_S
                try:
                    if any(d["product_id"] == PID_WIRED for d in find()):
                        log.info("cabo detectado; trocando para a conexão com fio")
                        self._close()
                except Exception:
                    pass
            if self.kb is None and now >= self._next_try:
                self._next_try = now + RETRY_S
                try:
                    self.kb = X820()
                    log.info("teclado conectado %s", "pelo 2.4G (só luzes)" if self.kb.wireless else "pelo cabo")
                except Exception:
                    self.kb = None
            return self.kb

    def reset(self, why):
        with self._lock:
            if self.kb:
                log.warning("conexão com o teclado perdida (%s); reconectando", why)
                self._close()

    def _close(self):
        try:
            self.kb.close()
        except Exception:
            pass
        self.kb = None


def lights_loop(link, tracker, stop, color):
    """Manda as barras do estado atual ~30x/s pelo cabo; não manda nada em idle/offline."""
    state, since, mode_ok = None, time.time(), False
    while not stop.is_set():
        now_state = overall(tracker.agents())
        if now_state != state:
            state, since = now_state, time.time()
        bars = lights.frame(state, time.time(), since)
        kb = link.get() if bars is not None else None
        if kb is None or kb.wireless:
            mode_ok = False
            stop.wait(0.5)
            continue
        try:
            if not mode_ok:
                want = lights.mode_params(color)
                if kb.light_setting() != want:
                    log.info("luzes: colocando o teclado em Music Follow (grava a configuração uma vez)")
                    kb.set_light_setting(want)
                mode_ok = True
            kb.music_bars(bars)
        except Exception as e:
            mode_ok = False
            link.reset(e)
        stop.wait(0.033)


class FileDisplay:
    """Modo sem teclado: grava a animação atual em ~/.clawd-tracker/current.gif."""

    def __init__(self, path):
        self.path = path

    def show(self, frames, delay):
        frames[0].save(self.path, save_all=True, append_images=frames[1:], duration=delay, loop=0)
        return True


class ScreenDisplay:
    def __init__(self, link):
        self.link = link

    def show(self, frames, delay):
        kb = self.link.get()
        if kb is None or kb.wireless:
            return False
        try:
            kb.upload(frames, delay_ms=delay)
            return True
        except Exception as e:
            self.link.reset(e)
            return False


def _handler(tracker):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(n) or b"{}")
                if self.path == "/hook":
                    tracker.on_hook(data)
                elif self.path == "/state":
                    tracker.set(str(data["session"]), data["state"])
                else:
                    return self._reply(404, {"error": "not found"})
            except (ValueError, KeyError, TypeError) as e:
                return self._reply(400, {"error": str(e)})
            self._reply(200, {})          # resposta vazia: o Claude Code não muda nada

        def do_GET(self):
            if self.path != "/status":
                return self._reply(404, {"error": "not found"})
            agents = tracker.agents()
            self._reply(200, {"overall": overall(agents), "agents": agents, "sessions": tracker.snapshot()})

        def log_message(self, *args):
            pass

    return Handler


def run(port=DEFAULT_PORT, dry_run=False, screen=True, use_lights=False,
        screen_cooldown=DEFAULT_SCREEN_COOLDOWN, light_color=lights.DEFAULT_COLOR):
    os.makedirs(BASE_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(BASE_DIR, "daemon.log"), encoding="utf-8"),
                                  logging.StreamHandler()])
    tracker = Tracker()
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler(tracker))
    except OSError:
        log.info("porta %d ocupada: o daemon já deve estar rodando", port)
        return 1
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    stop = threading.Event()
    link = KeyboardLink()
    if dry_run:
        display = FileDisplay(os.path.join(BASE_DIR, "current.gif"))
    else:
        display = ScreenDisplay(link) if screen else None
        if use_lights:
            threading.Thread(target=lights_loop, args=(link, tracker, stop, light_color), daemon=True).start()
    log.info("daemon ouvindo em http://127.0.0.1:%d (tela: %s, luzes: %s)", port,
             "arquivo" if dry_run else ("sim" if screen else "não"),
             "não" if dry_run or not use_lights else "sim")

    shown, last_upload = None, 0.0
    try:
        while display is not None:
            tracker.changed.wait(timeout=RETRY_S)
            tracker.changed.clear()
            time.sleep(DEBOUNCE_S)                   # junta rajadas de eventos (Pre/PostToolUse)
            agents = tuple(tracker.agents())
            state = overall(agents)
            if state == shown or time.time() - last_upload < screen_cooldown:
                continue
            frames, delay = render(state, list(agents))
            t0 = time.time()
            if display.show(frames, delay):
                shown, last_upload = state, time.time()
                log.info("tela: %s %s (%.1fs)", state, list(agents), time.time() - t0)
        while True:                                  # sem tela: só mantém o processo vivo
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.shutdown()
        if display is not None and shown is not None:    # deixa o Clawd dormindo ao sair
            display.show(*render("offline", []))
        if link.kb:
            link.kb.close()
    return 0
