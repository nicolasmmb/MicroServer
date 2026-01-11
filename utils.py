import os
import time

from micropython import const

# Constantes compartilhadas
CHUNK_SIZE = const(512)


class Logger:
    """Sistema de logging minimalista com rotação de arquivo."""

    def __init__(self, enabled=True, filepath="api.log", max_size=5120):
        self.enabled = enabled
        self.filepath = filepath
        self.max_size = max_size

    def log(self, msg, level="INFO"):
        if not self.enabled:
            return
        t = time.ticks_ms()
        print(f"[{level}] {msg}")

        if self.filepath:
            try:
                try:
                    if os.stat(self.filepath)[6] > self.max_size:
                        os.remove(self.filepath)
                except OSError:
                    pass

                with open(self.filepath, "a") as f:
                    f.write(f"[{t}] [{level}] {msg}\n")
            except Exception:
                pass


def unquote(string):
    """Decodifica URL encoding (ex: %20 -> espaço)."""
    if not string:
        return ""
    res = string.split("%")
    if len(res) == 1:
        return string
    s = res[0]
    for item in res[1:]:
        try:
            s += chr(int(item[:2], 16)) + item[2:]
        except ValueError:
            s += "%" + item
    return s


def get_mime_type(filename):
    """Retorna Content-Type baseado na extensão."""
    ext = filename.split(".")[-1].lower()
    mimes = {
        "html": "text/html",
        "css": "text/css",
        "js": "application/javascript",
        "json": "application/json",
        "png": "image/png",
        "jpg": "image/jpeg",
        "txt": "text/plain",
        "ico": "image/x-icon",
        "svg": "image/svg+xml",
    }
    return mimes.get(ext, "application/octet-stream")
