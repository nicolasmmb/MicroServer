# MicroServer

**MicroServer** is a minimalist, asynchronous HTTP/WebSocket server designed for MicroPython (tested on ESP32). It features decorator-based routing, robust middleware support (CORS, Logging), dynamic path parameters, static file serving, and JSON/WebSocket helpers.

Focused on **low memory footprint** and **ease of use**, it is ideal for building RESTful APIs and simple web interfaces on resource-constrained IoT devices.

## Features

*   🚀 **Asynchronous**: Built on `uasyncio` for non-blocking concurrency.
*   🛣️ **Routing**: Flask-style decorators (`@app.get`, `@app.post`) with dynamic segments (`/user/<id>`).
*   🔌 **Middleware**: Pipeline support for global request processing (CORS, Auth, Logging).
*   📂 **Static Files**: Efficient file serving with path traversal protection and `Cache-Control` headers.
*   📜 **WebSockets**: RFC 6455 compliant with ping/pong keepalive and proper close handshake.
*   ⚡ **Performance**: Efficient header parsing and memory management using `__slots__` and generators.
*   🔒 **Security**: DoS protection (Slowloris defense, header bomb prevention, request size limits).
*   📐 **RFC Compliant**: Full HTTP/1.1 (RFC 7230-7235) and WebSocket (RFC 6455) compliance.
*   🔄 **Keep-Alive**: HTTP persistent connections for reduced latency on multiple requests.

## What's New in v1.0.0

**Major Improvements:**
- ✅ **RFC 7230-7235 HTTP Compliance**: Required headers (`Date`, `Server`), proper header validation, request size limits
- ✅ **RFC 6455 WebSocket Compliance**: Ping/pong keepalive (30s interval), complete close handshake, RSV bit validation, frame size limits (64KB)
- ✅ **HTTP Keep-Alive**: Connection reuse for reduced latency (configurable timeout and max requests)
- ✅ **Atomic Connection Limiting**: Semaphore-based limiting fixes race condition that allowed >max_conns
- ✅ **DoS Protection**: Body read timeout (Slowloris defense), header count/size limits, request line size limit
- ✅ **Performance Optimizations**: Cached middleware pipeline, batched socket writes, improved error handling
- ✅ **Production Ready**: Comprehensive testing, improved resource leak prevention, errno constants

**Breaking Changes:**
- `_send_response()` signature changed (added `keep_alive` and `requests_remaining` parameters)
- WebSocket connections now have ~200 bytes additional overhead for ping/pong background task
- Connection handling internally refactored (user code unchanged)

## Installation

### Via `mip` (Recommended)
For devices with internet access:
```python
import mip
mip.install("github:nicolasmmb/MicroServer")
```

### Manual Installation
Copy the following files to your device's `/lib` folder:
- `microserver.py`: Core server logic.
- `routing.py`: Trie-based routing engine.
- `http.py`: Request/Response classes.
- `middleware.py`: Standard middlewares.
- `utils.py`: Utilities.
- `websocket.py`: WebSocket protocol implementation.

## Quick Start

Save this as `main.py`:

```python
import uasyncio as asyncio
from microserver import MicroServer
from http import Response

app = MicroServer(port=80)

@app.get("/")
async def index(req):
    return Response.json({"message": "Hello from MicroServer"})

@app.post("/data")
async def receive(req):
    data = req.json
    return Response.json({"status": "received", "data": data})

asyncio.run(app.run())
```

## Detailed Usage

### Routing

MicroServer supports common HTTP methods and dynamic parameters.

```python
# Static Route
@app.get("/status")
async def status(req):
    return Response.plain("OK")

# Dynamic Route (captures 'user_id')
@app.get("/users/<user_id>")
async def get_user(req):
    uid = req.path_params.get("user_id")
    return Response.json({"id": uid})
```

### Middleware

Middlewares wrap the request processing pipeline. The included `CORSMiddleware` is optimized to pre-calculate headers for performance.

```python
from middleware import LoggingMiddleware, CORSMiddleware

# 1. Logging: Logs method, path, status, and duration
app.add_middleware(LoggingMiddleware())

# 2. CORS: handles OPTIONS preflight and adds headers
app.add_middleware(CORSMiddleware(
    origins="*", 
    methods="GET,POST,PUT,DELETE", 
    headers="Content-Type,Authorization"
))
```

### WebSockets

Handle real-time connections easily with full RFC 6455 compliance (v1.0.0+).

```python
@app.websocket("/ws")
async def ws_handler(ws):
    await ws.accept()
    await ws.send("Connected!")

    while True:
        msg = await ws.receive()
        if msg is None: break  # Disconnected
        await ws.send(f"Echo: {msg}")
```

**v1.0.0+ WebSocket Features:**
- **Ping/Pong Keepalive**: Automatic ping every 30s, closes connection if no pong within 60s
- **Proper Close Handshake**: Sends close frame with code/reason, waits for acknowledgment
- **Frame Validation**: RSV bits checked, max frame size enforced (64KB)
- **Control Frame Handling**: Automatically responds to ping frames with pong

```python
# Graceful close with reason
await ws.close(1000, "Normal closure")
```

### Response Objects

Use the static factory methods on `Response` for explicit content types:

```python
from http import Response

# JSON (Content-Type: application/json)
return Response.json({"key": "value"})

# HTML (Content-Type: text/html)
return Response.html("<h1>Hello</h1>")

# Plain Text (Content-Type: text/plain)
return Response.plain("Simple text")

# Error (JSON with status code)
return Response.error("Something went wrong", 400)

# Custom Status Code and Headers
return Response.json({"error": "Auth failed"}, status=401)
```

### Streaming

For large payloads, use `Response.stream` with a generator to save RAM.

```python
@app.get("/large-data")
async def stream_data(req):
    async def huge_data():
        for i in range(1000):
            yield f"Line {i}\n"
            await asyncio.sleep(0.01)
            
    return Response.stream(huge_data())
```

### Serving Static Files

Use `mount_static` to bind a URL prefix to a directory on flash.

```python
# Maps http://<ip>/static/... -> /flash/www/...
app.mount_static("/static", "/flash/www")
```

## Production Configuration

For deployment, consider these optimizations:

1.  **Memory Management**:
    *   Explicitly limit body size to prevent OOM attacks:
        ```python
        app.max_body_size = 4096 # 4KB
        ```
    *   Run garbage collection periodically in your main loop or before heavy operations.

2.  **Concurrency & Connection Limits**:
    *   Adjust `max_conns` (default 10) based on your available RAM and ESP32 socket limits:
        ```python
        app = MicroServer(port=80, max_conns=8)
        ```
    *   ESP32 standard builds have a hard limit of ~10-16 sockets (LWIP). Setting `max_conns > 10` may not work.
    *   Server logs warning at 80% capacity.

3.  **HTTP Keep-Alive**:
    *   Configure persistent connection timeouts (v1.0.0+):
        ```python
        app.keep_alive_timeout = 5  # seconds (default)
        app.max_keep_alive_requests = 100  # per connection (default)
        ```
    *   Keep-alive reduces latency for multiple requests but consumes connection slots longer.

4.  **Security & DoS Protection**:
    *   Body read timeout prevents Slowloris attacks (default 30s):
        ```python
        app.body_timeout = 30  # seconds
        ```
    *   Built-in limits (v1.0.0+):
        - Max headers: 50
        - Max header size: 8KB
        - Max request line: 8KB
        - Max WebSocket frame: 64KB

5.  **Static File Caching**:
    *   Set `Cache-Control` max-age for static assets (v1.0.0+):
        ```python
        app.mount_static("/static", "/flash/www", max_age=3600)  # 1 hour
        ```

6.  **Error Handling**:
    *   Wrap your main loop to catch `KeyboardInterrupt` or unexpected crashes and reset cleanly if needed.

### Full Configuration Example

```python
from microserver import MicroServer

app = MicroServer(
    port=80,
    max_conns=8,                    # Connection limit (ESP32 socket constraints)
)

# Timeouts & Limits
app.keep_alive_timeout = 5          # HTTP keep-alive idle timeout
app.max_keep_alive_requests = 100   # Max requests per connection
app.body_timeout = 30               # Body read timeout (Slowloris protection)
app.max_body_size = 8192            # Max request body size (8KB)

# Static files with caching
app.mount_static("/static", "/www", max_age=3600)
```

## Directory Structure

*   `microserver.py`: Server entry point.
*   `examples/`: Ready-to-run examples.
    *   `basic.py`: Simple routes.
    *   `medium.py`: Middleware and files.
    *   `full.py`: WiFi connection, Hardware control, WS.

## License

MIT License
