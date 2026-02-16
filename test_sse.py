"""
Test SSE implementation in MicroPython
"""

import sys
import gc
import uasyncio as asyncio
from microserver import MicroServer
from http import Response

print("=" * 60)
print("Testing SSE Implementation")
print("=" * 60)

# Test 1: Response.sse() method exists
print("\n[1/5] Testing Response.sse() method...")
try:
    assert hasattr(Response, 'sse'), "Response.sse() method not found"
    print("✓ Response.sse() method exists")
except AssertionError as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 2: SSE response has correct content type
print("\n[2/5] Testing SSE response content type...")
try:
    async def dummy_generator():
        yield "data: test\n\n"

    response = Response.sse(dummy_generator())
    assert response.content_type == "text/event-stream", \
        f"Wrong content type: {response.content_type}"
    assert "Cache-Control" in response.headers, "Missing Cache-Control header"
    assert response.headers["Cache-Control"] == "no-cache", \
        f"Wrong Cache-Control: {response.headers['Cache-Control']}"
    print("✓ SSE response has correct headers")
    print(f"  - Content-Type: {response.content_type}")
    print(f"  - Cache-Control: {response.headers['Cache-Control']}")
    print(f"  - X-Accel-Buffering: {response.headers.get('X-Accel-Buffering', 'N/A')}")
except AssertionError as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 3: SSE generator works
print("\n[3/5] Testing SSE event generation...")
try:
    import ujson

    # MicroPython async generator compatibility
    class EventStream:
        def __init__(self):
            self.count = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.count >= 3:
                raise StopAsyncIteration
            data = {"count": self.count, "message": "test"}
            event = f"data: {ujson.dumps(data)}\n\n"
            self.count += 1
            await asyncio.sleep_ms(0)
            return event

    response = Response.sse(EventStream())

    # Consume events
    events = []
    async def consume():
        async for event in response.body:
            events.append(event)

    asyncio.run(consume())

    assert len(events) == 3, f"Expected 3 events, got {len(events)}"
    assert events[0].startswith("data:"), "Event doesn't start with 'data:'"
    assert events[0].endswith("\n\n"), "Event doesn't end with \\n\\n"

    print("✓ SSE events generated correctly")
    print(f"  - Generated {len(events)} events")
    print(f"  - Sample event: {events[0][:50]}...")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.print_exception(e)
    sys.exit(1)

# Test 4: MicroServer has _send_sse_body method
print("\n[4/5] Testing MicroServer._send_sse_body()...")
try:
    app = MicroServer(port=8080)
    assert hasattr(app, '_send_sse_body'), "MicroServer._send_sse_body() not found"
    print("✓ MicroServer has _send_sse_body() method")
except AssertionError as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 5: Integration test
print("\n[5/5] Testing SSE endpoint integration...")
try:
    app = MicroServer(port=8080)

    @app.get("/events")
    async def sse_endpoint(req):
        async def stream():
            for i in range(2):
                yield f"data: {{\"count\": {i}}}\n\n"
                await asyncio.sleep_ms(10)

        return Response.sse(stream())

    # Find the handler
    handler, _ = app.router.match("GET", "/events")

    if handler:
        # Create mock request
        from http import Request
        req = Request("GET", "/events", {}, "127.0.0.1")

        # Call handler
        async def test_handler():
            response = await handler(req)
            return response

        response = asyncio.run(test_handler())

        assert response.content_type == "text/event-stream"
        print("✓ SSE endpoint integration works")
        print(f"  - Content-Type: {response.content_type}")
        print(f"  - Response status: {response.status}")
    else:
        raise Exception("Handler not found")

except Exception as e:
    print(f"✗ Failed: {e}")
    sys.print_exception(e)
    sys.exit(1)

# Summary
print("\n" + "=" * 60)
print("✓ ALL SSE TESTS PASSED!")
print("=" * 60)

print("\n📊 SSE Implementation Summary:")
print("  ✓ Response.sse() factory method")
print("  ✓ Correct HTTP headers (text/event-stream, no-cache)")
print("  ✓ Event stream generation")
print("  ✓ MicroServer SSE body handler")
print("  ✓ Endpoint integration")

print("\n✅ SSE is ready for use!")

# Memory check
gc.collect()
print(f"\n💾 Memory: {gc.mem_free()} bytes free after tests")
