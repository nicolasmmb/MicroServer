import uasyncio as asyncio
import gc
import machine
import network
import time

from microserver import MicroServer
from middleware import LoggingMiddleware, CORSMiddleware
from http import Response

# Configuration
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
LED_PIN = 2  # Default onboard LED (ESP32 usually)


# Setup Network
def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f"Connecting to {ssid}...")
        wlan.connect(ssid, password)

        # Wait for connection with timeout
        timeout = 10
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > timeout:
                return False
            time.sleep(1)

    print("Network Config:", wlan.ifconfig())
    return True


# Initialize Server
app = MicroServer(port=80)
app.max_body_size = 4096

# Middlewares
app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware(origins="*", methods="*"))


@app.get("/")
async def index(req):
    return Response.json(
        {"status": "online", "system": "ESP32", "memory_free": gc.mem_free()}
    )


@app.get("/gc")
async def run_gc(req):
    """Manually trigger garbage collection."""
    before = gc.mem_free()
    gc.collect()
    after = gc.mem_free()
    return Response.json({"freed": after - before, "current_free": after})


@app.post("/led")
async def led_control(req):
    """Control an LED via JSON payload: {"state": 1} or {"state": 0}"""
    data = req.json or {}
    state = data.get("state")

    if state is None:
        return Response.error("Missing 'state' in JSON body", 400)

    try:
        # Initialize pin only when needed or globally if preferred
        pin = machine.Pin(LED_PIN, machine.Pin.OUT)
        value = 1 if state in (1, True, "on") else 0
        pin.value(value)
        return Response.json({"led": "on" if value else "off"})
    except Exception as e:
        return Response.error(f"Hardware error: {str(e)}", 500)


@app.websocket("/ws/echo")
async def ws_echo(ws):
    """Simple WebSocket Echo Server"""
    print("WS Connected")
    await ws.send("Welcome to MicroServer WS")

    try:
        while True:
            msg = await ws.receive()
            if msg is None:
                break  # Connection closed

            # Echo back
            await ws.send(f"Echo: {msg}")
    except Exception as e:
        print("WS Error:", e)
    finally:
        print("WS Disconnected")


# Mount Static Files
# app.mount_static("/", "/www") # Serve root from /www


async def main():
    # 1. Connect to WiFi
    if not connect_wifi(SSID, PASSWORD):
        print("Failed to connect to WiFi")
        return

    # 2. Start Server
    print("Starting server...")
    # Run the server loop
    asyncio.create_task(app.run())

    # 3. Request Loop for periodic tasks (e.g. status report, cleanup)
    while True:
        await asyncio.sleep(60)
        gc.collect()  # Periodically clean memory
        # print(f"Heartbeat: free mem {gc.mem_free()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted via Keyboard")
