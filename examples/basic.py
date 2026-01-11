import uasyncio as asyncio
from microserver import MicroServer
from http import Response

# Initialize the server on port 80
app = MicroServer(port=80)


@app.get("/")
async def hello(req):
    """Simple Hello World endpoint."""
    return {"message": "Hello from MicroServer"}


@app.post("/echo")
async def echo(req):
    """Echo endpoint returning the request body."""
    if not req.body:
        return Response.error("Empty body", 400)

    # Return raw body as plain text
    return Response(req.body, content_type="text/plain")


@app.get("/stream")
async def stream(req):
    """Example of streaming response using a generator."""

    async def gen():
        for i in range(5):
            await asyncio.sleep(0.5)
            yield f"chunk {i}\n"

    return Response.stream(gen(), content_type="text/plain")


async def main():
    print("Starting server...")
    try:
        await app.run()
    except KeyboardInterrupt:
        print("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
