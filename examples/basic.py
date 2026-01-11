import uasyncio as asyncio
from microserver import MicroServer
from http import Response

app = MicroServer(port=80)


@app.get("/")
async def hello(req):
    return "Hello from MicroServer"


@app.post("/echo")
async def echo(req):
    return Response(req.body or b"", content_type="text/plain")


@app.get("/stream")
async def stream(req):
    async def gen():
        for i in range(3):
            await asyncio.sleep(0.1)
            yield f"chunk {i}\n"

    return Response(gen(), content_type="text/plain")


asyncio.run(app.run())
