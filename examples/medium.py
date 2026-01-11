import uasyncio as asyncio
from microserver import MicroServer
from middleware import LoggingMiddleware, CORSMiddleware
from http import Response
from utils import CHUNK_SIZE

# Initialize server
app = MicroServer(port=80)

# Configure limits directly on the instance
app.max_body_size = 4096  # Limit body size to 4KB

# Add Middleware
# Logging: Prints request details to console
app.add_middleware(LoggingMiddleware())

# CORS: Allow all origins, typical methods and headers
app.add_middleware(
    CORSMiddleware(
        origins="*", methods="GET,POST,OPTIONS", headers="Content-Type,Authorization"
    )
)


@app.get("/status")
async def status(req):
    """Check server status and client IP."""
    return {"ok": True, "ip": req.ip}


@app.post("/sum")
async def sum_numbers(req):
    """Calculate sum of two numbers from JSON body."""
    # req.json implicitly parses body; returns None if invalid/empty
    data = req.json or {}

    try:
        a = float(data.get("a", 0))
        b = float(data.get("b", 0))
        return {"result": a + b}
    except (ValueError, TypeError):
        return Response.error("Invalid numbers provided", 400)


@app.get("/stream-file")
async def stream_file(req):
    """Stream a large file from flash storage."""

    # Generator to read file in chunks
    def file_chunker():
        try:
            # Adjust path as needed for your device
            with open("big.txt", "rb") as f:
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    yield data
        except OSError:
            pass  # Stream ends empty if file not found

    return Response.stream(file_chunker(), content_type="text/plain")


# Serve static files from /flash/www at /static
# Ensure the directory exists on your device
app.mount_static("/static", "/flash/www")
app.mount_static("/libs", "/flash/libs")

async def main():
    print("Starting Medium Example Server...")
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
