import json
from utils import unquote


_PHRASES = {
    # 1xx: Informational
    100: "Continue",
    101: "Switching Protocols",
    102: "Processing",
    103: "Early Hints",
    # 2xx: Success
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non-Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    207: "Multi-Status",
    208: "Already Reported",
    226: "IM Used",
    # 3xx: Redirection
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    305: "Use Proxy",
    306: "Switch Proxy",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    # 4xx: Client Error
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Payload Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    416: "Range Not Satisfiable",
    417: "Expectation Failed",
    418: "I'm a teapot",
    421: "Misdirected Request",
    422: "Unprocessable Entity",
    423: "Locked",
    424: "Failed Dependency",
    425: "Too Early",
    426: "Upgrade Required",
    428: "Precondition Required",
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    451: "Unavailable For Legal Reasons",
    # 5xx: Server Error
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
    505: "HTTP Version Not Supported",
    506: "Variant Also Negotiates",
    507: "Insufficient Storage",
    508: "Loop Detected",
    510: "Not Extended",
    511: "Network Authentication Required",
}


class Request:
    __slots__ = (
        "method",
        "path",
        "headers",
        "query_params",
        "body",
        "ip",
        "_json",
        "path_params",
    )

    def __init__(
        self, method: str, path: str, headers: dict, ip: str, query_params: dict = None
    ):
        self.method: str = method
        self.headers: dict = headers
        self.ip: str = ip
        self.body: bytes = None
        self._json = None
        self.path_params: dict = {}

        if "?" in path:
            self.path, query_string = path.split("?", 1)
            self.query_params: dict = query_params or {}
            for pair in query_string.split("&"):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    self.query_params[unquote(key)] = unquote(value)
                elif pair:
                    self.query_params[unquote(pair)] = ""
        else:
            self.path: str = path
            self.query_params: dict = query_params or {}

    @property
    def json(self) -> dict:
        if self._json is None and self.body:
            try:
                self._json = json.loads(self.body)
            except ValueError:
                pass
        return self._json


class Response:
    __slots__ = ("body", "status", "headers", "content_type")

    def __init__(
        self, body: object, status: int = 200, content_type: str = "application/json"
    ):
        self.body = body
        self.status: int = status
        self.headers: dict = {}
        self.content_type: str = content_type

    def add_header(self, key: str, value: str):
        self.headers[key] = value

    @classmethod
    def json(cls, data: dict, status: int = 200) -> "Response":
        """Factory para respostas JSON."""
        return cls(json.dumps(data), status=status, content_type="application/json")

    @classmethod
    def html(cls, content: str, status: int = 200) -> "Response":
        """Factory para respostas HTML."""
        return cls(content, status=status, content_type="text/html")

    @classmethod
    def plain(cls, content: str, status: int = 200) -> "Response":
        """Factory para respostas de texto plano."""
        return cls(content, status=status, content_type="text/plain")

    @classmethod
    def redirect(cls, location: str) -> "Response":
        """Helper para redirecionamento."""
        resp = cls("", status=302)
        resp.add_header("Location", location)
        return resp

    @classmethod
    def error(cls, message: str, status: int = 400) -> "Response":
        """Factory para respostas de erro padronizadas."""
        return cls.json({"error": message, "code": status}, status=status)

    @classmethod
    def stream(cls, generator, content_type: str = "text/plain") -> "Response":
        """Factory para respostas em streaming (generator)."""
        return cls(generator, status=200, content_type=content_type)
