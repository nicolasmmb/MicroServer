import struct
import ubinascii
import hashlib
import uasyncio as asyncio


class WebSocket:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.closed = False
        self.lock = asyncio.Lock()

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
            head = await self.reader.read(2)
            if len(head) < 2:
                return None

            byte1, byte2 = head[0], head[1]
            opcode = byte1 & 0x0F
            masked = (byte2 & 0x80) != 0
            length = byte2 & 0x7F

            if opcode == 0x08:  # Close frame
                await self.close()
                return None

            if length == 126:
                data = await self.reader.read(2)
                length = struct.unpack(">H", data)[0]
            elif length == 127:
                data = await self.reader.read(8)
                length = struct.unpack(">Q", data)[0]

            mask = await self.reader.read(4) if masked else None
            payload = await self.reader.read(length)

            if masked:
                payload = bytearray(payload)
                for i in range(len(payload)):
                    payload[i] ^= mask[i % 4]

            if opcode == 0x01:
                return payload.decode()
            return payload

        except Exception:
            await self.close()
            return None

    async def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except:
                pass
