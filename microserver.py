import sys
import time
import uasyncio as asyncio
from http import Request, Response, _PHRASES
from routing import Router
from utils import Logger, ConsoleLogger, unquote, get_mime_type
from middleware import MiddlewarePipeline
from websocket import WebSocket

# Constantes compartilhadas
import gc
from micropython import const

# Errno constants (with MicroPython fallback)
try:
    from errno import EPIPE, ECONNRESET, EMFILE
except ImportError:
    EPIPE = 32
    ECONNRESET = 104
    EMFILE = 23


# Semaphore implementation for MicroPython (uasyncio doesn't have Semaphore)
class _Semaphore:
    """Async semaphore for MicroPython compatibility"""

    def __init__(self, value=1):
        self._value = value
        self._max_value = value
        self._waiters = []

    def locked(self):
        """Returns True if semaphore cannot be acquired immediately."""
        return self._value == 0

    async def __aenter__(self):
        """Acquire semaphore (async context manager)"""
        while self._value <= 0:
            # Wait for release
            event = asyncio.Event()
            self._waiters.append(event)
            await event.wait()
        self._value -= 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Release semaphore (async context manager)"""
        self._value += 1
        # Wake up one waiter
        if self._waiters:
            waiter = self._waiters.pop(0)
            waiter.set()
        return False

CHUNK_SIZE = const(512)
_READLINE_TIMEOUT = const(2)
_HEADER_TIMEOUT = const(2)
_MAX_HEADERS = const(50)
_MAX_HEADER_SIZE = const(8192)
_MAX_REQUEST_LINE = const(8192)
_BODY_TIMEOUT = const(30)


def _format_http_date():
    """Format current time as RFC 7231 HTTP-date (IMF-fixdate)"""
    t = time.gmtime()
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return "{}, {:02d} {} {:04d} {:02d}:{:02d}:{:02d} GMT".format(
        days[t[6]], t[2], months[t[1]-1], t[0], t[3], t[4], t[5]
    )


class MicroServer:
    def __init__(
        self, port: int = 80, logger: Logger = None, router=None, max_conns: int = 10
    ):
        # NOTE: ESP32 standard builds often have a hard limit of ~10-16 sockets (LWIP).
        # Setting max_conns > 10 might not work depending on the firmware/usage.
        self.port = port
        self.logger = logger or ConsoleLogger()
        self.router = router or Router()
        self.middlewares = []
        self.max_conns = max_conns
        self._conn_semaphore = _Semaphore(max_conns)
        self._active_connections = 0
        self._warned_capacity = False
        self.ws_routes = {}
        self.max_body_size = 1024 * 1024  # 1MB limit for safety
        self.server_name = "MicroServer/1.0"
        self.keep_alive_timeout = 5  # seconds
        self.max_keep_alive_requests = 100
        self.body_timeout = 30  # seconds
        self._handler = None  # Cached pipeline

    def add_middleware(self, middleware):
        self.middlewares.append(middleware)
        self._handler = None  # Invalidate cache

    def route(self, path, methods=["GET"]):
        def decorator(handler):
            for method in methods:
                self.router.add(method, path, handler)
            return handler

        return decorator

    # Helpers RESTful
    def get(self, path):
        return self.route(path, methods=["GET"])

    def post(self, path):
        return self.route(path, methods=["POST"])

    def put(self, path):
        return self.route(path, methods=["PUT"])

    def delete(self, path):
        return self.route(path, methods=["DELETE"])

    def patch(self, path):
        return self.route(path, methods=["PATCH"])

    def _build_pipeline(self):
        """Constrói a cadeia de execução."""
        pipeline = MiddlewarePipeline(self._dispatch_request)
        for mw in self.middlewares:
            pipeline.add(mw)
        return pipeline.build()

    def _get_handler(self):
        """Get cached handler or build new pipeline"""
        if self._handler is None:
            self._handler = self._build_pipeline()
        return self._handler

    def websocket(self, path: str):
        def decorator(handler):
            self.ws_routes[path] = handler
            return handler

        return decorator

    def mount_static(self, url_path: str, dir_path: str, max_age: int = 3600):
        import os

        async def static_handler(request):
            file_path = request.path.replace(url_path, dir_path, 1)
            if ".." in file_path:
                return Response.plain("Forbidden", 403)
            try:
                os.stat(file_path)
            except OSError:
                return Response.plain("Not Found", 404)

            response = self.send_file(file_path)
            response.add_header("Cache-Control", f"public, max-age={max_age}")
            return response

        self.route(url_path, methods=["GET"])(static_handler)
        self.router.add_static(url_path, static_handler)

    def send_file(self, filename: str):
        async def file_gen():
            f = None
            try:
                f = open(filename, "rb")
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    yield data
                    await asyncio.sleep_ms(0)  # Yield control
            finally:
                if f:
                    try:
                        f.close()
                    except Exception:
                        pass

        return Response.stream(file_gen(), content_type=get_mime_type(filename))

    async def _dispatch_request(self, request):
        """Encontra o handler para a rota e executa."""
        handler, params = self.router.match(request.method, request.path)

        if not handler:
            return Response.error("Not Found", 404)

        request.path_params = params

        try:
            result = await handler(request)

            # Estrito: O handler DEVE retornar um objeto Response
            if not isinstance(result, Response):
                # Levanta exceção para ser capturada pelo bloco except abaixo
                raise ValueError(f"Handler returned {type(result)}, expected Response")
            return result

        except Exception as e:
            sys.print_exception(e)
            self.logger.log(f"Handler Error: {e}", "ERROR")
            return Response.error("Internal Server Error", 500)

    async def _handle_request(self, reader, writer):
        # Try to acquire semaphore (non-blocking check)
        if self._conn_semaphore.locked():
            # Semaphore full, reject immediately
            try:
                writer.write(b"HTTP/1.1 503 Service Unavailable\r\n")
                writer.write(b"Retry-After: 5\r\n")
                writer.write(b"Content-Length: 0\r\n\r\n")
                await writer.drain()
            finally:
                writer.close()
            return

        async with self._conn_semaphore:
            self._active_connections += 1

            # Capacity warning
            if self._active_connections >= self.max_conns * 0.8 and not self._warned_capacity:
                self.logger.log(f"WARNING: 80% capacity ({self._active_connections}/{self.max_conns})", "WARNING")
                self._warned_capacity = True

            request_count = 0
            addr = writer.get_extra_info("peername")

            try:
                while request_count < self.max_keep_alive_requests:
                    # Parse request line with timeout
                    try:
                        line = await asyncio.wait_for(reader.readline(), _READLINE_TIMEOUT)
                    except asyncio.TimeoutError:
                        if request_count == 0:
                            # No request received on new connection
                            break
                        else:
                            # Idle timeout on keep-alive connection
                            break

                    if not line:
                        break

                    if len(line) > _MAX_REQUEST_LINE:
                        await self._send_response(writer, Response.plain("URI Too Long", 414), keep_alive=False, requests_remaining=0)
                        break

                    parts = line.decode().strip().split()
                    if len(parts) < 2:
                        break

                    method, path = parts[0].upper(), unquote(parts[1])

                    # Parse headers
                    headers = {}
                    header_count = 0

                    while True:
                        if header_count >= _MAX_HEADERS:
                            await self._send_response(writer, Response.plain("Too Many Headers", 431), keep_alive=False, requests_remaining=0)
                            return

                        header_line = await asyncio.wait_for(reader.readline(), _HEADER_TIMEOUT)
                        if not header_line or header_line == b"\r\n":
                            break

                        if len(header_line) > _MAX_HEADER_SIZE:
                            await self._send_response(writer, Response.plain("Header Too Large", 431), keep_alive=False, requests_remaining=0)
                            return

                        if b":" not in header_line:
                            continue

                        try:
                            key, value = header_line.decode().strip().split(":", 1)
                            # Validate token format (RFC 7230 §3.2)
                            if not key or not all(c.isalnum() or c in "-_" for c in key):
                                continue
                            headers[key.lower()] = value.strip()
                            header_count += 1
                        except (ValueError, UnicodeDecodeError):
                            continue

                    # Check keep-alive preference
                    connection_header = headers.get("connection", "").lower()
                    keep_alive = (connection_header == "keep-alive")

                    # Handle WebSocket upgrade
                    if headers.get("upgrade", "").lower() == "websocket" and path in self.ws_routes:
                        await self._handle_websocket(reader, writer, path, headers)
                        return  # WebSocket takes over connection

                    # Handle HTTP request
                    request = await self._create_request(reader, writer, method, path, headers, addr)
                    if not request:
                        break

                    handler = self._get_handler()
                    response = await handler(request)

                    # Send response with appropriate Connection header
                    should_keep_alive = keep_alive and request_count < self.max_keep_alive_requests - 1
                    await self._send_response(
                        writer, response,
                        keep_alive=should_keep_alive,
                        requests_remaining=self.max_keep_alive_requests - request_count - 1
                    )

                    request_count += 1

                    if not should_keep_alive:
                        break

                    # Wait for next request with keep-alive timeout
                    # Note: Due to MicroPython limitations, we can't peek/pushback bytes efficiently
                    # So we just wait for the next iteration to read the next request
                    await asyncio.sleep(0)  # Yield control

            except asyncio.TimeoutError:
                # Normal behavior for keep-alive/pre-opened connections that don't send data
                pass
            except OSError as e:
                # Ignora erros de desconexão comuns
                if e.args[0] in (EPIPE, ECONNRESET):
                    self.logger.log(f"Connection closed by peer: {e}", "DEBUG")
                elif e.args[0] == EMFILE:
                    self.logger.log(f"System limit reached: {e}", "WARNING")
                    try:
                        await self._send_response(
                            writer, Response.error("Service Unavailable", 503),
                            keep_alive=False, requests_remaining=0
                        )
                    except Exception:
                        pass
                else:
                    sys.print_exception(e)
                    self.logger.log(f"Server Error: {repr(e)}", "ERROR")
            except Exception as e:
                sys.print_exception(e)
                self.logger.log(f"Server Error: {repr(e)}", "ERROR")
            finally:
                self._active_connections -= 1
                try:
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
                gc.collect()

    async def _handle_websocket(self, reader, writer, path, headers):
        websocket = WebSocket(reader, writer)
        if not await websocket.accept(headers):
            await self._send_response(
                writer, Response.plain("Bad WebSocket handshake", 400)
            )
            return

        self.logger.log(f"WS Connect: {path}")
        try:
            await self.ws_routes[path](websocket)
        except Exception as e:
            self.logger.log(f"WS Error: {e}", "ERROR")

    async def _create_request(self, reader, writer, method, path, headers, addr):
        content_length_header = headers.get("content-length")
        try:
            content_length = int(content_length_header) if content_length_header else 0
        except ValueError:
            await self._send_response(
                writer,
                Response.plain("Invalid Content-Length", 400),
                keep_alive=False,
                requests_remaining=0
            )
            return None

        body = None
        if content_length > 0:
            if content_length > self.max_body_size:
                await self._send_response(
                    writer,
                    Response.plain("Payload Too Large", 413),
                    keep_alive=False,
                    requests_remaining=0
                )
                return None

            try:
                body = await asyncio.wait_for(
                    reader.read(content_length),
                    self.body_timeout
                )
            except asyncio.TimeoutError:
                await self._send_response(
                    writer,
                    Response.plain("Request Timeout", 408),
                    keep_alive=False,
                    requests_remaining=0
                )
                return None

        request = Request(method, path, headers, addr[0])
        request.body = body
        return request

    async def _send_response(self, writer, response, keep_alive=False, requests_remaining=0):
        reason = self._reason_phrase(response.status)
        http_date = _format_http_date()

        writer.write(f"HTTP/1.1 {response.status} {reason}\r\n".encode())
        writer.write(f"Date: {http_date}\r\n".encode())
        writer.write(f"Server: {self.server_name}\r\n".encode())

        if keep_alive:
            writer.write(b"Connection: keep-alive\r\n")
            writer.write(f"Keep-Alive: timeout={self.keep_alive_timeout}, max={requests_remaining}\r\n".encode())
        else:
            writer.write(b"Connection: close\r\n")

        writer.write(f"Content-Type: {response.content_type}\r\n".encode())
        for key, value in response.headers.items():
            writer.write(f"{key}: {value}\r\n".encode())

        if self._is_streaming_body(response.body):
            await self._send_streaming_body(writer, response.body)
        else:
            await self._send_payload(writer, response.body)
        await writer.drain()

    async def _send_streaming_body(self, writer, body):
        writer.write(b"Transfer-Encoding: chunked\r\n\r\n")
        gen = body
        if hasattr(gen, "__aiter__"):
            async for chunk in gen:
                await self._write_chunk(writer, chunk)
        else:
            for chunk in gen:
                await self._write_chunk(writer, chunk)
        writer.write(b"0\r\n\r\n")

    async def _send_payload(self, writer, payload):
        if isinstance(payload, str):
            payload = payload.encode()
        writer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode())
        writer.write(payload)

    async def _write_chunk(self, writer, chunk):
        if not chunk:
            return
        if isinstance(chunk, str):
            chunk = chunk.encode()

        # Build complete chunk: size\r\ndata\r\n (single write for efficiency)
        size_hex = f"{len(chunk):x}"
        complete = bytearray()
        complete.extend(size_hex.encode())
        complete.extend(b"\r\n")
        complete.extend(chunk)
        complete.extend(b"\r\n")

        writer.write(complete)
        await writer.drain()

    async def start(self):
        self.logger.log(f"Server started on port {self.port}")
        return await asyncio.start_server(self._handle_request, "0.0.0.0", self.port)

    async def run(self, host: str = "0.0.0.0", port: int = None):
        if port is not None:
            self.port = port
        self.logger.log(f"Server started on port {self.port}")
        return await asyncio.start_server(self._handle_request, host, self.port)

    def _reason_phrase(self, status: int) -> str:
        return _PHRASES.get(status, "")

    def _is_streaming_body(self, body) -> bool:
        if body is None:
            return False
        if hasattr(body, "__aiter__"):
            return True
        if hasattr(body, "__next__"):
            return True
        if hasattr(body, "__iter__") and not isinstance(body, (bytes, bytearray, str)):
            return True
        return False
