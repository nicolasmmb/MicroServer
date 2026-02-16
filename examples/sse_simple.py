"""
SSE Simple Example - Sensor Monitoring
Exemplo minimalista de Server-Sent Events
"""

import time
from http import Response

import uasyncio as asyncio
import ujson

from microserver import MicroServer

app = MicroServer(port=80)


def get_sensor_data():
    """Simula leitura de sensores"""
    import urandom

    return {
        "temperature": 20 + urandom.randint(0, 10),
        "humidity": 50 + urandom.randint(0, 30),
        "timestamp": time.time(),
    }


@app.get("/")
async def index(req):
    """Página HTML com SSE"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Sensor Monitor</title>
    <style>
        body {
            font-family: Arial;
            padding: 20px;
            background: #f0f0f0;
        }
        .sensor {
            background: white;
            padding: 20px;
            margin: 10px 0;
            border-radius: 8px;
            font-size: 24px;
        }
        .value {
            color: #2196F3;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <h1>📊 Sensor Monitor (SSE)</h1>
    <p id="status">Conectando...</p>

    <div class="sensor">
        🌡️ Temperatura: <span class="value" id="temp">--</span>°C
    </div>

    <div class="sensor">
        💧 Umidade: <span class="value" id="humidity">--</span>%
    </div>

    <div class="sensor">
        🕐 Última atualização: <span id="time">--</span>
    </div>

    <script>
        const events = new EventSource('/events');

        events.onopen = () => {
            document.getElementById('status').textContent = '✅ Conectado';
        };

        events.onerror = () => {
            document.getElementById('status').textContent = '❌ Desconectado';
        };

        events.onmessage = (e) => {
            const data = JSON.parse(e.data);

            document.getElementById('temp').textContent = data.temperature;
            document.getElementById('humidity').textContent = data.humidity;

            const time = new Date(data.timestamp * 1000).toLocaleTimeString();
            document.getElementById('time').textContent = time;
        };
    </script>
</body>
</html>
    """
    return Response.html(html)


@app.get("/events")
async def events(req):
    """SSE endpoint - atualiza a cada 2 segundos"""

    async def stream():
        while True:
            data = get_sensor_data()

            yield f"data: {ujson.dumps(data)}\n\n".encode()
            await asyncio.sleep(2)

    return Response.sse(stream())


async def main():
    print("🚀 Servidor SSE iniciando...")
    print("📡 Acesse: http://192.168.1.100/")
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
