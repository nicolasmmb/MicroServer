# MicroServer

**MicroServer** is a minimalist, asynchronous HTTP/WebSocket server designed for **MicroPython** (tested on ESP32). It features decorator-based routing, middleware support, dynamic path parameters, static file serving, Server-Sent Events (SSE), and WebSocket helpers — all with a low memory footprint.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Via mip (Recommended)](#via-mip-recommended)
  - [Manual Installation](#manual-installation)
  - [Development Setup (Contributing)](#development-setup-contributing)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [API Reference](#api-reference)
  - [MicroServer](#microserver-class)
  - [Request](#request-object)
  - [Response](#response-object)
  - [WebSocket](#websocket-object)
  - [Middleware](#middleware)
  - [Loggers](#loggers)
- [Routing](#routing)
- [Middleware](#middleware-1)
- [Responses](#responses)
- [Streaming](#streaming)
- [Server-Sent Events (SSE)](#server-sent-events-sse)
- [WebSockets](#websockets)
- [Static Files](#static-files)
- [Configuration Reference](#configuration-reference)
- [Examples](#examples)
  - [Basic](#basic-example)
  - [Medium (Middleware + Files)](#medium-example)
  - [Full (WiFi + Hardware + WebSocket)](#full-example)
  - [SSE Sensor Monitor](#sse-sensor-monitor)
  - [SSE Dashboard](#sse-dashboard)
- [Production Guide](#production-guide)
- [Security](#security)
- [Architecture](#architecture)
- [File Structure](#file-structure)

---

## Features

| Feature              | Description                                                      |
| -------------------- | ---------------------------------------------------------------- |
| **Async**            | Built on `uasyncio` — non-blocking, handles multiple connections |
| **Routing**          | Flask-style decorators with dynamic segments (`/user/<id>`)      |
| **Middleware**       | Composable pipeline: CORS, Logging, or custom                    |
| **WebSocket**        | RFC 6455 compliant with ping/pong keepalive and close handshake  |
| **SSE**              | Server-Sent Events for real-time push to browsers                |
| **Static Files**     | File serving with path traversal protection and `Cache-Control`  |
| **Keep-Alive**       | HTTP persistent connections for reduced latency                  |
| **DoS Protection**   | Slowloris defense, header bomb prevention, request size limits   |
| **RFC Compliant**    | Full HTTP/1.1 (RFC 7230-7235) and WebSocket (RFC 6455)           |
| **Memory Efficient** | `__slots__`, generators, lazy parsing, cached pipelines          |

---

## Installation

### Via mip (Recommended)

For devices with internet access (e.g., ESP32 connected to Wi-Fi):

```python
import mip
mip.install("github:nicolasmmb/MicroServer")
```

This installs all required files to your device's `/lib` folder automatically.

### Manual Installation

Copy these files to the `/lib` folder on your device:

```
microserver.py   ← Core server
http.py          ← Request / Response classes
routing.py       ← Trie-based routing engine
middleware.py    ← CORS + Logging middleware
websocket.py     ← RFC 6455 WebSocket implementation
utils.py         ← Logger, URL decode, MIME types
```

**Using Thonny:** Open each file and use **File → Save as...** selecting your MicroPython device, saving to `/lib/<filename>`.

### Development Setup (Contributing)

To run the test suite locally (requires CPython 3.10+):

```bash
# Clone the repository
git clone https://github.com/nicolasmmb/MicroServer.git
cd MicroServer

# Run tests (no extra dependencies needed — tests use stdlib only)
python tests/test_syntax.py
python tests/test_functional.py
python tests/test_sse.py
python tests/test_micropython_compat.py
```

The test files include MicroPython shims (`uasyncio`, `ubinascii`, `uhashlib`, `const`) so they run on standard CPython.

---

## Quick Start

Create a `main.py` on your device:

```python
import uasyncio as asyncio
from microserver import MicroServer
from http import Response

app = MicroServer(port=80)

@app.get("/")
async def index(req):
    return Response.json({"message": "Hello from MicroServer!"})

@app.post("/echo")
async def echo(req):
    return Response.json({"received": req.json})

asyncio.run(app.run())
```

Access via browser or curl:

```bash
curl http://<device-ip>/
# {"message": "Hello from MicroServer!"}

curl -X POST http://<device-ip>/echo \
     -H "Content-Type: application/json" \
     -d '{"hello": "world"}'
# {"received": {"hello": "world"}}
```

---

## Core Concepts

1. **Routes** map URL patterns + HTTP methods to `async` handler functions.
2. **Handlers** receive a `Request` object and must return a `Response` object.
3. **Middleware** wraps the handler pipeline to process every request/response globally.
4. **The server** is async — it handles multiple connections concurrently via `uasyncio`.

```
Client Request
     │
     ▼
[Middleware 1] → [Middleware 2] → [Route Handler]
                                         │
                                         ▼
                                    Response object
                                         │
     ◀────────────────────────────────────
     HTTP response sent to client
```

---

## API Reference

### MicroServer Class

```python
from microserver import MicroServer

app = MicroServer(port=80, logger=None, router=None, max_conns=10)
```

**Constructor Parameters:**

| Parameter   | Type     | Default           | Description                                        |
| ----------- | -------- | ----------------- | -------------------------------------------------- |
| `port`      | `int`    | `80`              | TCP port to listen on                              |
| `logger`    | `Logger` | `ConsoleLogger()` | Logger instance (see [Loggers](#loggers))          |
| `router`    | `Router` | `Router()`        | Custom router (rarely needed)                      |
| `max_conns` | `int`    | `10`              | Max simultaneous connections (ESP32 limit: ~10-16) |

**Instance Attributes (configurable):**

| Attribute                     | Default             | Description                                        |
| ----------------------------- | ------------------- | -------------------------------------------------- |
| `app.max_body_size`           | `1048576` (1MB)     | Max request body size in bytes                     |
| `app.keep_alive_timeout`      | `5`                 | HTTP keep-alive idle timeout (seconds)             |
| `app.max_keep_alive_requests` | `100`               | Max requests per keep-alive connection             |
| `app.body_timeout`            | `30`                | Body read timeout — Slowloris protection (seconds) |
| `app.server_name`             | `"MicroServer/1.0"` | Value of the `Server` response header              |

**Methods:**

```python
# Route decorators
app.get(path)           # Register GET handler
app.post(path)          # Register POST handler
app.put(path)           # Register PUT handler
app.delete(path)        # Register DELETE handler
app.patch(path)         # Register PATCH handler
app.route(path, methods=["GET"])  # Register multiple methods at once

# WebSocket
app.websocket(path)     # Register WebSocket handler

# Static files
app.mount_static(url_path, dir_path, max_age=3600)

# Middleware
app.add_middleware(middleware_instance)

# Start server
await app.run(host="0.0.0.0", port=None)   # Blocks until stopped
await app.start()                            # Returns server object
```

---

### Request Object

Passed to every route handler as the first argument.

```python
@app.get("/example/<item_id>")
async def handler(req):
    # req is a Request instance
    ...
```

**Attributes:**

| Attribute          | Type    | Description                                         |
| ------------------ | ------- | --------------------------------------------------- |
| `req.method`       | `str`   | HTTP method: `"GET"`, `"POST"`, etc.                |
| `req.path`         | `str`   | URL path without query string: `"/users/42"`        |
| `req.headers`      | `dict`  | All request headers (lowercase keys)                |
| `req.body`         | `bytes` | Raw request body (`None` if no body)                |
| `req.ip`           | `str`   | Client IP address                                   |
| `req.path_params`  | `dict`  | Dynamic path segments: `{"item_id": "42"}`          |
| `req.query_params` | `dict`  | Query string parameters: `{"page": "2"}`            |
| `req.json`         | `dict`  | Lazily parsed JSON body (`None` if invalid/missing) |

**Examples:**

```python
@app.get("/users/<user_id>")
async def get_user(req):
    uid = req.path_params["user_id"]        # Path param
    page = req.query_params.get("page", "1") # Query param ?page=1
    auth = req.headers.get("authorization")  # Header
    return Response.json({"id": uid, "page": page})

@app.post("/data")
async def post_data(req):
    body = req.json                          # Parsed JSON dict
    raw = req.body                           # Raw bytes
    return Response.json({"ok": True})
```

---

### Response Object

All route handlers **must** return a `Response` instance. Use the factory class methods:

```python
from http import Response
```

**Factory Methods:**

```python
# JSON response (Content-Type: application/json)
Response.json(data: dict, status: int = 200)

# HTML response (Content-Type: text/html)
Response.html(content: str, status: int = 200)

# Plain text (Content-Type: text/plain)
Response.plain(content: str, status: int = 200)

# Error — returns JSON: {"error": message, "code": status}
Response.error(message: str, status: int = 400)

# Redirect (302 with Location header)
Response.redirect(location: str)

# Streaming (chunked transfer encoding)
Response.stream(generator, content_type: str = "text/plain")

# Server-Sent Events
Response.sse(generator)
```

**Adding Custom Headers:**

```python
@app.get("/protected")
async def protected(req):
    resp = Response.json({"data": "secret"})
    resp.add_header("X-Custom-Header", "value")
    resp.add_header("Cache-Control", "no-store")
    return resp
```

**Examples:**

```python
# 200 OK JSON
return Response.json({"users": [1, 2, 3]})

# 201 Created
return Response.json({"id": 42}, status=201)

# 204 No Content
return Response.plain("", status=204)

# 400 Bad Request
return Response.error("Missing required field: name", 400)

# 401 Unauthorized
return Response.json({"error": "Invalid token"}, status=401)

# 404 Not Found
return Response.error("User not found", 404)

# HTML page
return Response.html("<h1>Hello World</h1>")

# Redirect to /login
return Response.redirect("/login")
```

---

### WebSocket Object

Passed to `@app.websocket` handlers. **Do not** call `accept()` manually — it is called automatically by the server.

```python
@app.websocket("/ws")
async def ws_handler(ws):
    # ws is a WebSocket instance — already accepted
    ...
```

**Methods:**

```python
await ws.send(data)          # Send text (str) or binary (bytes)
msg = await ws.receive()     # Receive message; returns None on disconnect
await ws.close(code=1000, reason="")  # Graceful close
```

**Properties:**

| Property           | Description                            |
| ------------------ | -------------------------------------- |
| `ws.closed`        | `True` if connection is closed         |
| `ws.ping_interval` | Ping interval in seconds (default: 30) |

**Notes:**

- Ping/pong keepalive runs automatically every 30 seconds
- Connection closes automatically if no pong is received within 60 seconds
- `ws.receive()` returns `None` when the client disconnects

---

### WebSocket Object

---

### Middleware

Middleware intercepts every request before the handler runs and can modify the request/response.

**Built-in Middleware:**

```python
from middleware import LoggingMiddleware, CORSMiddleware

# Logging: prints method, path, status, duration to console
app.add_middleware(LoggingMiddleware())

# Logging with custom logger
from utils import FileLogger
app.add_middleware(LoggingMiddleware(logger=FileLogger("api.log")))

# CORS: handles OPTIONS preflight + adds headers to all responses
app.add_middleware(CORSMiddleware(
    origins="*",
    methods="GET,POST,PUT,DELETE,OPTIONS",
    headers="Content-Type,Authorization",
    allow_credentials=False
))
```

**Custom Middleware:**

```python
class AuthMiddleware:
    async def __call__(self, request, next_handler):
        token = request.headers.get("authorization", "")
        if not token.startswith("Bearer valid-token"):
            from http import Response
            return Response.error("Unauthorized", 401)
        return await next_handler(request)

app.add_middleware(AuthMiddleware())
```

Middleware executes in the order it is added (first added = outermost = runs first on request, last on response).

---

### Loggers

```python
from utils import ConsoleLogger, FileLogger, NoOpLogger

# Console (default) — prints to stdout
logger = ConsoleLogger()

# File — writes to file, rotates at max_size bytes
logger = FileLogger(filepath="api.log", max_size=10240)  # 10KB rotation

# No-Op — silences all logging
logger = NoOpLogger()

app = MicroServer(port=80, logger=logger)
```

**Custom Logger:**

```python
from utils import Logger

class MyLogger(Logger):
    def log(self, msg, level="INFO"):
        # level: "INFO", "DEBUG", "WARNING", "ERROR"
        print(f"[{level}] {msg}")

app = MicroServer(port=80, logger=MyLogger())
```

---

## Routing

### Static Routes

```python
@app.get("/")
async def index(req):
    return Response.json({"status": "ok"})

@app.post("/users")
async def create_user(req):
    return Response.json({"created": True}, status=201)

@app.put("/users/<id>")
async def update_user(req):
    return Response.json({"updated": req.path_params["id"]})

@app.delete("/users/<id>")
async def delete_user(req):
    return Response.plain("", status=204)

@app.patch("/users/<id>")
async def patch_user(req):
    return Response.json({"patched": True})
```

### Dynamic Routes

Wrap segments in `<angle_brackets>` to capture path parameters:

```python
@app.get("/users/<user_id>")
async def get_user(req):
    uid = req.path_params["user_id"]
    return Response.json({"id": uid})

@app.get("/posts/<post_id>/comments/<comment_id>")
async def get_comment(req):
    post_id = req.path_params["post_id"]
    comment_id = req.path_params["comment_id"]
    return Response.json({"post": post_id, "comment": comment_id})
```

### Multi-Method Routes

```python
@app.route("/resource", methods=["GET", "POST"])
async def resource(req):
    if req.method == "GET":
        return Response.json({"items": []})
    elif req.method == "POST":
        return Response.json({"created": True}, status=201)
```

### Query Parameters

Query strings are parsed automatically:

```python
# GET /search?q=esp32&page=2
@app.get("/search")
async def search(req):
    query = req.query_params.get("q", "")
    page = int(req.query_params.get("page", 1))
    return Response.json({"query": query, "page": page})
```

---

## Middleware

### Execution Order

Middleware runs in the order it is added. The first middleware added is the outermost layer:

```python
app.add_middleware(LoggingMiddleware())   # Runs first on request
app.add_middleware(CORSMiddleware(...))  # Runs second
# Route handler runs last
```

### CORSMiddleware

```python
from middleware import CORSMiddleware

app.add_middleware(CORSMiddleware(
    origins="*",                                    # Allowed origins (* = all)
    methods="GET,POST,PUT,DELETE,OPTIONS",           # Allowed methods
    headers="Content-Type,Authorization",            # Allowed headers
    allow_credentials=False                          # Allow credentials
))
```

- Automatically handles `OPTIONS` preflight requests (returns 204 immediately)
- Adds `Access-Control-Allow-*` headers to all responses
- Headers are pre-calculated at init time for performance

### LoggingMiddleware

```python
from middleware import LoggingMiddleware

app.add_middleware(LoggingMiddleware())
# Output: [INFO] 2024-01-15 10:30:45 | 192.168.1.50 | GET /api/data | 200 | 1.2ms
```

---

## Responses

### JSON

```python
return Response.json({"key": "value"})
return Response.json({"users": [1, 2]}, status=200)
return Response.json({"error": "not found"}, status=404)
```

### HTML

```python
return Response.html("""
<!DOCTYPE html>
<html><body><h1>Hello!</h1></body></html>
""")
```

### Plain Text

```python
return Response.plain("OK")
return Response.plain("Not Found", status=404)
```

### Error

```python
# Returns JSON: {"error": "message", "code": 400}
return Response.error("Bad request", 400)
return Response.error("Not found", 404)
return Response.error("Internal error", 500)
```

### Redirect

```python
return Response.redirect("/new-path")      # 302
```

### Custom Headers

```python
resp = Response.json({"data": "..."})
resp.add_header("X-Rate-Limit", "100")
resp.add_header("X-Request-Id", "abc123")
return resp
```

---

## Streaming

Use `Response.stream()` when the response body is large — avoids loading everything into RAM at once. Sends with `Transfer-Encoding: chunked`.

**Async generator (recommended on ESP32):**

```python
@app.get("/large")
async def large(req):
    async def generate():
        for i in range(1000):
            yield f"Line {i}\n"
            await asyncio.sleep(0)  # Yield control to event loop

    return Response.stream(generate(), content_type="text/plain")
```

**Sync generator:**

```python
@app.get("/file")
async def serve_file(req):
    def read_chunks():
        with open("/data/large.csv", "rb") as f:
            while True:
                chunk = f.read(512)
                if not chunk:
                    break
                yield chunk

    return Response.stream(read_chunks(), content_type="text/csv")
```

**Using `send_file` helper:**

```python
@app.get("/download")
async def download(req):
    return app.send_file("/flash/data/report.csv")
```

---

## Server-Sent Events (SSE)

SSE allows the server to push real-time updates to the browser over a single long-lived HTTP connection. The browser reconnects automatically if the connection drops.

**Browser side (JavaScript):**

```javascript
const events = new EventSource("/events");
events.onmessage = (e) => {
  const data = JSON.parse(e.data);
  console.log(data);
};
events.onerror = () => console.log("Reconnecting...");
```

**Server side (MicroPython):**

```python
import ujson
import uasyncio as asyncio
from http import Response

@app.get("/events")
async def events(req):
    async def stream():
        while True:
            data = {"temperature": read_sensor(), "time": time.time()}
            yield f"data: {ujson.dumps(data)}\n\n"
            await asyncio.sleep(2)   # Send every 2 seconds

    return Response.sse(stream())
```

**SSE Event Format:**

Each event must end with `\n\n` (double newline). Optional fields:

```
data: {"value": 42}\n\n               ← Simple data event
event: temperature\ndata: 25.5\n\n    ← Named event (client: events.addEventListener('temperature', ...))
id: 1\ndata: hello\n\n                ← With event ID (for reconnection)
```

**Notes:**

- `Response.sse()` automatically sets `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and `X-Accel-Buffering: no`
- Uses raw streaming (no chunked encoding) for immediate delivery
- Each `await writer.drain()` flushes the event immediately to the client
- The generator runs indefinitely — the connection closes only when the client disconnects or the generator ends

---

## WebSockets

Full RFC 6455 compliance with automatic ping/pong keepalive.

### Basic Echo Server

```python
@app.websocket("/ws")
async def ws_echo(ws):
    await ws.send("Connected!")

    while True:
        msg = await ws.receive()
        if msg is None:
            break  # Client disconnected
        await ws.send(f"Echo: {msg}")
```

### Broadcast Pattern

```python
clients = []

@app.websocket("/ws/chat")
async def ws_chat(ws):
    clients.append(ws)
    try:
        while True:
            msg = await ws.receive()
            if msg is None:
                break
            # Broadcast to all connected clients
            for client in clients[:]:
                try:
                    await client.send(msg)
                except Exception:
                    clients.remove(client)
    finally:
        if ws in clients:
            clients.remove(ws)
```

### Binary Data

```python
@app.websocket("/ws/binary")
async def ws_binary(ws):
    while True:
        data = await ws.receive()
        if data is None:
            break
        if isinstance(data, bytes):
            # Process binary frame
            await ws.send(bytes([b ^ 0xFF for b in data]))  # Invert bits
```

### Graceful Close

```python
@app.websocket("/ws")
async def ws_handler(ws):
    msg = await ws.receive()
    if msg == "bye":
        await ws.close(1000, "Normal closure")
        return
    await ws.send(f"Got: {msg}")
```

### Browser JavaScript Client

```javascript
const ws = new WebSocket("ws://192.168.1.100/ws");
ws.onopen = () => ws.send("Hello!");
ws.onmessage = (e) => console.log("Received:", e.data);
ws.onclose = () => console.log("Disconnected");
ws.onerror = (e) => console.error("Error:", e);
```

---

## Static Files

Serve files directly from the device's flash storage.

### Mount a Directory

```python
# Maps /static/... → /flash/www/...
app.mount_static("/static", "/flash/www")

# With custom cache duration (default 3600 = 1 hour)
app.mount_static("/assets", "/flash/assets", max_age=86400)  # 1 day
```

### Serve a Single File

```python
@app.get("/favicon.ico")
async def favicon(req):
    return app.send_file("/flash/www/favicon.ico")
```

**Security:** Path traversal (`..`) is automatically blocked — returns 403.

**MIME Types Supported:** `.html`, `.css`, `.js`, `.json`, `.txt`, `.png`, `.jpg`, `.ico`, `.svg`

---

## Configuration Reference

```python
from microserver import MicroServer
from utils import ConsoleLogger

app = MicroServer(
    port=80,
    max_conns=8,                    # Max simultaneous connections
    logger=ConsoleLogger(),         # Logger instance
)

# Body & request limits
app.max_body_size = 8192           # 8KB max body (default: 1MB)
app.body_timeout = 30              # Body read timeout in seconds (default: 30)

# Keep-Alive (HTTP persistent connections)
app.keep_alive_timeout = 5         # Idle timeout in seconds (default: 5)
app.max_keep_alive_requests = 100  # Max requests per connection (default: 100)

# Server identification
app.server_name = "MyDevice/1.0"   # Server header value

# Static files
app.mount_static("/static", "/www", max_age=3600)

# Middleware
from middleware import LoggingMiddleware, CORSMiddleware
app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware(origins="*", methods="*"))
```

**Built-in Limits (not configurable, compile-time constants):**

| Constant                | Value | Protection        |
| ----------------------- | ----- | ----------------- |
| Max headers per request | 50    | Header bomb       |
| Max header line size    | 8 KB  | Header bomb       |
| Max request line        | 8 KB  | URI too long      |
| Max WebSocket frame     | 64 KB | Frame bomb        |
| Read chunk size         | 512 B | Memory efficiency |

---

## Examples

### Basic Example

```python
# examples/basic.py
import uasyncio as asyncio
from microserver import MicroServer
from http import Response

app = MicroServer(port=80)

@app.get("/")
async def hello(req):
    return Response.json({"message": "Hello from MicroServer"})

@app.post("/echo")
async def echo(req):
    if not req.body:
        return Response.error("Empty body", 400)
    return Response.plain(req.body.decode())

@app.get("/stream")
async def stream(req):
    async def gen():
        for i in range(5):
            await asyncio.sleep(0.5)
            yield f"chunk {i}\n"
    return Response.stream(gen(), content_type="text/plain")

asyncio.run(app.run())
```

### Medium Example

```python
# examples/medium.py — Middleware, JSON processing, static files
import uasyncio as asyncio
from microserver import MicroServer
from middleware import LoggingMiddleware, CORSMiddleware
from http import Response

app = MicroServer(port=80)
app.max_body_size = 4096  # 4KB limit

app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware(
    origins="*",
    methods="GET,POST,OPTIONS",
    headers="Content-Type,Authorization"
))

@app.get("/status")
async def status(req):
    return Response.json({"ok": True, "ip": req.ip})

@app.post("/sum")
async def sum_numbers(req):
    data = req.json or {}
    try:
        a = float(data.get("a", 0))
        b = float(data.get("b", 0))
        return Response.json({"result": a + b})
    except (ValueError, TypeError):
        return Response.error("Invalid numbers provided", 400)

# Serve files from flash
app.mount_static("/static", "/flash/www")

asyncio.run(app.run())
```

### Full Example

```python
# examples/full.py — WiFi, hardware control, WebSocket
import uasyncio as asyncio
import gc
import machine
import network
import time

from microserver import MicroServer
from middleware import LoggingMiddleware, CORSMiddleware
from http import Response

SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
LED_PIN = 2  # ESP32 onboard LED

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > 10:
                return False
            time.sleep(1)
    print("IP:", wlan.ifconfig()[0])
    return True

app = MicroServer(port=80, max_conns=8)
app.max_body_size = 4096
app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware(origins="*", methods="*"))

@app.get("/")
async def index(req):
    return Response.json({
        "status": "online",
        "memory_free": gc.mem_free()
    })

@app.get("/gc")
async def run_gc(req):
    before = gc.mem_free()
    gc.collect()
    return Response.json({"freed": gc.mem_free() - before, "free": gc.mem_free()})

@app.post("/led")
async def led_control(req):
    data = req.json or {}
    state = data.get("state")
    if state is None:
        return Response.error("Missing 'state' field", 400)
    pin = machine.Pin(LED_PIN, machine.Pin.OUT)
    value = 1 if state in (1, True, "on") else 0
    pin.value(value)
    return Response.json({"led": "on" if value else "off"})

@app.websocket("/ws/echo")
async def ws_echo(ws):
    await ws.send("Welcome!")
    while True:
        msg = await ws.receive()
        if msg is None:
            break
        await ws.send(f"Echo: {msg}")

async def main():
    if not connect_wifi(SSID, PASSWORD):
        print("WiFi failed")
        return
    asyncio.create_task(app.run())
    while True:
        await asyncio.sleep(60)
        gc.collect()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped")
```

### SSE Sensor Monitor

```python
# examples/sse_simple.py — Real-time sensor dashboard
import time
import ujson
import uasyncio as asyncio
from microserver import MicroServer
from http import Response

app = MicroServer(port=80)

def read_sensor():
    import urandom
    return {
        "temperature": 20 + urandom.randint(0, 10),
        "humidity": 50 + urandom.randint(0, 30),
        "timestamp": time.time(),
    }

@app.get("/")
async def index(req):
    return Response.html("""
<!DOCTYPE html>
<html>
<head><title>Sensor Monitor</title></head>
<body>
    <h1>Sensor Monitor (SSE)</h1>
    <p>Temperature: <strong id="temp">--</strong>°C</p>
    <p>Humidity: <strong id="hum">--</strong>%</p>
    <script>
        const es = new EventSource('/events');
        es.onmessage = (e) => {
            const d = JSON.parse(e.data);
            document.getElementById('temp').textContent = d.temperature;
            document.getElementById('hum').textContent = d.humidity;
        };
    </script>
</body>
</html>
""")

@app.get("/events")
async def events(req):
    async def stream():
        while True:
            data = read_sensor()
            yield f"data: {ujson.dumps(data)}\n\n"
            await asyncio.sleep(2)
    return Response.sse(stream())

asyncio.run(app.run())
```

### SSE Dashboard

See [`examples/sse_dashboard.py`](examples/sse_dashboard.py) for a complete production-like dashboard featuring:

- Real-time sales tracking for a vending machine
- Stock monitoring with low-stock alerts
- REST API + SSE combined
- Auto-sales simulator background task
- Rich HTML5/CSS UI with CSS Grid

---

## Production Guide

### 1. Memory Management

```python
import gc

# Limit body size to prevent OOM
app.max_body_size = 4096  # 4KB is plenty for most IoT APIs

# Periodically collect garbage in your main loop
async def main():
    asyncio.create_task(app.run())
    while True:
        await asyncio.sleep(60)
        gc.collect()
        print(f"Free RAM: {gc.mem_free()} bytes")
```

### 2. Connection Limits

```python
# ESP32 LWIP hard limit is typically 10-16 sockets
# Recommended: leave headroom for the OS
app = MicroServer(port=80, max_conns=8)
```

The server logs a warning at 80% capacity and returns `503 Service Unavailable` when full.

### 3. Security Headers

```python
@app.get("/api/data")
async def data(req):
    resp = Response.json({"data": "..."})
    resp.add_header("X-Content-Type-Options", "nosniff")
    resp.add_header("X-Frame-Options", "DENY")
    return resp
```

### 4. Graceful Shutdown

```python
import uasyncio as asyncio

async def main():
    asyncio.create_task(app.run())
    # ... rest of app

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Server stopped")
```

### 5. WiFi Reconnection

```python
import network, time

def ensure_wifi(ssid, password, timeout=30):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(ssid, password)
    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            return False
        time.sleep(1)
    return True

async def wifi_watchdog(ssid, password):
    while True:
        if not ensure_wifi(ssid, password):
            import machine
            machine.reset()  # Hard reset if WiFi fails
        await asyncio.sleep(30)
```

### 6. Complete Production Template

```python
import uasyncio as asyncio
import gc
import network
import time
import machine

from microserver import MicroServer
from middleware import LoggingMiddleware, CORSMiddleware
from http import Response
from utils import FileLogger

# Config
SSID = "MY_WIFI"
PASSWORD = "MY_PASS"

# Server
app = MicroServer(
    port=80,
    max_conns=8,
    logger=FileLogger("server.log", max_size=20480)
)

app.max_body_size = 8192
app.keep_alive_timeout = 5
app.max_keep_alive_requests = 100
app.body_timeout = 30

app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware(origins="*", methods="GET,POST,PUT,DELETE"))

app.mount_static("/static", "/www", max_age=86400)

@app.get("/health")
async def health(req):
    return Response.json({
        "status": "ok",
        "free_ram": gc.mem_free(),
        "uptime": time.time()
    })

async def main():
    # WiFi
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            break
        time.sleep(1)

    if not wlan.isconnected():
        machine.reset()

    print("IP:", wlan.ifconfig()[0])

    # Start server
    asyncio.create_task(app.run())

    # Maintenance loop
    while True:
        await asyncio.sleep(60)
        gc.collect()

try:
    asyncio.run(main())
except Exception as e:
    import sys
    sys.print_exception(e)
    machine.reset()
```

---

## Security

MicroServer includes multiple layers of protection built in:

| Threat                   | Protection                                             |
| ------------------------ | ------------------------------------------------------ |
| **Slowloris**            | Body read timeout (30s default via `app.body_timeout`) |
| **Header Bomb**          | Max 50 headers, max 8KB per header                     |
| **URI Too Long**         | Max 8KB request line → 414 response                    |
| **Large Payload**        | Configurable `max_body_size` → 413 response            |
| **Connection Flood**     | Semaphore-based `max_conns` limiting → 503 response    |
| **Path Traversal**       | `..` blocked in static file paths → 403 response       |
| **WebSocket Frame Bomb** | Max 64KB frame size                                    |
| **Invalid WebSocket**    | RSV bits validated per RFC 6455                        |
| **Broken Connection**    | EPIPE/ECONNRESET errors caught silently                |

---

## Architecture

### Request Flow

```
1. TCP accept
2. Semaphore acquire (enforces max_conns)
3. Parse request line + validate length
4. Parse headers + validate count/size
5. Read body + apply body_timeout
6. Check WebSocket upgrade
7. Create Request object
8. Middleware pipeline (LoggingMiddleware → CORSMiddleware → ...)
9. Route dispatch (Router.match → handler)
10. Build Response
11. Send response (payload / chunked / SSE)
12. Keep-Alive or close
13. Semaphore release + gc.collect()
```

### Module Dependencies

```
microserver.py
├── http.py       (Request, Response)
├── routing.py    (Router, Trie)
├── middleware.py (Pipeline, CORS, Logging)
├── websocket.py  (WebSocket)
└── utils.py      (Logger, unquote, MIME types)
```

### Router

- Uses a **Trie** data structure for O(n) route matching (n = path segments)
- Two tries per HTTP method: one for static routes, one for dynamic (`<param>`) routes
- Static prefix trie for `mount_static` (efficient prefix matching)
- LRU-style 404 cache (50 entries) prevents memory exhaustion from path scanning

### WebSocket

- RFC 6455 handshake: SHA-1 + Base64 key validation via `uhashlib`/`ubinascii`
- Background `asyncio.Task` for ping/pong (30s interval, 60s pong timeout)
- `asyncio.Lock` for thread-safe concurrent writes
- Proper close handshake: sends close frame, waits for echoed close frame

---

## File Structure

```
MicroServer/
├── microserver.py     ← Main server class (MicroServer, _Semaphore)
├── http.py            ← Request, Response, HTTP status phrases
├── routing.py         ← Router, _RouteTrie, _StaticTrie
├── middleware.py      ← MiddlewarePipeline, CORSMiddleware, LoggingMiddleware
├── websocket.py       ← WebSocket (RFC 6455)
├── utils.py           ← ConsoleLogger, FileLogger, NoOpLogger, unquote, get_mime_type
├── manifest.py        ← mip package manifest
├── package.json       ← Version and URL manifest
├── examples/
│   ├── basic.py       ← Minimal routes and streaming
│   ├── medium.py      ← Middleware, JSON API, static files
│   ├── full.py        ← WiFi, hardware (LED), WebSocket
│   ├── sse_simple.py  ← SSE sensor monitor
│   └── sse_dashboard.py ← Full SSE vending machine dashboard
└── tests/
    ├── test_syntax.py               ← Module import/syntax validation
    ├── test_functional.py           ← HTTP/WebSocket feature tests
    ├── test_sse.py                  ← SSE-specific tests
    └── test_micropython_compat.py   ← MicroPython shim tests (CPython)
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
