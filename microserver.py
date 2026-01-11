import sys
import json
import os
import uasyncio as asyncio
from micropython import const


from http import Request, Response
from websocket import WebSocket
from utils import CHUNK_SIZE, Logger, get_mime_type, unquote


_DEFAULT_MAX_BODY_SIZE = const(10240)
_DEFAULT_MAX_CONNS = const(4)
_READLINE_TIMEOUT = const(5)  # seconds
_HEADER_TIMEOUT = const(2)  # seconds
_PHRASES = {
    200: "OK",
    204: "No Content",
    400: "Bad Request",
    404: "Not Found",
    413: "Payload Too Large",
    500: "Internal Server Error",
}


from routing import Router

class MicroServer:
    def __init__(self, port=80, config=None):
        self.port = port
        self.config = config or {}
        self.router = Router()
        self.ws_routes = {}
        self.middlewares = []
        self.logger = Logger(enabled=self.config.get("logging", True))
        self.conns = 0
        self.max_conns = self.config.get("max_conns", _DEFAULT_MAX_CONNS)

    def add_middleware(self, middleware):
        self.middlewares.append(middleware)

    def route(self, path, methods=None):
        if methods is None:
            methods = ("GET",)
        def decorator(handler):
            for method in methods:
                self.router.add(method, path, handler)
            return handler

        return decorator

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

    def options(self, path):
        return self.route(path, methods=["OPTIONS"])

    def websocket(self, path):
        def decorator(handler):
            self.ws_routes[path] = handler
            return handler

        return decorator

    def mount_static(self, url_path, dir_path):
        async def static_handler(request):
            file_path = request.path.replace(url_path, dir_path, 1)
            if ".." in file_path:
                return Response("Forbidden", 403, content_type="text/plain")
            try:
                os.stat(file_path)
            except OSError:
                return Response("Not Found", 404, content_type="text/plain")

            return self.send_file(file_path)

        self.route(url_path, methods=["GET"])(static_handler)
        self.router.add_static(url_path, static_handler)

    def send_file(self, filename):
        async def file_gen():
            with open(filename, "rb") as f:
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    yield data

        return Response(file_gen(), content_type=get_mime_type(filename))

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
                websocket = WebSocket(reader, writer)
                if not await websocket.accept(headers):
                    await self._send_response(
                        writer,
                        Response(
                            "Bad WebSocket handshake", 400, content_type="text/plain"
                        ),
                    )
                    return

                self.logger.log(f"WS Connect: {path}")
                try:
                    await self.ws_routes[path](websocket)
                except Exception as e:
                    self.logger.log(f"WS Error: {e}", "ERROR")
                return

            content_length_header = headers.get("content-length")
            try:
                content_length = int(content_length_header) if content_length_header else 0
            except ValueError:
                await self._send_response(
                    writer,
                    Response("Invalid Content-Length", 400, content_type="text/plain"),
                )
                return

            body = None
            if content_length > 0:
                max_body = self.config.get("max_body_size", _DEFAULT_MAX_BODY_SIZE)
                if content_length > max_body:
                    await self._send_response(
                        writer,
                        Response("Payload Too Large", 413, content_type="text/plain"),
                    )
                    return
                body = await reader.read(content_length)

            request = Request(method, path, headers, addr[0])
            request.body = body

            async def dispatch(request):
                handler, params = self.router.match(request.method, request.path)

                if handler is None:
                    return Response('{"error": "Not Found"}', 404)

                if params is not None:
                    request.path_params = params

                result = await handler(request)
                if isinstance(result, Response):
                    return result
                if isinstance(result, (dict, list)):
                    return Response(json.dumps(result))
                if self._is_streaming_body(result):
                    return Response(result)
                return Response(str(result), content_type="text/html")

            handler_chain = dispatch
            for middleware in reversed(self.middlewares):
                middleware_ref = middleware
                next_handler = handler_chain

                async def handler_chain(request, current_middleware=middleware_ref, next_call=next_handler):
                    return await current_middleware(request, next_call)

            try:
                response = await handler_chain(request)
            except Exception as e:
                sys.print_exception(e)
                self.logger.log(f"Handler Error: {e}", "ERROR")
                response = Response('{"error": "Internal Error"}', 500)

            await self._send_response(writer, response)

        except Exception as e:
            self.logger.log(f"Server Error: {e}", "ERROR")
        finally:
            self.conns -= 1
            try:
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except:
                pass

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

    async def run(self, host="0.0.0.0", port=None):
        if port is not None:
            self.port = port
        self.logger.log(f"Server started on port {self.port}")
        return await asyncio.start_server(self._handle_request, host, self.port)

    def _reason_phrase(self, status):
        return _PHRASES.get(status, "")

    def _is_streaming_body(self, body):
        if body is None:
            return False
        if hasattr(body, "__aiter__"):
            return True
        if hasattr(body, "__next__"):
            return True
        if hasattr(body, "__iter__") and not isinstance(body, (bytes, bytearray, str)):
            return True
        return False


class MicroServer:
