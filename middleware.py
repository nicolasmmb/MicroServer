import time
from utils import Logger
from http import Response


class CORSMiddleware:
    def __init__(self, origins="*", methods="*", headers="*", allow_credentials=False):
        self.origins = origins
        self.methods = methods
        self.headers = headers
        self.allow_credentials = allow_credentials

    async def __call__(self, req, next_handler):
        if req.method == "OPTIONS":
            resp = Response("", 204)
            self._add_headers(resp)
            return resp

        response = await next_handler(req)
        self._add_headers(response)
        return response

    def _add_headers(self, resp):
        resp.add_header("Access-Control-Allow-Origin", self.origins)
        resp.add_header("Access-Control-Allow-Methods", self.methods)
        resp.add_header("Access-Control-Allow-Headers", self.headers)
        if self.allow_credentials:
            resp.add_header("Access-Control-Allow-Credentials", "true")


class LoggingMiddleware:
    """Middleware para log detalhado de requisições: Data, IP, Método, Path, Status, Tempo."""

    def __init__(self):
        self.logger = Logger(enabled=True)

    def _fmt_duration(self, us):
        """Formata microsegundos para unidade mais apropriada (us, ms, s, min, h)."""
        if us < 1000:
            return f"{int(us)}us"
        elif us < 1000000:
            return f"{us / 1000:.3f}ms"
        elif us < 60000000:
            return f"{us / 1000000:.3f}s"
        elif us < 3600000000:
            return f"{us / 60000000:.2f}min"
        else:
            return f"{us / 3600000000:.2f}h"

    async def __call__(self, req, next_handler):
        t0 = time.ticks_us()
        response = await next_handler(req)
        dt_us = time.ticks_diff(time.ticks_us(), t0)
        time_str = self._fmt_duration(dt_us)

        t = time.localtime()
        timestamp = "{:02d}/{:02d}/{:04d} {:02d}:{:02d}:{:02d}".format(
            t[2], t[1], t[0], t[3], t[4], t[5]
        )

        log_msg = f"{timestamp} | {req.ip} | {req.method} {req.path} | {response.status} | {time_str}"

        self.logger.log(log_msg)
        return response
