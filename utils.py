import os
import time

from micropython import const

# Constantes compartilhadas
CHUNK_SIZE = const(512)


class Logger:
    """Interface (Strategy) base para loggers."""

    def log(self, msg: str, level: str = "INFO"):
        raise NotImplementedError


class ConsoleLogger(Logger):
    """Implementação simples de logger para console."""

    def log(self, msg: str, level: str = "INFO"):
        print(f"[{level}] {msg}")


class FileLogger(Logger):
    """Implementação de logger com rotação de arquivo e segurança de I/O."""

    def __init__(self, filepath: str = "api.log", max_size: int = 10240):
        self.filepath = filepath
        self.max_size = max_size

    def log(self, msg: str, level: str = "INFO"):
        t = time.ticks_ms()
        # Sempre imprime no console também para debug via serial
        print(f"[{level}] {msg}")

        # Escrita segura em arquivo com rotação
        try:
            try:
                if os.stat(self.filepath)[6] > self.max_size:
                    os.remove(self.filepath)
            except OSError:
                pass  # Arquivo não existe ainda

            with open(self.filepath, "a") as f:
                f.write(f"[{t}] [{level}] {msg}\n")
        except Exception:
            # Falha silenciosa em I/O é preferível a crashar o servidor
            pass


class NoOpLogger(Logger):
    """Logger silencioso (Null Object Pattern)."""

    def log(self, msg: str, level: str = "INFO"):
        pass


def unquote(string: str) -> str:
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


def get_mime_type(filename: str) -> str:
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
