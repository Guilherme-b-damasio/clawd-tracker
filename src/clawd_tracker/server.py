"""Daemon: recebe os hooks por HTTP local e mantém a tela do teclado atualizada.

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

from .states import overall, render
from .tracker import Tracker

DEFAULT_PORT = 47820
BASE_DIR = os.path.join(os.path.expanduser("~"), ".clawd-tracker")
DEBOUNCE_S = 0.6
RETRY_S = 3.0

log = logging.getLogger("clawd")


class KeyboardDisplay:
    """Envia as animações ao X820 Ultra pelo cabo; reconecta sozinho."""

    def __init__(self):
        self.kb = None
        self._next_try = 0.0

    def _connect(self):
        if self.kb:
            return True
        if time.time() < self._next_try:
            return False
        self._next_try = time.time() + RETRY_S
        from .x820 import X820
        try:
            kb = X820()
        except Exception:
            return False
        if kb.wireless:
            kb.close()
            log.info("teclado só pelo 2.4G; a tela só atualiza com o cabo (modo com fio)")
            return False
        self.kb = kb
        log.info("teclado conectado pelo cabo")
        return True

    def show(self, frames, delay):
        if not self._connect():
            return False
        try:
            self.kb.upload(frames, delay_ms=delay)
            return True
        except Exception as e:
            log.warning("falha ao enviar (%s); reconectando", e)
            self.close()
            return False

    def close(self):
        if self.kb:
            try:
                self.kb.close()
            except Exception:
                pass
            self.kb = None


class FileDisplay:
    """Modo sem teclado: grava a animação atual em ~/.clawd-tracker/current.gif."""

    def __init__(self, path):
        self.path = path

    def show(self, frames, delay):
        frames[0].save(self.path, save_all=True, append_images=frames[1:], duration=delay, loop=0)
        return True

    def close(self):
        pass


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


def run(port=DEFAULT_PORT, dry_run=False):
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
    display = FileDisplay(os.path.join(BASE_DIR, "current.gif")) if dry_run else KeyboardDisplay()
    log.info("daemon ouvindo em http://127.0.0.1:%d%s", port, " (sem teclado)" if dry_run else "")

    shown = None
    try:
        while True:
            tracker.changed.wait(timeout=RETRY_S)
            tracker.changed.clear()
            time.sleep(DEBOUNCE_S)                   # junta rajadas de eventos (Pre/PostToolUse)
            agents = tuple(tracker.agents())
            if agents == shown:
                continue
            state = overall(agents)
            frames, delay = render(state, list(agents))
            t0 = time.time()
            if display.show(frames, delay):
                shown = agents
                log.info("%s %s (%.1fs)", state, list(agents), time.time() - t0)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        if shown is not None:                        # deixa o Clawd dormindo ao sair
            display.show(*render("offline", []))
        display.close()
    return 0
