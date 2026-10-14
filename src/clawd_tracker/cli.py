"""clawd-tracker: Clawd do Claude Code na tela do teclado.

  clawd-tracker run [opções]        roda o daemon (em primeiro plano)
      --no-screen                   não mexe na tela (nenhuma gravação na flash)
      --lights                      status também nas luzes (efeito Music Follow, só pelo cabo)
      --light-color RRGGBB          cor das luzes (padrão ff4600)
      --screen-cooldown SEG         intervalo mínimo entre gravações da tela (padrão 60)
      --dry-run                     sem teclado: grava ~/.clawd-tracker/current.gif
  clawd-tracker autostart           inicia junto com o sistema (Windows: Inicializar; Linux: systemd --user)
  clawd-tracker autostart --remove
  clawd-tracker hooks               grava os hooks HTTP no ~/.claude/settings.json (se não usar o plugin)
  clawd-tracker hooks --remove
  clawd-tracker udev                (Linux) mostra a regra udev para acessar o teclado sem root
  clawd-tracker status              estado atual e teclado detectado
  clawd-tracker set <estado>        muda o estado de uma sessão manual (teste ou integrações)
  clawd-tracker preview [pasta]     gera prévias em GIF das animações
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from .server import DEFAULT_PORT, DEFAULT_SCREEN_COOLDOWN, run

HOOK_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
               "Notification", "Stop", "SessionEnd"]
UDEV_RULE = ('KERNEL=="hidraw*", ATTRS{idVendor}=="3151", ATTRS{idProduct}=="5002", '
             'MODE="0660", TAG+="uaccess"\n')
UDEV_PATH = "/etc/udev/rules.d/99-clawd-tracker.rules"


def hook_url(port):
    return f"http://127.0.0.1:{port}/hook"


# --- hooks ------------------------------------------------------------------
def cmd_hooks(args):
    path = Path.home() / ".claude" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    hooks = settings.setdefault("hooks", {})
    url = hook_url(args.port)

    def ours(group):
        return any(h.get("type") == "http" and h.get("url", "").endswith(f":{args.port}/hook")
                   for h in group.get("hooks", []))

    for ev in HOOK_EVENTS:
        groups = [g for g in hooks.get(ev, []) if not ours(g)]
        if not args.remove:
            groups.append({"hooks": [{"type": "http", "url": url, "timeout": 2}]})
        if groups:
            hooks[ev] = groups
        else:
            hooks.pop(ev, None)
    if not hooks:
        settings.pop("hooks")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(("hooks removidos de " if args.remove else "hooks gravados em ") + str(path))


# --- autostart --------------------------------------------------------------
def _windows_startup_file():
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/clawd-tracker.vbs"


def _systemd_unit_file():
    return Path.home() / ".config/systemd/user/clawd-tracker.service"


def cmd_autostart(args):
    if sys.platform == "win32":
        f = _windows_startup_file()
        if args.remove:
            f.unlink(missing_ok=True)
            print(f"removido: {f}")
            return
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else Path(sys.executable)
        f.write_text('CreateObject("WScript.Shell").Run """' + str(exe) +
                     f'"" -m clawd_tracker run --port {args.port}", 0, False\n', encoding="utf-8")
        subprocess.Popen(["wscript", str(f)])
        print(f"instalado e iniciado: {f}")
    elif sys.platform.startswith("linux"):
        f = _systemd_unit_file()
        if args.remove:
            subprocess.run(["systemctl", "--user", "disable", "--now", "clawd-tracker"], check=False)
            f.unlink(missing_ok=True)
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            print(f"removido: {f}")
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"""[Unit]
Description=Clawd tracker (status do Claude Code na tela do teclado)

[Service]
ExecStart={sys.executable} -m clawd_tracker run --port {args.port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
""", encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "clawd-tracker"], check=True)
        print(f"instalado e iniciado: {f}")
        print("logs: journalctl --user -u clawd-tracker -f")
    else:
        sys.exit("autostart só está implementado para Windows e Linux; rode `clawd-tracker run` manualmente")


def cmd_udev(args):
    if not sys.platform.startswith("linux"):
        print("só é necessário no Linux")
        return
    print("Regra para acessar o teclado sem root. Rode:\n")
    print(f"echo '{UDEV_RULE.strip()}' | sudo tee {UDEV_PATH}")
    print("sudo udevadm control --reload-rules && sudo udevadm trigger")
    print("\nDepois desconecte e conecte o cabo do teclado.")


# --- status / set / preview ---------------------------------------------------
def cmd_status(args):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/status", timeout=2) as r:
            st = json.load(r)
        print(f"daemon: rodando | estado: {st['overall']} | agentes: {st['agents']}")
    except OSError:
        print("daemon: parado (rode `clawd-tracker run` ou `clawd-tracker autostart`)")
    try:
        from .x820 import PID_WIRED, find
        devs = find()
        if not devs:
            print("teclado: não encontrado" + (" (falta a regra udev? `clawd-tracker udev`)"
                                               if sys.platform.startswith("linux") else ""))
        else:
            wired = devs[0]["product_id"] == PID_WIRED
            print("teclado: " + ("conectado pelo cabo" if wired
                                 else "só pelo 2.4G (tela e luzes de status precisam do cabo)"))
    except Exception as e:
        print(f"teclado: erro ao procurar ({e})")


def cmd_set(args):
    body = json.dumps({"session": args.session, "state": args.state}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{args.port}/state", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=2).read()
    except OSError as e:
        sys.exit(f"daemon não respondeu: {e}")


def cmd_preview(args):
    from .art import write_gifs
    from .states import write_preview
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    write_preview(str(out / "states_preview.gif"))
    write_gifs(str(out))
    print(f"prévias em {out.resolve()}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="clawd-tracker", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true", help="sem teclado: grava ~/.clawd-tracker/current.gif")
    r.add_argument("--port", type=int, default=DEFAULT_PORT)
    r.add_argument("--no-screen", action="store_true", help="não mexe na tela")
    r.add_argument("--lights", action="store_true", help="status também nas luzes (só pelo cabo)")
    r.add_argument("--light-color", default="ff4600", help="cor das luzes em hex (padrão ff4600)")
    r.add_argument("--screen-cooldown", type=float, default=DEFAULT_SCREEN_COOLDOWN)
    for name in ("hooks", "autostart"):
        s = sub.add_parser(name)
        s.add_argument("--remove", action="store_true")
        s.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub.add_parser("udev")
    sub.add_parser("status")
    s = sub.add_parser("set")
    s.add_argument("state", choices=["idle", "working", "attention", "done", "end"])
    s.add_argument("--session", default="manual")
    pv = sub.add_parser("preview")
    pv.add_argument("dir", nargs="?", default=".")
    args = p.parse_args(argv)

    if args.cmd == "run":
        color = tuple(bytes.fromhex(args.light_color.lstrip("#")))
        sys.exit(run(args.port, args.dry_run, screen=not args.no_screen, use_lights=args.lights,
                     screen_cooldown=args.screen_cooldown, light_color=color))
    {"hooks": cmd_hooks, "autostart": cmd_autostart, "udev": cmd_udev, "status": cmd_status,
     "set": cmd_set, "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    main()
