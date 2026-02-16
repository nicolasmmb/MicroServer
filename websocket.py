import struct
import time
import ubinascii
import hashlib
import uasyncio as asyncio
from micropython import const

MAX_FRAME_SIZE = const(65536)  # 64KB


class WebSocket:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.closed = False
        self.lock = asyncio.Lock()
        self.last_pong = time.time()
        self.ping_interval = 30  # seconds
        self._ping_task = None

    async def _ping_loop(self):
        """Background task sending pings (RFC 6455 §5.5.2)"""
        while not self.closed:
            await asyncio.sleep(self.ping_interval)
            if self.closed:
                break

            # Send ping frame (opcode 0x09)
            try:
                async with self.lock:
                    self.writer.write(b"\x89\x00")  # FIN=1, opcode=9, len=0
                    await self.writer.drain()
            except Exception:
                await self.close(1006, "Connection lost")
                break

            # Check pong timeout
            if time.time() - self.last_pong > self.ping_interval * 2:
                await self.close(1002, "Ping timeout")
                break

    async def accept(self, headers: dict) -> bool:
        """Realiza o handshake do WebSocket."""
        key = headers.get("sec-websocket-key", "")
        if not key:
            return False

        magic = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        resp_key = ubinascii.b2a_base64(
            hashlib.sha1(key.encode() + magic).digest()
        ).strip()

        resp = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + resp_key + b"\r\n\r\n"
        )
        self.writer.write(resp)
        await self.writer.drain()

        # Start ping/pong keepalive
        self._ping_task = asyncio.create_task(self._ping_loop())

        return True

    async def send(self, data):
        """Envia dados (texto ou bytes)."""
        if self.closed:
            return

        opcode = 0x01 if isinstance(data, str) else 0x02
        payload = data.encode() if isinstance(data, str) else data
        length = len(payload)

        header = bytearray()
        header.append(0x80 | opcode)

        if length < 126:
            header.append(length)
        elif length < 65536:
            header.append(126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(127)
            header.extend(struct.pack(">Q", length))

        async with self.lock:
            try:
                self.writer.write(header)
                self.writer.write(payload)
                await self.writer.drain()
            except Exception:
                self.closed = True

    async def receive(self):
        """Recebe mensagem completa."""
        if self.closed:
            return None

        try:
            while True:
                head = await self.reader.read(2)
                if len(head) < 2:
                    return None

                byte1, byte2 = head[0], head[1]

                # Check RSV bits (RFC 6455 §5.2)
                rsv = (byte1 & 0x70) >> 4
                if rsv != 0:
                    await self.close(1002, "RSV bits must be 0")
                    return None

                opcode = byte1 & 0x0F
                masked = (byte2 & 0x80) != 0
                length = byte2 & 0x7F

                # Parse extended length
                if length == 126:
                    data = await self.reader.read(2)
                    length = struct.unpack(">H", data)[0]
                elif length == 127:
                    data = await self.reader.read(8)
                    length = struct.unpack(">Q", data)[0]

                # Enforce max frame size
                if length > MAX_FRAME_SIZE:
                    await self.close(1009, "Frame too large")
                    return None

                # Read mask and payload
                mask = await self.reader.read(4) if masked else None
                payload = await self.reader.read(length) if length > 0 else b""

                # Unmask payload
                if masked and payload:
                    payload = bytearray(payload)
                    for i in range(len(payload)):
                        payload[i] ^= mask[i % 4]

                # Handle control frames
                if opcode == 0x0A:  # Pong frame
                    self.last_pong = time.time()
                    continue  # Don't return, keep reading

                if opcode == 0x09:  # Ping frame
                    # Respond with pong (same payload)
                    async with self.lock:
                        header = bytearray([0x8A, len(payload)])  # FIN=1, opcode=10
                        self.writer.write(header)
                        if payload:
                            self.writer.write(payload)
                        await self.writer.drain()
                    continue  # Don't return, keep reading

                if opcode == 0x08:  # Close frame
                    # Parse close code/reason
                    code = 1000
                    if len(payload) >= 2:
                        code = struct.unpack(">H", bytes(payload[:2]))[0]
                    await self.close(code, "Client initiated close")
                    return None

                # Handle data frames
                if opcode == 0x01:  # Text frame
                    return payload.decode()
                elif opcode == 0x02:  # Binary frame
                    return payload

                # Unknown opcode, ignore
                continue

        except Exception:
            await self.close()
            return None

    async def close(self, code=1000, reason=""):
        """Properly close WebSocket (RFC 6455 §7.1.2)"""
        if not self.closed:
            self.closed = True

            # Cancel ping task
            if self._ping_task:
                try:
                    self._ping_task.cancel()
                    await self._ping_task
                except Exception:
                    pass

            # Send close frame
            try:
                payload = struct.pack(">H", code)
                if reason:
                    payload += reason.encode()[:123]  # Max 125 bytes - 2 for code

                header = bytearray([0x88, len(payload)])  # FIN=1, opcode=8

                async with self.lock:
                    self.writer.write(header)
                    if payload:
                        self.writer.write(payload)
                    await self.writer.drain()

                # Wait for close frame from client (timeout 5s)
                try:
                    await asyncio.wait_for(self._wait_close_frame(), 5)
                except asyncio.TimeoutError:
                    pass
            except Exception:
                pass
            finally:
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except Exception:
                    pass

    async def _wait_close_frame(self):
        """Wait for close frame acknowledgment"""
        try:
            while True:
                head = await self.reader.read(2)
                if len(head) < 2:
                    break
                opcode = head[0] & 0x0F
                length = head[1] & 0x7F

                # Parse extended length
                if length == 126:
                    await self.reader.read(2)
                elif length == 127:
                    await self.reader.read(8)

                if opcode == 0x08:  # Close frame received
                    break
        except Exception:
            pass
