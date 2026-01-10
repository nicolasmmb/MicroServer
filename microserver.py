import sys
import json
import os
import uasyncio as asyncio

from http import Request, Response
from websocket import WebSocket
from utils import CHUNK_SIZE, Logger, get_mime_type, unquote


class MicroServer:
    def __init__(self, port=80, config=None):
        self.port = port
        self.config = config or {}
        self.routes = []
        self.ws_routes = {}
        self.middlewares = []
        self.logger = Logger(enabled=self.config.get("logging", True))
        self.conns = 0
        self.max_conns = self.config.get("max_conns", 4)

    def add_middleware(self, mw):
        self.middlewares.append(mw)

    def route(self, path, methods=["GET"]):
        def decorator(handler):
            self.routes.append((path, methods, handler))
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
        async def static_handler(req):
            file_path = req.path.replace(url_path, dir_path, 1)
            if ".." in file_path:
                return Response("Forbidden", 403, content_type="text/plain")
            try:
                os.stat(file_path)
            except OSError:
                return Response("Not Found", 404, content_type="text/plain")

            return self.send_file(file_path)

        self.route(url_path, methods=["GET"])(static_handler)

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
            line = await asyncio.wait_for(reader.readline(), 5)
            if not line:
                return

            parts = line.decode().strip().split()
            if len(parts) < 2:
                return

            method, path = parts[0].upper(), unquote(parts[1])

            headers = {}
            while True:
                h_line = await asyncio.wait_for(reader.readline(), 2)
                if not h_line or h_line == b"\r\n":
                    break
                if b":" not in h_line:
                    continue
                k, v = h_line.decode().strip().split(":", 1)
                headers[k.lower()] = v.strip()

            if (
                headers.get("upgrade", "").lower() == "websocket"
                and path in self.ws_routes
            ):
                ws = WebSocket(reader, writer)
                if not await ws.accept(headers):
                    await self._send_response(
                        writer,
                        Response(
                            "Bad WebSocket handshake", 400, content_type="text/plain"
                        ),
                    )
                    return

                self.logger.log(f"WS Connect: {path}")
                try:
                    await self.ws_routes[path](ws)
                except Exception as e:
                    self.logger.log(f"WS Error: {e}", "ERROR")
                return

            cl_header = headers.get("content-length")
            try:
                cl = int(cl_header) if cl_header else 0
            except ValueError:
                await self._send_response(
                    writer,
                    Response("Invalid Content-Length", 400, content_type="text/plain"),
                )
                return

            body = None
            if cl > 0:
                max_body = self.config.get("max_body_size", 10240)
                if cl > max_body:
                    await self._send_response(
                        writer,
                        Response("Payload Too Large", 413, content_type="text/plain"),
                    )
                    return
                body = await reader.read(cl)

            req = Request(method, path, headers, addr[0])
            req.body = body

            async def dispatch(request):
                handler = None
                for r_path, r_methods, r_handler in self.routes:
                    if request.method not in r_methods:
                        continue
                    if r_path == request.path:
                        handler = r_handler
                        break
                    if (
                        "static_handler" in r_handler.__name__
                        and request.path.startswith(r_path)
                    ):
                        handler = r_handler
                        break

                if handler is None:
                    return Response('{"error": "Not Found"}', 404)

                res = await handler(request)
                if isinstance(res, Response):
                    return res
                if hasattr(res, "__aiter__"):
                    return Response(res)
                if hasattr(res, "__iter__") and hasattr(res, "__next__"):
                    return Response(res)
                if isinstance(res, (dict, list)):
                    return Response(json.dumps(res))
                return Response(str(res), content_type="text/html")

            handler_chain = dispatch
            for mw in reversed(self.middlewares):
                handler_chain = self._wrap_middleware(mw, handler_chain)

            try:
                resp = await handler_chain(req)
            except Exception as e:
                sys.print_exception(e)
                self.logger.log(f"Handler Error: {e}", "ERROR")
                resp = Response(f'{{"error": "Internal Error"}}', 500)

            await self._send_response(writer, resp)

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

    def _wrap_middleware(self, mw, next_handler):
        async def wrapped(req):
            return await mw(req, next_handler)

        return wrapped

    async def _send_response(self, writer, resp):
        reason = self._reason_phrase(resp.status)
        writer.write(f"HTTP/1.1 {resp.status} {reason}\r\n".encode())
        writer.write(b"Connection: close\r\n")
        writer.write(f"Content-Type: {resp.content_type}\r\n".encode())
        for k, v in resp.headers.items():
            writer.write(f"{k}: {v}\r\n".encode())

        if hasattr(resp.body, "__aiter__") or hasattr(resp.body, "__next__"):
            writer.write(b"Transfer-Encoding: chunked\r\n\r\n")
            gen = resp.body
            if hasattr(gen, "__aiter__"):
                async for chunk in gen:
                    await self._write_chunk(writer, chunk)
            else:
                for chunk in gen:
                    await self._write_chunk(writer, chunk)
            writer.write(b"0\r\n\r\n")
        else:
            payload = resp.body
            if isinstance(payload, str):
                payload = payload.encode()
            writer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode())
            writer.write(payload)
        await writer.drain()

    async def _write_chunk(self, writer, chunk):
        if chunk:
            if isinstance(chunk, str):
                chunk = chunk.encode()
            writer.write(f"{len(chunk):x}\r\n".encode())
            writer.write(chunk)
            writer.write(b"\r\n")
            await writer.drain()

    async def start(self):
        self.logger.log(f"Server started on port {self.port}")
        return await asyncio.start_server(self._handle_request, "0.0.0.0", self.port)

    def _reason_phrase(self, status):
        phrases = {
            200: "OK",
            204: "No Content",
            400: "Bad Request",
            404: "Not Found",
            413: "Payload Too Large",
            500: "Internal Server Error",
        }
        return phrases.get(status, "")
