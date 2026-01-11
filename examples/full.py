import uasyncio as asyncio
import gc
import machine
import network
import time

from microserver import MicroServer
from middleware import LoggingMiddleware, CORSMiddleware
from http import Response
from utils import CHUNK_SIZE

SSID = "SEU_WIFI"
PASSWORD = "SUA_SENHA"
LED_PIN = 2  # ajuste para seu board


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        for _ in range(10):
            if wlan.isconnected():
                break
            time.sleep(1)
    return wlan.isconnected()


app = MicroServer(port=80, config={"max_body_size": 4096, "logging": False})
app.add_middleware(LoggingMiddleware())
app.add_middleware(
    CORSMiddleware(origins="*", methods="GET,POST,OPTIONS", headers="Content-Type")
)


@app.get("/")
async def index(req):
    return "MicroServer full example"


@app.get("/status")
async def status(req):
    gc.collect()
    return {"ok": True, "mem_free": gc.mem_free(), "ip": req.ip}


@app.post("/led")
async def led(req):
    data = req.json or {}
    state = data.get("state")
    if state is None:
        return Response({"error": "Missing state"}, 400)
    pin = machine.Pin(LED_PIN, machine.Pin.OUT)
    val = 1 if state in (1, True, "on") else 0
    pin.value(val)
    return {"led": "on" if val else "off"}


@app.websocket("/ws/echo")
async def ws_echo(ws):
    await ws.send("ready")
    while True:
        msg = await ws.receive()
        if msg is None:
            break
        await ws.send(f"echo: {msg}")


@app.get("/stream")
async def stream(req):
    async def gen():
        for i in range(5):
            await asyncio.sleep(0.2)
            yield f"chunk {i}\n"

    return Response(gen(), content_type="text/plain")


app.mount_static("/static", "/flash/www")


async def main():
    connected = connect_wifi()
    print("WiFi:", "ok" if connected else "offline")
    gc.collect()
    asyncio.create_task(app.run())
    while True:
        await asyncio.sleep(10)
        gc.collect()


asyncio.run(main())
