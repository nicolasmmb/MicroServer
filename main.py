import uasyncio as asyncio
import gc
import machine
import network
import sys
import time

from microserver import MicroServer
from middleware import CORSMiddleware, LoggingMiddleware
from http import Response


# ============================================================================
# 1. CONFIGURAÇÃO E EXECUÇÃO (MAIN)
# ============================================================================

# Configurações do usuário
SSID = "SEU_WIFI"
PASSWORD = "SUA_SENHA"
LED_PIN = 2  # Geralmente o LED embutido no ESP32


def connect_wifi():
    """Gerencia conexão WiFi."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando ao WiFi...")
        wlan.connect(SSID, PASSWORD)
        for _ in range(10):
            if wlan.isconnected():
                break
            time.sleep(1)

    if wlan.isconnected():
        print("WiFi Conectado:", wlan.ifconfig()[0])
    else:
        print("Falha ao conectar WiFi (Modo Offline)")


# Instancia o Servidor
# 'logging': False desativa o log interno do MicroServer para não duplicar com o Middleware
app = MicroServer(port=80, config={"logging": False, "max_body_size": 4096})

# 1. Middleware de Log (Adicionado PRIMEIRO para englobar tudo)
app.add_middleware(LoggingMiddleware())

# 2. Middleware de CORS
app.add_middleware(
    CORSMiddleware(
        origins="*", methods="GET, POST, PUT, DELETE, OPTIONS", headers="Content-Type"
    )
)


# --- Rotas ---


@app.get("/")
async def index(req):
    return """
    <!DOCTYPE html>
    <html>
    <head><title>MicroServer</title></head>
    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h1>🚀 MicroServer Online</h1>
        <p>Endpoints disponíveis:</p>
        <ul style="list-style: none;">
            <li>GET /api/status</li>
            <li>POST /api/led (JSON: {"state": 1})</li>
            <li>WS /ws/echo</li>
        </ul>
    </body>
    </html>
    """


@app.get("/api/status")
async def status(req):
    gc.collect()
    return {"status": "online", "mem_free": gc.mem_free(), "ip": req.ip}


@app.post("/api/led")
async def control_led(req):
    data = req.json
    if not data or "state" not in data:
        return Response({"error": "Missing 'state' field"}, 400)

    state = data["state"]
    try:
        pin = machine.Pin(LED_PIN, machine.Pin.OUT)
        val = 1 if state in [1, True, "on"] else 0
        pin.value(val)
        return {"success": True, "led": "ON" if val else "OFF"}
    except Exception as e:
        return Response({"error": str(e)}, 500)


@app.websocket("/ws/echo")
async def ws_echo(ws):
    print("Cliente WS conectado")
    await ws.send("Echo server pronto!")
    while True:
        try:
            msg = await ws.receive()
            if msg is None:
                break
            await ws.send(f"Echo: {msg}")
        except:
            break
    print("Cliente WS desconectado")


# --- Loop Principal ---


async def main():
    connect_wifi()
    print("Iniciando servidor assíncrono...")
    gc.collect()

    asyncio.create_task(app.start())

    while True:
        await asyncio.sleep(10)
        gc.collect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Servidor parado.")
    except Exception as e:
        sys.print_exception(e)
