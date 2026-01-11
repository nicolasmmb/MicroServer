import uasyncio as asyncio
from microserver import MicroServer
from middleware import LoggingMiddleware, CORSMiddleware
from http import Response
from utils import CHUNK_SIZE

app = MicroServer(port=80, config={"max_body_size": 4096, "logging": False})
app.add_middleware(LoggingMiddleware())
app.add_middleware(
    CORSMiddleware(origins="*", methods="GET,POST,OPTIONS", headers="Content-Type")
)


@app.get("/status")
async def status(req):
    return {"ok": True, "ip": req.ip}


@app.post("/sum")
async def sum_numbers(req):
    data = req.json or {}
    a = data.get("a")
    b = data.get("b")
    if a is None or b is None:
        return Response({"error": "Missing a or b"}, 400)
    try:
        return {"result": float(a) + float(b)}
    except Exception:
        return Response({"error": "Invalid numbers"}, 400)


@app.get("/stream-file")
async def stream_file(req):
    def chunks():
        with open("/flash/big.txt", "rb") as f:
            while True:
                data = f.read(CHUNK_SIZE)
                if not data:
                    break
                yield data

    return Response(chunks(), content_type="text/plain")


app.mount_static("/static", "/flash/www")

asyncio.run(app.run())
