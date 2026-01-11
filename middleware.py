import time
from utils import Logger
from http import Response


class CORSMiddleware:
    def __init__(self, origins="*", methods="*", headers="*", allow_credentials=False):
        self.origins = origins
        self.methods = methods
        self.headers = headers
        self.allow_credentials = allow_credentials

    async def __call__(self, request, next_handler):
        if request.method == "OPTIONS":
            response = Response("", 204)
            self._add_headers(response)
            return response

        response = await next_handler(request)
        self._add_headers(response)
        return response

    def _add_headers(self, response):
        response.add_header("Access-Control-Allow-Origin", self.origins)
        response.add_header("Access-Control-Allow-Methods", self.methods)
        response.add_header("Access-Control-Allow-Headers", self.headers)
        if self.allow_credentials:
            response.add_header("Access-Control-Allow-Credentials", "true")


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

    async def __call__(self, request, next_handler):
        start_time = time.ticks_us()
        response = await next_handler(request)
        duration_us = time.ticks_diff(time.ticks_us(), start_time)
        time_str = self._fmt_duration(duration_us)

        time_struct = time.localtime()
        timestamp = "{:02d}/{:02d}/{:04d} {:02d}:{:02d}:{:02d}".format(
            time_struct[2], time_struct[1], time_struct[0], time_struct[3], time_struct[4], time_struct[5]
        )

        log_msg = f"{timestamp} | {request.ip} | {request.method} {request.path} | {response.status} | {time_str}"

        self.logger.log(log_msg)
        return response
