import json
from utils import unquote


class Request:
    __slots__ = ("method", "path", "headers", "query_params", "body", "ip", "_json")

    def __init__(self, method, path, headers, ip):
        self.method = method
        self.headers = headers
        self.ip = ip
        self.body = None
        self._json = None

        if "?" in path:
            self.path, qs = path.split("?", 1)
            self.query_params = {}
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    self.query_params[unquote(k)] = unquote(v)
                elif pair:
                    self.query_params[unquote(pair)] = ""
        else:
            self.path = path
            self.query_params = {}

    @property
    def json(self):
        if self._json is None and self.body:
            try:
                self._json = json.loads(self.body)
            except ValueError:
                pass
        return self._json


class Response:
    __slots__ = ("body", "status", "headers", "content_type")

    def __init__(self, body, status=200, content_type="application/json"):
        self.body = body
        self.status = status
        self.headers = {}
        self.content_type = content_type

    def add_header(self, key, value):
        self.headers[key] = value
