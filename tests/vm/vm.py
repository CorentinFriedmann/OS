#!/usr/bin/env python3
"""Pilote minimal d'une VM QEMU par QMP (sans dépendance) pour les tests de Nova OS.

  vm.py shot  SOCKET FICHIER.png        capture d'écran (+ luminosité moyenne affichée)
  vm.py keys  SOCKET TOUCHE [TOUCHE…]   touches successives (codes QEMU : up, ret, esc…)
  vm.py chord SOCKET TOUCHE [TOUCHE…]   touches enfoncées ensemble (ex. alt sysrq s)
  vm.py type  SOCKET TEXTE              tape un texte (lettres minuscules et chiffres)
  vm.py spam  SOCKET TOUCHE SECONDES    répète une touche toutes les 0,5 s
  vm.py quit  SOCKET                    arrête QEMU immédiatement
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import tempfile
import time
import zlib


class QMP:
    def __init__(self, path: str, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.sock = socket.socket(socket.AF_UNIX)
                self.sock.connect(path)
                break
            except OSError:
                self.sock.close()
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        self.sock.settimeout(60)
        self.file = self.sock.makefile("rwb")
        self._read()  # message d'accueil
        self.execute("qmp_capabilities")

    def _read(self) -> dict:
        while True:
            line = self.file.readline()
            if not line:
                raise ConnectionError("connexion QMP fermée")
            message = json.loads(line)
            if "event" not in message:
                return message

    def execute(self, command: str, **arguments):
        payload: dict = {"execute": command}
        if arguments:
            payload["arguments"] = arguments
        self.file.write(json.dumps(payload).encode() + b"\n")
        self.file.flush()
        reply = self._read()
        if "error" in reply:
            raise RuntimeError(f"{command} : {reply['error']}")
        return reply.get("return")

    def close(self) -> None:
        self.sock.close()


def read_ppm(path: str) -> tuple[int, int, bytes]:
    data = open(path, "rb").read()
    fields: list[bytes] = []
    pos = 0
    while len(fields) < 4:  # P6 largeur hauteur maxval
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        fields.append(data[start:pos])
    if fields[0] != b"P6":
        raise ValueError("format PPM inattendu")
    width, height = int(fields[1]), int(fields[2])
    pixels = data[pos + 1:pos + 1 + width * height * 3]
    return width, height, pixels


def write_png(path: str, width: int, height: int, rgb: bytes) -> None:
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    with open(path, "wb") as out:
        out.write(b"\x89PNG\r\n\x1a\n")
        out.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        out.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        out.write(chunk(b"IEND", b""))


def screenshot(qmp: QMP, png_path: str) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        ppm = os.path.join(tmp, "ecran.ppm")
        qmp.execute("screendump", filename=ppm)
        width, height, pixels = read_ppm(ppm)
    write_png(png_path, width, height, pixels)
    sample = pixels[::301]
    return sum(sample) / max(len(sample), 1)


def key(name: str) -> dict:
    return {"type": "qcode", "data": name}


def send_keys(qmp: QMP, names: list[str], together: bool = False) -> None:
    if together:
        qmp.execute("send-key", keys=[key(n) for n in names])
        return
    for name in names:
        qmp.execute("send-key", keys=[key(name)])
        time.sleep(0.15)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    action, sock = argv[1], argv[2]
    args = argv[3:]
    qmp = QMP(sock)
    try:
        if action == "shot":
            brightness = screenshot(qmp, args[0])
            print(f"{args[0]} (luminosité moyenne {brightness:.0f}/255)")
        elif action == "keys":
            send_keys(qmp, args)
        elif action == "chord":
            send_keys(qmp, args, together=True)
        elif action == "type":
            text = args[0]
            if not all(c.isascii() and (c.islower() or c.isdigit()) for c in text):
                raise SystemExit("type : lettres minuscules et chiffres uniquement")
            send_keys(qmp, list(text))
        elif action == "spam":
            end = time.monotonic() + float(args[1])
            while time.monotonic() < end:
                qmp.execute("send-key", keys=[key(args[0])])
                time.sleep(0.5)
        elif action == "quit":
            qmp.execute("quit")
        else:
            print(__doc__)
            return 2
    finally:
        qmp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
