import sys
import uasyncio as asyncio
from http import Request, Response, _PHRASES
from routing import Router
from utils import Logger, ConsoleLogger, unquote, get_mime_type
from middleware import MiddlewarePipeline
from websocket import WebSocket

# Constantes compartilhadas
import gc
from micropython import const

CHUNK_SIZE = const(512)
_READLINE_TIMEOUT = const(2)
_HEADER_TIMEOUT = const(2)


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
        self.conns = 0
        self.max_conns = max_conns
        self.ws_routes = {}
        self.max_body_size = 1024 * 1024  # 1MB limit for safety

    def add_middleware(self, middleware):
        self.middlewares.append(middleware)

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

    def websocket(self, path: str):
        def decorator(handler):
            self.ws_routes[path] = handler
            return handler

        return decorator

    def mount_static(self, url_path: str, dir_path: str):
        import os

        async def static_handler(request):
            file_path = request.path.replace(url_path, dir_path, 1)
            if ".." in file_path:
                return Response.plain("Forbidden", 403)
            try:
                os.stat(file_path)
            except OSError:
                return Response.plain("Not Found", 404)

            return self.send_file(file_path)

        self.route(url_path, methods=["GET"])(static_handler)
        self.router.add_static(url_path, static_handler)

    def send_file(self, filename: str):
        async def file_gen():
            with open(filename, "rb") as f:
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    yield data

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
        if self.conns >= self.max_conns:
            writer.close()
            return
        self.conns += 1
        addr = writer.get_extra_info("peername")

        try:
            line = await asyncio.wait_for(reader.readline(), _READLINE_TIMEOUT)

            if not line:
                return

            parts = line.decode().strip().split()
            if len(parts) < 2:
                return

            method, path = parts[0].upper(), unquote(parts[1])

            headers = {}
            while True:
                header_line = await asyncio.wait_for(reader.readline(), _HEADER_TIMEOUT)
                if not header_line or header_line == b"\r\n":
                    break
                if b":" not in header_line:
                    continue
                key, value = header_line.decode().strip().split(":", 1)
                headers[key.lower()] = value.strip()

            if (
                headers.get("upgrade", "").lower() == "websocket"
                and path in self.ws_routes
            ):
                await self._handle_websocket(reader, writer, path, headers)
                return

            request = await self._create_request(
                reader, writer, method, path, headers, addr
            )
            if not request:
                return

            # Pipeline Execution
            handler = self._build_pipeline()
            response = await handler(request)

            # Sending Response
            await self._send_response(writer, response)

        except asyncio.TimeoutError:
            # Normal behavior for keep-alive/pre-opened connections that don't send data
            pass
        except OSError as e:
            # Ignora erros de desconexão comuns (EPIPE=32, ECONNRESET=104)
            if e.args[0] in (32, 104):
                self.logger.log(f"Connection closed by peer: {e}", "DEBUG")
            elif e.args[0] == 23:  # EMFILE: Too many open files
                self.logger.log(f"System limit reached (EMFILE): {e}", "WARNING")
                try:
                    await self._send_response(
                        writer, Response.error("Service Unavailable", 503)
                    )
                except:
                    pass
            else:
                sys.print_exception(e)
                self.logger.log(f"Server Error: {repr(e)}", "ERROR")
        except Exception as e:
            sys.print_exception(e)
            self.logger.log(f"Server Error: {repr(e)}", "ERROR")
        finally:
            self.conns -= 1
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
            )
            return None

        body = None
        if content_length > 0:
            if content_length > self.max_body_size:
                await self._send_response(
                    writer,
                    Response.plain("Payload Too Large", 413),
                )
                return None
            body = await reader.read(content_length)

        request = Request(method, path, headers, addr[0])
        request.body = body
        return request

    async def _send_response(self, writer, response):
        reason = self._reason_phrase(response.status)
        writer.write(f"HTTP/1.1 {response.status} {reason}\r\n".encode())
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
        writer.write(f"{len(chunk):x}\r\n".encode())
        writer.write(chunk)
        writer.write(b"\r\n")
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
