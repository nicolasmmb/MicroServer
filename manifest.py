# Manifest for MicroServer so it can be installed via mip
metadata(
    version="0.1.0", description="Minimal HTTP/WebSocket microserver for MicroPython"
)

# Install modules directly into /lib so imports stay the same
module("microserver.py")
module("http.py")
module("middleware.py")
module("utils.py")
module("websocket.py")
