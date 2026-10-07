"""Envio de animações para a tela TFT 128x128 do Attack Shark X820 Ultra.

Protocolo extraído do driver oficial (Attack Shark Driver v4, Electron):
- HID feature report de 64 bytes na interface usagePage 0xFFFF / usage 2.
- byte 7 = 255 - (soma dos bytes 0..6 & 0xFF)  ("Bit7").
- 0xA5: cabeçalho (quadro, total, delay em ms, tamanho do quadro, retângulo).
- 0x25: dados, 8 bytes de cabeçalho + 56 bytes de pixels RGB565 big-endian,
  varridos por coluna (x externo, y interno).
- Pelo receptor 2.4G (PID 0x5006) cada comando é roteado: F7 (status),
  F6 0x0A (seleciona teclado), comando, e para ler: F7 até canRead, FC, get.
  O firmware recusa envio de imagem pelo 2.4G, então o upload exige o cabo.
"""
import sys
import time


def _hid_backend():
    # No Linux, prefere hidraw: funciona junto com o driver do kernel, sem precisar desanexá-lo como o libusb.
    if sys.platform.startswith("linux"):
        try:
            import hidraw
            return hidraw
        except ImportError:
            pass
    import hid
    return hid


hid = _hid_backend()

VID = 0x3151
PID_WIRED = 0x5002
PID_DONGLE = 0x5006
W = H = 128


def _pad(cmd):
    b = bytearray(64)
    b[:len(cmd)] = bytes(cmd)
    return b


def _encode(cmd):
    b = _pad(cmd)
    b[7] = 255 - (sum(b[:7]) & 255)
    return b


def _is_command_interface(d):
    if d['product_id'] not in (PID_WIRED, PID_DONGLE):
        return False
    if d.get('usage_page'):
        return d['usage_page'] == 0xFFFF and d['usage'] == 2
    return d.get('interface_number') == 2       # backends que não informam usage_page


def find():
    """Lista as interfaces de comando encontradas (cabo primeiro)."""
    devs = [d for d in hid.enumerate(VID) if _is_command_interface(d)]
    devs.sort(key=lambda d: d['product_id'] != PID_WIRED)
    return devs


class X820:
    def __init__(self):
        devs = find()
        if not devs:
            raise RuntimeError("X820 Ultra não encontrado (cabo ou receptor 2.4G)")
        self.wireless = devs[0]['product_id'] == PID_DONGLE
        self.h = hid.device()
        self.h.open_path(devs[0]['path'])
        self._routed = False
        self.packet_sleep = 0.001   # sem pausa o teclado perde pacotes e os quadros saem corrompidos

    def close(self):
        self.h.close()

    # --- transporte ---------------------------------------------------------
    def _feat(self, b):
        self.h.send_feature_report(bytes([0]) + bytes(b))

    def _get(self):
        return bytes(self.h.get_feature_report(0, 65))[1:]

    def _status(self):
        self._feat(_pad([0xF7]))
        time.sleep(0.004)
        r = self._get()
        return {'canRead': r[0] == 1, 'battery': r[1], 'online': r[3] == 0, 'canSend': r[5] == 1}

    def _wait(self, key, timeout=2.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self._status()[key]:
                return True
            time.sleep(0.003)
        return False

    def send(self, cmd):
        if not self.wireless:
            self._feat(_encode(cmd))
            return True
        if not self._wait('canSend'):
            return False
        if not self._routed:
            self._feat(_pad([0xF6, 0x0A]))
            time.sleep(0.01)
            self._routed = True
        self._feat(_encode(cmd))
        return True

    def ask(self, cmd, timeout=1.0, read_delay=0.01):
        if not self.send(cmd):
            return None
        if not self.wireless:
            time.sleep(read_delay)
            return self._get()
        if not self._wait('canRead', timeout):
            return None
        self._feat(_pad([0xFC]))
        time.sleep(0.01)
        return self._get()

    # --- comandos -----------------------------------------------------------
    def device_id(self):
        r = self.ask([0x8F])
        return int.from_bytes(r[1:5], 'little') if r and r[0] == 0x8F else None

    def battery(self):
        return self._status()['battery'] if self.wireless else None

    def upload(self, frames, delay_ms=80, progress=None):
        """frames: lista de PIL.Image 128x128. Preto puro (0,0,0) fora do desenho não é enviado."""
        rgb = [f.convert('RGB') for f in frames]
        box = None
        for im in rgb:
            b = im.getbbox()                     # bbox dos pixels não-pretos
            if b:
                box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                             max(box[2], b[2]), max(box[3], b[3]))
        left, top, right, bottom = box or (0, 0, 1, 1)
        datas = []
        for im in rgb:
            px = im.load()
            out = bytearray()
            for x in range(left, right):
                for y in range(top, bottom):
                    r, g, b = px[x, y]
                    v = (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)
                    out += bytes((v >> 8, v & 255))
            datas.append(out)

        n, delay = len(datas), max(0, min(255, int(delay_ms)))
        size = len(datas[0])
        head = [0xA5, 0, n, delay, size & 255, (size >> 8) & 255, 0, 0,
                left & 255, top & 255, right & 255, bottom & 255,
                left >> 8, top >> 8, right >> 8, bottom >> 8,
                (size >> 16) & 255, (size >> 24) & 255, 0]
        ok = False
        for _ in range(10):
            r = self.ask(head, timeout=1.5, read_delay=0.1)
            if r is not None and r[1] == 1:
                ok = True
                break
            time.sleep(0.1)
        if not ok:
            raise RuntimeError("teclado não aceitou o cabeçalho da imagem")
        time.sleep(0.1)

        chunks = (size + 55) // 56
        total = n * chunks
        for fi, data in enumerate(datas):
            for ci in range(chunks):
                part = data[ci * 56:(ci + 1) * 56]
                pkt = bytes([0x25, fi, n, delay, ci & 255, ci >> 8, len(part), 0]) + part.ljust(56, b'\0')
                if not self.send(pkt):
                    raise RuntimeError(f"falha no quadro {fi}, pacote {ci}")
                if self.packet_sleep:
                    time.sleep(self.packet_sleep)
                if progress:
                    progress((fi * chunks + ci + 1) / total)
        return {'frames': n, 'rect': (left, top, right, bottom), 'bytes': size * n}
