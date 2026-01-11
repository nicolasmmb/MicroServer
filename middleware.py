import time
from utils import Logger, ConsoleLogger
from http import Response


class CORSMiddleware:
    def __init__(
        self,
        origins: str = "*",
        methods: str = "*",
        headers: str = "*",
        allow_credentials: bool = False,
    ):
        # Pre-calculate headers to avoid dictionary creation on every request
        self.cors_headers = {
            "Access-Control-Allow-Origin": origins,
            "Access-Control-Allow-Methods": methods,
            "Access-Control-Allow-Headers": headers,
        }

        if allow_credentials:
            self.cors_headers["Access-Control-Allow-Credentials"] = "true"

        # Cache the OPTIONS response entirely since it never changes
        # This saves memory allocation on every preflight request
        self._options_response = Response("", 204)
        self._options_response.headers.update(self.cors_headers)

    async def __call__(self, request, next_handler):
        # Fast path for preflight requests
        if request.method == "OPTIONS":
            return self._options_response

        # Process request
        response = await next_handler(request)

        # Merge CORS headers into the response headers
        # .update() is generally implemented efficiently in C for MicroPython
        response.headers.update(self.cors_headers)
        return response


class LoggingMiddleware:
    """Middleware for detailed request logging: Date, IP, Method, Path, Status, Duration."""

    def __init__(self, logger: Logger = None):
        self.logger = logger or ConsoleLogger()

    async def __call__(self, request, next_handler):
        start = time.ticks_us()
        response = await next_handler(request)
        duration = time.ticks_diff(time.ticks_us(), start)

        # Format duration logic inline for performance
        if duration < 1000:
            time_str = f"{duration}us"
        elif duration < 1000000:
            time_str = f"{duration / 1000:.3f}ms"
        else:
            time_str = f"{duration / 1000000:.3f}s"

        # Get simplified timestamp
        # MicroPython returns 8-tuple, CPython returns 9-tuple. Slicing maintains compatibility.
        y, m, d, H, M, S = time.localtime()[:6]

        # f-string formatting is efficient in recent MicroPython versions
        self.logger.log(
            f"{d:02d}/{m:02d}/{y:04d} {H:02d}:{M:02d}:{S:02d} | "
            f"{request.ip} | {request.method} {request.path} | "
            f"{response.status} | {time_str}"
        )

        return response


class MiddlewarePipeline:
    def __init__(self, final_handler):
        self.final_handler = final_handler
        self.middlewares = []

    def add(self, middleware):
        self.middlewares.append(middleware)

    def build(self):
        chain = self.final_handler
        for middleware in reversed(self.middlewares):
            chain = self._wrap(middleware, chain)
        return chain

    def _wrap(self, middleware, next_handler):
        async def wrapped_middleware(request):
            return await middleware(request, next_handler)

        return wrapped_middleware
