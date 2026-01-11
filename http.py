import json
from utils import unquote


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
