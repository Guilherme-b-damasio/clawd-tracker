"""Estado das sessões do Claude Code, alimentado pelos hooks."""
import threading
import time

STATES = ("idle", "working", "attention", "done")
DONE_DECAY_S = 5 * 60          # "done" vira "idle" depois de 5 min
STALE_S = 12 * 60 * 60         # sessão sem notícia há 12 h é descartada (terminal fechado na marra)

EVENT_STATE = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "Stop": "done",
}


def state_from_hook(data):
    """Traduz o JSON de um hook do Claude Code em um estado (None = ignorar, "end" = remover)."""
    event = data.get("hook_event_name", "")
    if event == "SessionEnd":
        return "end"
    if event == "Notification":
        kind = data.get("notification_type", "")
        msg = str(data.get("message", "")).lower()
        # pedido de permissão = precisa de você; "esperando input" depois do Stop não muda nada
        if kind == "idle_prompt" or "waiting for your input" in msg:
            return None
        return "attention"
    return EVENT_STATE.get(event)


class Tracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}          # id -> (estado, timestamp)
        self.changed = threading.Event()

    def set(self, session, state):
        with self._lock:
            if state == "end":
                self._sessions.pop(session, None)
            elif state in STATES:
                self._sessions[session] = (state, time.time())
            else:
                raise ValueError(f"estado desconhecido: {state}")
        self.changed.set()

    def on_hook(self, data):
        state = state_from_hook(data)
        if state is not None:
            self.set(data.get("session_id") or "unknown", state)

    def agents(self):
        """Lista ordenada dos estados atuais, já com decaimento e limpeza."""
        now = time.time()
        with self._lock:
            for sid, (_, ts) in list(self._sessions.items()):
                if now - ts > STALE_S:
                    del self._sessions[sid]
            out = []
            for state, ts in self._sessions.values():
                if state == "done" and now - ts > DONE_DECAY_S:
                    state = "idle"
                out.append(state)
        return sorted(out)

    def snapshot(self):
        with self._lock:
            return {sid: {"state": s, "ts": ts} for sid, (s, ts) in self._sessions.items()}
