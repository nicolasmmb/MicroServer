# MicroServer

**MicroServer** is a minimalist, asynchronous HTTP/WebSocket server designed for MicroPython (tested on ESP32). It features decorator-based routing, robust middleware support (CORS, Logging), dynamic path parameters, static file serving, and JSON/WebSocket helpers.

Focused on **low memory footprint** and **ease of use**, it is ideal for building RESTful APIs and simple web interfaces on resource-constrained IoT devices.

## Features

*   🚀 **Asynchronous**: Built on `uasyncio` for non-blocking concurrency.
*   🛣️ **Routing**: Flask-style decorators (`@app.get`, `@app.post`) with dynamic segments (`/user/<id>`).
*   🔌 **Middleware**: Pipeline support for global request processing (CORS, Auth, Logging).
*   📂 **Static Files**: Efficient file serving with path traversal protection.
*   📜 **WebSockets**: Built-in support for real-time bidirectional communication.
*   ⚡ **Performance**: Efficient header parsing and memory management using `__slots__` and generators.

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

app = MicroServer(port=80)

@app.get("/")
async def index(req):
    return {"message": "Hello from MicroServer"}

@app.post("/data")
async def receive(req):
    data = req.json
    return {"status": "received", "data": data}

asyncio.run(app.run())
```

## Detailed Usage

### Routing

MicroServer supports common HTTP methods and dynamic parameters.

```python
# Static Route
@app.get("/status")
async def status(req):
    return "OK"

# Dynamic Route (captures 'user_id')
@app.get("/users/<user_id>")
async def get_user(req):
    uid = req.path_params.get("user_id")
    return {"id": uid}
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

Handle real-time connections easily.

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

### Response Objects

Valid return types from handlers:
1.  **Dict/List**: Automatically serialized to JSON.
2.  **String**: Returned as `text/html`.
3.  **`Response` Object**: For full control.

```python
from http import Response

# Custom Status Code and Headers
return Response(
    body="Unauthorized", 
    status=401, 
    content_type="text/plain"
)

# Stream Generator (save RAM on large payloads)
def huge_data():
    for i in range(1000):
        yield f"Line {i}\n"
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

2.  **Concurrency**:
    *   Adjust `max_conns` (default 10) based on your available RAM.
        ```python
        app.max_conns = 5
        ```

3.  **Error Handling**:
    *   Wrap your main loop to catch `KeyboardInterrupt` or unexpected crashes and reset cleanly if needed.

## Directory Structure

*   `microserver.py`: Server entry point.
*   `examples/`: Ready-to-run examples.
    *   `basic.py`: Simple routes.
    *   `medium.py`: Middleware and files.
    *   `full.py`: WiFi connection, Hardware control, WS.

## License

MIT License
